import json
from typing import TypedDict

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.config import redact, settings
from app.db import Record, Repository, load_record, save_record, session
from app.llm import Proposal, structured
from app.mcp_client import call_sync
from app.patches import validate_edits
from app.retrieval import recorded_search


class State(TypedDict, total=False):
    run_id: str
    repository_id: str
    issue: str
    issue_number: int | None
    evidence: list[dict]
    tools: list[dict]
    proposal: dict
    patch: dict
    decision: str


def step(state, stage, data):
    if load_record(state["run_id"], "agent").status == "cancelled":
        raise ValueError("Investigation cancelled by user")
    save_record(
        "step", {"run_id": state["run_id"], "stage": stage, **data}, repository_id=state["repository_id"]
    )
    with session() as db:
        obj = db.get(Record, state["run_id"])
        obj.data = obj.data | {"stage": stage}


def load_issue(state):
    with session() as db:
        repo = db.get(Repository, state["repository_id"])
        owner, name = repo.name.split("/")
    tools = []
    try:
        if state.get("issue_number"):
            tool = call_sync(
                "github",
                "issue_read",
                {"owner": owner, "repo": name, "method": "get", "issue_number": state["issue_number"]},
            )
            issue = json.dumps(tool["result"])
        else:
            tool = call_sync(
                "github", "get_file_contents", {"owner": owner, "repo": name, "path": "README.md"}
            )
            issue = state["issue"]
        tools.append(tool)
    except Exception as exc:
        if state.get("issue_number"):
            raise ValueError("GitHub issue could not be read through MCP: " + redact(str(exc))) from None
        issue = state["issue"]
        tools.append({"server": "github", "status": "blocked", "error": redact(str(exc))})
    step(
        state,
        "fetch",
        {"source": "GitHub issue" if state.get("issue_number") else "Manual bug report", "tools": tools},
    )
    return {"issue": issue, "tools": tools}


def retrieve(state):
    result = recorded_search(state["repository_id"], state["issue"])
    evidence = result["evidence"]
    if not evidence:
        raise ValueError("No source evidence found; cannot propose a grounded patch")
    first = evidence[0]
    tool = call_sync(
        "custom",
        "get_source_context",
        {
            "repository_id": state["repository_id"],
            "file_path": first["path"],
            "start_line": 1,
            "end_line": 200,
        },
    )
    step(state, "retrieve", {"evidence": evidence, "tool": tool})
    return {"evidence": evidence, "tools": state["tools"] + [tool]}


def propose(state):
    prompt = json.dumps(
        {
            "task": "Diagnose this issue and propose minimal exact replacements and regression tests. "
            "Include a regression test addition or modification unless the supplied existing tests already "
            "cover every reported edge case. Identify the exact existing coverage in test_plan if reused. "
            "old must be an exact unique substring of the file; no markdown fences. "
            "Only edit evidenced files or create regression tests. If uncertain return no edits.",
            "issue": state["issue"],
            "evidence": state["evidence"],
            "tools": state["tools"],
        }
    )
    proposal = structured(Proposal, prompt, state["run_id"]).model_dump()
    if not set(proposal["evidence_ids"]) <= {e["id"] for e in state["evidence"]}:
        raise ValueError("Proposal cites evidence outside retrieved context")
    step(state, "diagnose", {"proposal": proposal})
    return {"proposal": proposal}


def validate(state):
    if not state["proposal"]["edits"]:
        raise ValueError("Insufficient evidence for a patch: " + state["proposal"]["diagnosis"])
    patch = validate_edits(
        state["repository_id"], state["proposal"]["edits"], {e["path"] for e in state["evidence"]}
    )
    step(state, "patch", {"validation": patch["validation"], "paths": patch["affected_paths"]})
    with session() as db:
        obj = db.get(Record, state["run_id"])
        obj.status, obj.data = (
            "awaiting_review",
            obj.data
            | {
                "proposal": state["proposal"],
                "patch": patch,
                "evidence": state["evidence"],
                "tools": state["tools"],
            },
        )
    return {"patch": patch}


def review(state):
    decision = interrupt(
        {"run_id": state["run_id"], "action": "review_patch", "paths": state["patch"]["affected_paths"]}
    )
    if decision not in {"approve", "reject"}:
        raise ValueError("Invalid review decision")
    return {"decision": decision}


def finish(state):
    status = "approved" if state["decision"] == "approve" else "human_rejected"
    with session() as db:
        obj = db.get(Record, state["run_id"])
        obj.status, obj.data = status, obj.data | {"decision": state["decision"], "stage": "review"}
    step(state, "review", {"decision": state["decision"]})
    return {}


def build_graph(checkpointer):
    graph = StateGraph(State)
    for name, node in [
        ("fetch", load_issue),
        ("retrieve", retrieve),
        ("diagnose", propose),
        ("patch", validate),
        ("review", review),
        ("finish", finish),
    ]:
        graph.add_node(name, node)
    graph.add_edge(START, "fetch")
    for left, right in zip(
        ["fetch", "retrieve", "diagnose", "patch", "review"],
        ["retrieve", "diagnose", "patch", "review", "finish"],
    ):
        graph.add_edge(left, right)
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpointer)


def execute(run_id, decision=None):
    run = load_record(run_id, "agent")
    config = {"configurable": {"thread_id": run_id}, "recursion_limit": 15}
    try:
        with PostgresSaver.from_conn_string(settings().conninfo) as checkpointer:
            checkpointer.setup()
            graph = build_graph(checkpointer)
            payload = (
                Command(resume=decision)
                if decision
                else {
                    "run_id": run_id,
                    "repository_id": run.repository_id,
                    "issue": run.data["issue"],
                    "issue_number": run.data.get("issue_number"),
                }
            )
            graph.invoke(payload, config)
    except Exception as exc:
        with session() as db:
            obj = db.get(Record, run_id)
            if obj.status != "cancelled":
                obj.status, obj.data = "failed", obj.data | {"error": redact(str(exc))}

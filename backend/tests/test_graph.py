from app import agent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command


def test_graph_interrupt_and_resume_across_reconstruction(monkeypatch):
    """Deterministic node fakes; tests real LangGraph checkpoint/review semantics without Gemini calls."""
    events = []
    monkeypatch.setattr(agent, "load_issue", lambda s: {"issue": s["issue"], "tools": []})
    monkeypatch.setattr(agent, "retrieve", lambda s: {"evidence": [{"id": "fixture"}]})
    monkeypatch.setattr(agent, "propose", lambda s: {"proposal": {"diagnosis": "fixture"}})
    monkeypatch.setattr(agent, "validate", lambda s: {"patch": {"affected_paths": ["money.py"]}})
    monkeypatch.setattr(agent, "finish", lambda s: events.append(s["decision"]) or {})
    saver = InMemorySaver()
    config = {"configurable": {"thread_id": "offline-fixture"}}
    graph = agent.build_graph(saver)
    result = graph.invoke(
        {"run_id": "offline-fixture", "repository_id": "fixture", "issue": "rounding defect"}, config
    )
    assert result["__interrupt__"]
    assert events == []
    rebuilt = agent.build_graph(saver)
    result = rebuilt.invoke(Command(resume="approve"), config)
    assert result["decision"] == "approve"
    assert events == ["approve"]


def test_graph_reject_path(monkeypatch):
    monkeypatch.setattr(agent, "load_issue", lambda s: {"tools": []})
    monkeypatch.setattr(agent, "retrieve", lambda s: {"evidence": []})
    monkeypatch.setattr(agent, "propose", lambda s: {"proposal": {}})
    monkeypatch.setattr(agent, "validate", lambda s: {"patch": {"affected_paths": []}})
    monkeypatch.setattr(agent, "finish", lambda s: {})
    graph = agent.build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "reject-fixture"}}
    graph.invoke({"run_id": "reject-fixture"}, config)
    assert graph.invoke(Command(resume="reject"), config)["decision"] == "reject"

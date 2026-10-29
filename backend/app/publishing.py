import httpx
from sqlalchemy import select

from app.config import settings
from app.db import Record, Repository, load_record, save_record, session


def publish_draft(run_id, approval_id):
    cfg = settings()
    if not cfg.github_remote_write_enabled or not cfg.github_token.get_secret_value():
        raise ValueError("Draft PR publishing is disabled or GitHub token is missing")
    run = load_record(run_id, "agent")
    if run.status != "test_passed":
        raise ValueError("A passing approved test run is required before publishing")
    gate = load_record(approval_id, "approval")
    if (
        gate.data.get("run_id") != run_id
        or gate.data.get("action") != "draft_pr"
        or gate.status != "approved"
    ):
        raise ValueError("This exact patch needs an explicit draft PR approval")
    with session() as db:
        repo = db.get(Repository, run.repository_id)
        if repo.meta.get("fixture"):
            raise ValueError("Deterministic fixture cannot receive pull requests")
        name = repo.name
        approval = db.scalar(select(Record).where(Record.id == approval_id))
        if approval.status != "approved":
            raise ValueError("Approval already consumed")
    # Documented GitHub REST fallback for write operations; MCP integration remains read-only.
    with httpx.Client(
        base_url="https://api.github.com",
        timeout=30,
        headers={
            "Authorization": f"Bearer {cfg.github_token.get_secret_value()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    ) as client:

        def request(method, path, body=None):
            response = client.request(method, path, json=body)
            if response.is_error:
                raise ValueError(
                    f"GitHub {method} {path}: HTTP {response.status_code}; inspect permissions/branch state"
                )
            return response.json()

        user = request("GET", "/user")
        owner = name.split("/")[0]
        if user["login"].lower() != owner.lower():
            raise ValueError("Token must belong to the authorized repository owner")
        info = request("GET", f"/repos/{name}")
        if not info.get("permissions", {}).get("push"):
            raise ValueError("Token lacks repository push permission")
        prefix = f"/repos/{name}"
        base = request("GET", f"{prefix}/git/commits/{run.data['patch']['sha']}")
        tree = request(
            "POST",
            f"{prefix}/git/trees",
            {
                "base_tree": base["tree"]["sha"],
                "tree": [
                    {"path": path, "mode": "100644", "type": "blob", "content": content}
                    for path, content in run.data["patch"]["files"].items()
                ],
            },
        )
        commit = request(
            "POST",
            f"{prefix}/git/commits",
            {"message": "fix: PatchPilot reviewed proposal", "tree": tree["sha"], "parents": [base["sha"]]},
        )
        branch = f"codex/patchpilot-{run_id[:12]}"
        request("POST", f"{prefix}/git/refs", {"ref": "refs/heads/" + branch, "sha": commit["sha"]})
        pr = request(
            "POST",
            f"{prefix}/pulls",
            {
                "title": "fix: PatchPilot reviewed proposal",
                "head": branch,
                "base": info["default_branch"],
                "draft": True,
                "body": run.data["proposal"]["diagnosis"]
                + "\n\nApproved local test run: "
                + run.data["test_id"],
            },
        )
    save_record(
        "audit",
        {"run_id": run_id, "action": "draft_pr_created", "url": pr["html_url"]},
        repository_id=run.repository_id,
    )
    with session() as db:
        obj = db.get(Record, run_id)
        obj.data = obj.data | {"pr_url": pr["html_url"]}
        gate = db.get(Record, approval_id)
        if gate:
            gate.status = "consumed"
    return {"url": pr["html_url"], "draft": True}

"""Read-only, separate MCP v1 stdio server. stdout is reserved for protocol messages."""

from app.config import settings
from app.db import load_record
from app.indexing import source_context
from app.retrieval import recorded_search
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("PatchPilot development evidence")


@mcp.tool()
def get_test_profiles() -> dict:
    """Inspect available fixed test profiles and execution policy. Does not run code or expose secrets."""
    return {
        "enabled": settings().local_test_execution_enabled,
        "profiles": {
            "fixture_python": {
                "command": "python -I -m unittest discover -s . -v",
                "scope": "labeled fixture only",
            },
            "banking_maven": {
                "command": "mvn -B -f backend/pom.xml test -DfailIfNoTests=false",
                "scope": "authorized Banking App only",
            },
        },
        "timeout_seconds": 180,
        "requires_approval": True,
        "sandbox": "Native trusted-code execution; no hardened OS/network isolation",
    }


@mcp.tool()
def get_source_context(repository_id: str, file_path: str, start_line: int = 1, end_line: int = 80) -> dict:
    """Read exact lines from an authorized indexed repository at its recorded Git revision."""
    return source_context(repository_id, file_path, start_line, end_line)


@mcp.tool()
def get_retrieval_evidence(repository_id: str, query: str) -> dict:
    """Retrieve real source citations with PostgreSQL vector/full-text reciprocal rank fusion."""
    if not 2 <= len(query) <= 2000:
        raise ValueError("Query must contain 2–2000 characters")
    return recorded_search(repository_id, query)


@mcp.tool()
def get_test_results(test_run_id: str) -> dict:
    """Read a previously recorded real test run. Never executes commands."""
    record = load_record(test_run_id, "test")
    return {"id": record.id, "status": record.status, **record.data}


if __name__ == "__main__":
    mcp.run(transport="stdio")

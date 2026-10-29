import asyncio
import json
import sys
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from app.config import ROOT, settings


@asynccontextmanager
async def custom_session():
    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"], cwd=str(ROOT))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as client:
            await client.initialize()
            yield client


@asynccontextmanager
async def github_session():
    token = settings().github_token.get_secret_value()
    if not token:
        raise ValueError("GitHub MCP needs GITHUB_TOKEN in local .env. Public Git clone remains available.")
    # Fixed official host prevents credentials being sent to an arbitrary configured endpoint.
    if settings().github_mcp_url != "https://api.githubcopilot.com/mcp/":
        raise ValueError("Only the official GitHub MCP endpoint is enabled")
    headers = {"Authorization": f"Bearer {token}", "X-MCP-Readonly": "true", "X-MCP-Toolsets": "repos,issues"}
    async with streamablehttp_client(settings().github_mcp_url, headers=headers) as (reader, writer, _):
        async with ClientSession(reader, writer) as client:
            await client.initialize()
            yield client


def parse_result(result):
    if result.isError:
        raise ValueError("MCP tool returned an error")
    if result.structuredContent:
        return result.structuredContent
    texts = [c.text for c in result.content if c.type == "text"]
    texts += [c.resource.text for c in result.content if c.type == "resource" and hasattr(c.resource, "text")]
    output = "\n".join(texts)[:24000]
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return output


async def call(server, name, arguments):
    if server == "github" and name not in {"get_file_contents", "list_issues", "issue_read", "get_me"}:
        raise ValueError("GitHub tool not allowlisted")
    if server == "custom" and name not in {
        "get_test_profiles",
        "get_source_context",
        "get_retrieval_evidence",
        "get_test_results",
    }:
        raise ValueError("Custom tool not allowlisted")
    async with asyncio.timeout(60):
        factory = custom_session if server == "custom" else github_session
        async with factory() as client:
            tools = await client.list_tools()
            if name not in {t.name for t in tools.tools}:
                raise ValueError(f"MCP server does not advertise {name}")
            output = await client.call_tool(name, arguments)
            return {
                "server": server,
                "tool": name,
                "arguments": arguments,
                "advertised_tools": [t.name for t in tools.tools],
                "result": parse_result(output),
            }


def call_sync(server, name, arguments):
    return asyncio.run(call(server, name, arguments))


async def issues(name):
    owner, repo = name.split("/")
    return await call("github", "list_issues", {"owner": owner, "repo": repo, "state": "OPEN", "perPage": 20})

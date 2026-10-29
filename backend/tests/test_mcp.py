from app.mcp_client import custom_session, parse_result


async def test_real_stdio_discovery_and_policy_tool_call():
    """Starts the actual separate Python MCP process, no transport mocks."""
    async with custom_session() as client:
        tools = (await client.list_tools()).tools
        assert {"get_source_context", "get_retrieval_evidence", "get_test_results", "get_test_profiles"} <= {
            tool.name for tool in tools
        }
        result = parse_result(await client.call_tool("get_test_profiles", {}))
        assert result["requires_approval"] is True
        assert result["timeout_seconds"] == 180
        assert "fixture_python" in result["profiles"]

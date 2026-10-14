"""Spawn the real server as a subprocess and talk MCP to it over stdio,
exactly as Claude Desktop does."""

import asyncio
import sys

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters


def run_session(db_path, scenario):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "cleandrop_mcp"],
        env={"CLEANDROP_DB": str(db_path)},
    )

    async def go():
        async with Client(params) as client:
            return await scenario(client)

    return asyncio.run(asyncio.wait_for(go(), timeout=60))


def test_tools_are_listed_with_safety_annotations(db):
    async def scenario(client):
        return {t.name: t for t in (await client.list_tools()).tools}

    tools = run_session(db.path, scenario)
    assert set(tools) == {
        "list_scheduled_deletions", "search_downloads", "get_download", "keep_file",
    }
    assert tools["search_downloads"].annotations.read_only_hint is True
    assert tools["keep_file"].annotations.destructive_hint is False
    # status is a closed enum in the schema, so the model can't invent values
    status = tools["search_downloads"].input_schema["properties"]["status"]
    assert "SCHEDULED" in str(status)


def test_search_then_keep_round_trip(db):
    row = db.add("invoice.pdf", page_title="ACME Invoice")

    async def scenario(client):
        found = await client.call_tool("search_downloads", {"query": "acme"})
        kept = await client.call_tool("keep_file", {"download_id": row})
        again = await client.call_tool("keep_file", {"download_id": row})
        return found, kept, again

    found, kept, again = run_session(db.path, scenario)
    assert found.structured_content["results"][0]["filename"] == "invoice.pdf"
    assert kept.structured_content["kept"] is True
    assert again.structured_content["kept"] is False


def test_domain_errors_become_tool_errors_not_crashes(db):
    async def scenario(client):
        return await client.call_tool("get_download", {"download_id": 999})

    result = run_session(db.path, scenario)
    assert result.is_error is True
    assert "No tracked download" in str(result.content)

# CleanDrop MCP Server

A local [MCP](https://modelcontextprotocol.io) server that lets an AI assistant
(Claude Desktop, Cursor, ...) answer questions about files CleanDrop is tracking
and keep them from being deleted. Runs over **stdio**: no network port, no cloud,
data never leaves the machine.

> **Scope:** CleanDrop only writes a database row when a deletion is *scheduled*.
> This is not a full download history, only files that were given an expiry.

## Tools

| Tool | Kind | Purpose |
|---|---|---|
| `list_scheduled_deletions(within_days?, limit?)` | read-only | "What's about to be deleted?" |
| `search_downloads(query?, status?, days?, limit?)` | read-only | Find tracked files; `status=DELETED` answers "what did you delete?" |
| `get_download(download_id)` | read-only | One file's details |
| `keep_file(download_id)` | state-changing | Cancel a pending deletion. Cannot delete or restore anything |

## Install (Windows)

```powershell
cd CleanDrop\mcp-server
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
.venv\Scripts\python -m pytest        # 29 tests
```

## Claude Desktop

Edit `%APPDATA%\Claude\claude_desktop_config.json`, merge into `mcpServers`, restart Claude Desktop:

```json
{
  "mcpServers": {
    "cleandrop": {
      "command": "C:\\path\\to\\CleanDrop\\mcp-server\\.venv\\Scripts\\python.exe",
      "args": ["-m", "cleandrop_mcp"]
    }
  }
}
```

Use the **full path** to the venv's python.exe: Claude Desktop does not activate your venv.
Optional: set `"env": {"CLEANDROP_DB": "..."}` to point at a different database.

Try: *"What's CleanDrop going to delete in the next 3 days?"* then *"Keep the second one."*

## Design

```
server.py      MCP adapter (only file importing the SDK)
   |
service.py     validation, limits, output shaping/sanitising
   |
domain.py      Download, DeleteStatus, ports: DownloadReader, DeletionCanceller
   |
repository.py  SQLite adapters (reader: mode=ro, canceller: one guarded UPDATE)
```

## Security decisions

- **Read path is physically read-only** (`mode=ro`); the only write is one guarded `UPDATE`.
- **`keep_file` uses compare-and-set** (`AND delete_status='SCHEDULED'`), the same pattern as the scheduler's claim, so it races safely with the background service.
- **No delete tool.** Least privilege: the worst a misbehaving agent can do is *keep* files.
- **Incognito downloads are never exposed.**
- **URLs reduced to hostname**: full URLs often carry tokens. Query strings are not searchable either.
- **Website-controlled text is untrusted** (filename, page title): control/invisible characters stripped and length capped. Mitigates, does not eliminate, prompt injection via tool output.
- **Bounded outputs**: `limit` capped at 50; `has_more` tells the model when to narrow.

## Known limitations

- `keep_file` cancels a *pending* deletion only; restoring from the Recycle Bin is not implemented.
- Search is `LIKE`-based (no ranking). FTS5 is a natural upgrade.
- stdio = one client per process.

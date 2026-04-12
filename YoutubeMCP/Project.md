# YoutubeMCP — Project Documentation

## Overview

**YoutubeMCP** is a minimal **Model Context Protocol (MCP) server** written in Python that exposes a single tool — `get_transcript` — to any MCP-compatible client (Claude Desktop, Claude Code CLI, MCP Inspector, etc.). Given a YouTube video URL or video ID, the server fetches the full transcript and returns it as plain text. The intended workflow is: paste a URL into Claude, get the transcript back, and ask Claude to summarize it — all without opening a browser.

The server uses [`youtube-transcript-api`](https://github.com/jdepoix/youtube-transcript-api) under the hood and optionally routes requests through a [Webshare](https://www.webshare.io/) rotating proxy to avoid IP-based rate limits from YouTube.

---

## Project Structure

```
YoutubeMCP/
├── server.py            # MCP server entrypoint — registers tools, starts the server
├── src/
│   ├── __init__.py      # Package init — re-exports core symbols
│   ├── service.py       # YouTubeTranscriptService — API wrapper + proxy config
│   └── utils.py         # extract_video_id — URL parsing helper
├── main.py              # Placeholder entry (not used by the MCP server)
├── test.py              # Manual smoke test for get_transcript
├── pyproject.toml       # Project metadata (uv / pip)
├── .python-version      # Pins Python 3.13 for uv
├── src/.env             # Proxy credentials (WEBSHARE_USERNAME / PASSWORD)
└── README.md            # Quickstart
```

---

## File-by-File Breakdown

### `server.py` — MCP Server Entrypoint

This is the **heart of the project**. It does three things:

1. **Declares inline `uv` script dependencies** via the `# /// script` comment block at the top. This lets `uv run server.py` install all dependencies into an isolated environment automatically — no manual `pip install` needed.

2. **Creates the MCP server instance** using `FastMCP` from the `mcp` library:
   ```python
   mcp = FastMCP(name="YouTube", stateless_http=True)
   ```
   `stateless_http=True` means every request is independent — no session state is held between tool calls.

3. **Registers the `get_transcript` tool** using the `@mcp.tool()` decorator:
   ```python
   @mcp.tool()
   def get_transcript(video_url_or_id: str) -> str:
       """Get transcript as plain text."""
       return _service.get_transcript_text(video_url_or_id)
   ```
   The function signature and docstring are used by MCP to advertise the tool to clients (Claude reads the docstring as the tool description).

4. **Starts the server** in stdio transport mode when run directly:
   ```python
   if __name__ == "__main__":
       mcp.run(transport="stdio")
   ```
   `stdio` transport means the server reads JSON-RPC messages from stdin and writes responses to stdout. Claude Desktop / Claude Code spawn the server as a subprocess and communicate over its stdio pipes.

**Where MCP is handled:** `server.py` is the only file that touches `mcp`. The `FastMCP` class handles all MCP protocol details — tool listing, JSON-RPC message parsing, schema generation from type hints, and error serialization. You never write raw MCP protocol code.

---

### `src/service.py` — YouTubeTranscriptService

This class wraps `youtube-transcript-api` and adds optional Webshare proxy support.

```
YouTubeTranscriptService
  ├── __init__(use_proxy: bool)
  │     └── calls _create_api()
  ├── _create_api(use_proxy) -> YouTubeTranscriptApi
  │     ├── if use_proxy AND env vars set → WebshareProxyConfig → requests.Session → YouTubeTranscriptApi(http_client=...)
  │     └── otherwise → plain YouTubeTranscriptApi()
  ├── fetch(video_url_or_id) -> raw transcript object
  │     └── calls extract_video_id() from utils, then api.fetch(video_id)
  └── get_transcript_text(video_url_or_id) -> str
        └── fetch() → TextFormatter.format_transcript() → plain string
```

**Proxy flow:** If `WEBSHARE_USERNAME` and `WEBSHARE_PASSWORD` are set in the environment, `WebshareProxyConfig` builds a proxy dict, which is injected into a `requests.Session`, and that session is passed to `YouTubeTranscriptApi` as its HTTP client. If the env vars are absent, the API falls back to a direct connection silently.

In `server.py` the service is instantiated once at module load time:
```python
_service = YouTubeTranscriptService(use_proxy=True)
```
This means the proxy config (and env var check) happens once at startup, not per request.

---

### `src/utils.py` — extract_video_id

A single pure function that parses a YouTube URL or bare video ID and returns the 11-character video ID.

```python
def extract_video_id(url_or_id: str) -> str:
```

Three regex patterns are tried in order:

| Pattern | Matches |
|---|---|
| `(?:v=\|/)([0-9A-Za-z_-]{11}).*` | Standard `?v=ID` URLs and `/ID` path segments |
| `(?:embed/)([0-9A-Za-z_-]{11})` | Embed URLs (`/embed/ID`) |
| `([0-9A-Za-z_-]{11})$` | Bare 11-character IDs passed directly |

If none match, the input is returned as-is (letting the API produce its own error).

---

### `src/__init__.py` — Package Init

Re-exports the two public symbols so callers can import from `src` directly:

```python
from .service import YouTubeTranscriptService
from .utils import extract_video_id

__all__ = ["YouTubeTranscriptService", "extract_video_id"]
```

---

### `main.py` — Placeholder Entry

Auto-generated by `uv init`. Not used by the MCP server at all. Contains only:

```python
def main():
    print("Hello from youtubemcp!")
```

Can be ignored or deleted.

---

### `test.py` — Manual Smoke Test

A quick sanity-check script. Imports `get_transcript` directly from `server.py` and calls it with a known video URL:

```python
from server import get_transcript
t = get_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
print(t)
```

Run it with `uv run test.py` to verify the full stack works end-to-end without needing an MCP client.

---

### `src/.env` — Proxy Credentials

Holds the two optional environment variables:

```
WEBSHARE_USERNAME=
WEBSHARE_PASSWORD=
```

**Note:** `python-dotenv` is listed as a dependency but `load_dotenv()` is not explicitly called in `service.py`. If you want `.env` to be loaded automatically, add `from dotenv import load_dotenv; load_dotenv()` at the top of `server.py` or `service.py`. Currently the values must be set as real shell environment variables before starting the server.

---

### `pyproject.toml` — Project Metadata

Minimal uv/pip project config. The actual runtime dependencies for the server are declared inline in `server.py`'s `# /// script` block, not here. This file is mainly for `uv init` bookkeeping.

```toml
[project]
name = "youtubemcp"
version = "0.1.0"
requires-python = ">=3.13"
```

---

### `.python-version`

Pins the Python version to `3.13` for `uv`'s automatic Python management.

---

## How the Files Connect

```
Claude Desktop / Claude Code CLI
        │  (spawns subprocess, communicates via stdio)
        ▼
    server.py
        │  FastMCP handles MCP protocol (JSON-RPC over stdio)
        │  @mcp.tool() registers get_transcript
        │
        ├── instantiates at startup
        ▼
    src/service.py  (YouTubeTranscriptService)
        │
        ├── reads env vars WEBSHARE_USERNAME / WEBSHARE_PASSWORD
        │   from src/.env (must be exported to shell) or shell env
        │
        ├── builds YouTubeTranscriptApi (with or without proxy)
        │
        ├── on each tool call: calls extract_video_id(url)
        │         ▼
        │     src/utils.py  (extract_video_id)
        │         returns 11-char video ID
        │
        └── calls api.fetch(video_id)
                  ▼
            youtube-transcript-api (third-party)
                  │  optionally routed through Webshare proxy
                  ▼
            YouTube servers → raw transcript data
                  │
            TextFormatter.format_transcript()
                  │
                  ▼
            plain text string → returned to MCP client
```

---

## Where MCP Is Handled

MCP (Model Context Protocol) machinery lives entirely in **`server.py`** and is managed by the `FastMCP` class from the `mcp[cli]` package. Here is what each MCP-related piece does:

| Code | MCP Role |
|---|---|
| `FastMCP(name="YouTube", stateless_http=True)` | Creates the server, sets its advertised name |
| `@mcp.tool()` | Registers `get_transcript` as a callable MCP tool; auto-generates the JSON Schema from the Python type hints |
| `mcp.run(transport="stdio")` | Starts the JSON-RPC event loop reading from stdin and writing to stdout |
| Function docstring on `get_transcript` | Becomes the tool's `description` field in MCP tool listings — this is what Claude reads to know what the tool does |
| Return type `-> str` | Tells MCP the tool returns a text result |

The `stateless_http=True` flag means the server is also compatible with HTTP transport (e.g., running behind a proxy or in Claude Desktop's HTTP mode) but defaults to stdio for local use.

---

## How to Run

### 1. Development / inspection

```bash
# From the YoutubeMCP directory:
mcp dev server.py
# Opens MCP Inspector at localhost:5173 — browse tools, run get_transcript manually
```

### 2. Smoke test (no client needed)

```bash
uv run test.py
```

### 3. Connect to Claude Code CLI

```bash
claude mcp add --transport stdio YouTube -- \
  uv --directory "/path/to/YoutubeMCP" run server.py

# Verify:
claude mcp tools YouTube
```

### 4. Connect to Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "YouTube": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/YoutubeMCP",
        "run",
        "server.py"
      ]
    }
  }
}
```

Restart Claude Desktop. The `get_transcript` tool will appear in Claude's tool list.

### 5. Enable proxy (optional)

Set before running the server:

```bash
export WEBSHARE_USERNAME=your_username
export WEBSHARE_PASSWORD=your_password
uv run server.py
```

Or populate `src/.env` and ensure `load_dotenv()` is called in `server.py`.

---

## Data Flow Summary (Single Tool Call)

```
User in Claude: "Summarize this video: https://youtu.be/abc123xyz01"
        │
        ▼
Claude identifies get_transcript tool → sends MCP tool call JSON to server stdin
        │
        ▼
server.py: FastMCP deserializes call, invokes get_transcript("https://youtu.be/abc123xyz01")
        │
        ▼
service.py: get_transcript_text("https://youtu.be/abc123xyz01")
        │
        ▼
utils.py: extract_video_id("https://youtu.be/abc123xyz01") → "abc123xyz01"
        │
        ▼
youtube-transcript-api: api.fetch("abc123xyz01") [via Webshare proxy if configured]
        │
        ▼
TextFormatter: formats raw transcript segments → plain text string
        │
        ▼
service.py returns string to server.py
        │
        ▼
FastMCP serializes result as MCP tool response → writes JSON to stdout
        │
        ▼
Claude receives transcript text → generates summary for user
```

---

## Dependencies (from `server.py` script block)

| Package | Purpose |
|---|---|
| `mcp[cli]>=1.12.3` | MCP server framework (`FastMCP`, stdio transport) |
| `pydantic>=2.11.7` | Data validation (used internally by `mcp`) |
| `python-dotenv>=1.1.1` | Load `.env` file into environment |
| `requests>=2.32.4` | HTTP client used by `YouTubeTranscriptApi` for proxy support |
| `youtube-transcript-api>=1.2.2` | Fetches YouTube transcripts, provides `TextFormatter` and `WebshareProxyConfig` |

---

## Known Gaps / Things to Be Aware Of

1. **`load_dotenv()` is never called.** `python-dotenv` is a listed dependency but the code never calls `load_dotenv()`. The `src/.env` file will not be loaded automatically — proxy credentials must be exported to the shell environment manually.

2. **`main.py` is unused.** It is a `uv init` artifact and plays no role in the MCP server.

3. **Single tool only.** The server exposes exactly one tool: `get_transcript`. Expanding it (e.g., `get_video_metadata`, `search_channel`) would follow the same `@mcp.tool()` pattern in `server.py` backed by new methods in `service.py`.

4. **No language selection.** `YouTubeTranscriptApi.fetch()` picks the default language for the video. If multi-language support is needed, `fetch()` accepts a `languages` parameter.

5. **Error handling is minimal.** Any exception from the service is caught in `server.py` and returned as an `"Error: ..."` string rather than an MCP error object. This is functional but means Claude sees errors as tool text, not structured failures.

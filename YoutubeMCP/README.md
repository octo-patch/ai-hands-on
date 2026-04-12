# YoutubeMCP — Minimal MCP server for YouTube transcripts

This repository provides a minimal Model Context Protocol (MCP) server that fetches YouTube transcripts on demand. It's designed for local developer automation (for example, connecting to Claude Desktop or Claude Code) so you can quickly summarize videos without opening a browser.

## Features

- Fetch YouTube video transcripts by URL
- Run as a local MCP server via `uv` or stdio
- Optional proxy support for Webshare-style proxies

## Prerequisites

- Python 3.12+
- `uv` (see https://docs.astral.sh/uv/)
- Claude Desktop or Claude Code (optional client)

> Replace `<ABSOLUTE_PATH_TO_THIS_DIR>` in examples below with this repository path.

## Project layout

- `main.py` — project entry (if present)
- `pyproject.toml` — project metadata and dependencies
- `mcp/servers/youtube/` — (convention) MCP server code
  - `server.py` — MCP entrypoint that registers tools
  - `src/service.py` — YouTube transcript wrapper
  - `src/utils.py` — helper utilities

Adjust locations if your implementation differs.

## Quickstart — run locally with `uv`

1. Add a `uv` script header at the top of `server.py` to let `uv` create an isolated environment. Example header:

```py
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "mcp[cli]>=1.12.3",
#   "pydantic>=2.11.7",
#   "python-dotenv>=1.1.1",
#   "requests>=2.32.4",
#   "youtube-transcript-api>=1.2.2",
# ]
# ///
```

2. From the directory containing `server.py`, run:

```bash
uv run server.py
```

3. Use the MCP Inspector or your client (Claude Desktop/Code) to list and run available tools (for example, `get_transcript`).

## Run via stdio (for Claude Code)

You can expose the server over stdio and register it with Claude Code or other clients. Example `claude` CLI usage:

```bash
claude mcp add --transport stdio YouTube -- \
  uv --directory "<ABSOLUTE_PATH_TO_THIS_DIR>" run server.py

claude mcp tools YouTube
```

## Proxy support (optional)

If you need to route transcript requests through a proxy service like Webshare, set these environment variables before running:

```
WEBSHARE_USERNAME=<your_username>
WEBSHARE_PASSWORD=<your_password>
```

## Example: Configure Claude Desktop

In Claude Desktop settings, add an MCP server entry that runs `uv` in this repository directory. Example config snippet:

```json
{
  "mcpServers": {
    "YouTube": {
      "command": "uv",
      "args": [
        "--directory",
        "<ABSOLUTE_PATH_TO_THIS_DIR>",
        "run",
        "server.py"
      ]
    }
  }
}
```

Restart Claude Desktop after editing the config; `get_transcript` and other tools should appear.

## Typical workflow

1. A new YouTube video appears.
2. Call `get_transcript` from Claude Desktop/Code with the video URL.
3. Paste the returned transcript to your model to summarize or extract notes.

This saves time by letting you decide whether a video is worth watching.

## Development

- Implement tool registration in `server.py` and keep business logic in `mcp/servers/youtube/src/`.
- Use environment variables for secrets and proxy credentials.

## License & Contributing

Contributions welcome. Open an issue or PR with proposed changes.

---

If you'd like, I can also:
- add a `pyproject.toml` example with server dependencies,
- scaffold `mcp/servers/youtube/server.py` with a minimal tool registration,
- or run a quick local `uv` test (if you want me to execute commands).
How to Automate Anything with Python Inside Claude Desktop (Using MCP)
This tutorial shows how to build a minimal Model Context Protocol (MCP) server in Python, manage and run it with uv, and connect it to Claude Desktop or Claude Code. We’ll use a practical example: fetch the transcript of any YouTube video on demand so you can summarize it and decide whether it’s worth watching.

Why MCP? It’s perfect for developer-side automations you want to trigger immediately from your IDE or desktop assistant—no deployments or UIs required. Great for personal workflows; not aimed at production apps.

Prerequisites
Python 3.12+
uv (see https://docs.astral.sh/uv/)
Claude Desktop or Claude Code
Replace any absolute paths below with your own, for example: <ABSOLUTE_PATH_TO_THIS_DIR>.

Project layout
mcp/servers/youtube/
  server.py              # MCP entrypoint with tools
  src/
    __init__.py
    service.py           # YouTubeTranscriptService wrapper
    utils.py             # helpers (extract_video_id)
  pyproject.toml         # deps for this server when using uv
  README.md              # this guide
Step: 1 Add a uv script header to simplify running
At the very top of server.py, add the script metadata so uv run server.py resolves everything automatically:

# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "mcp[cli]>=1.12.3",
#     "pydantic>=2.11.7",
#     "python-dotenv>=1.1.1",
#     "requests>=2.32.4",
#     "youtube-transcript-api>=1.2.2",
# ]
# ///
This lets uv create an isolated environment and install only what this script needs.

Step 2: Create your server
Create your server.py, implement any logic and register your tools. Use stdio for easy local servers without needing deployment.

Step 3: Run the dev server locally
From this directory:

mcp dev server.py
Test the server with the MCP Inspector tool. Connect > Tools > List Tools > get_transcript > Insert URL > Run Tool.

Step 4: Proxy support (Optional)
The transcript service supports Webshare proxies if you set these environment variables (otherwise it uses a direct connection):

WEBSHARE_USERNAME=<your_username>
WEBSHARE_PASSWORD=<your_password>
Step 5: Connect from Claude Desktop
Go to Claude Desktop > Settings > Developer > Edit Config > Edit §claude_desktop_config.json` and add:

{
  "mcpServers": {
    "YouTube": {
      "command": "uv",
      "args": [
        "--directory",
        "<ABSOLUTE_PATH_TO_THIS_DIR>",
        "run",
        "server.py"
      ]
    }
  }
}
Restart Claude Desktop. You should see tools like get_transcript available.

Step 6: Connect from Claude Code (CLI)
From anywhere:

claude mcp add --transport stdio YouTube -- \
  uv --directory "<ABSOLUTE_PATH_TO_THIS_DIR>" run server.py
Then list tools:

claude mcp tools YouTube
Typical workflow (why this is useful)
A new video drops and you don’t have time to watch it.
In Claude Desktop or Code, call get_transcript with the URL.
Paste the transcript to your model for a quick summary.
Decide if it’s worth a full watch—all without opening a browser tab.
This pattern generalizes to countless “small but effective” dev automations.
# multimodal-reader-mcp

MCP server for reading local audio and video files with Google Gen AI and returning structured observations, timelines, and transcripts.

## Requirements

- `uv`
- Python `3.14`
- `GOOGLE_API_KEY`


## MCP client configuration

Example Cursor MCP config:

```json
{
  "mcpServers": {
    "multimodal-reader": {
      "command": "uvx",
      "args": ["multimodal-reader-mcp"],
      "env": {
        "GOOGLE_API_KEY": "${env:GOOGLE_API_KEY}"
      }
    }
  }
}
```

## Tool

The package exposes one MCP tool:

- `read_media(file_path, question=None, model="gemini-2.5-flash")`

`file_path` must be an absolute path to a local media file.


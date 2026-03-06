# multimodal-reader-mcp

MCP server for reading local audio and video files with Google Gen AI and returning structured observations, timelines, and transcripts.

It analyzes a local media file and returns:

- a short summary
- a timeline of key moments
- transcript snippets for spoken or visible text
- key observations and notable signals
- relevant clues tailored to the user's question
- open questions plus a confidence level

## Requirements

- `uv`
- Python `3.14`
- `GOOGLE_API_KEY`

## Model configuration

The default model is `gemini-2.5-flash`.

You can override the default model for all requests by setting:

- `MULTIMODAL_READER_MODEL`

Users can also still pass `model` directly to the `read_media` tool call.


## MCP client configuration

Example Cursor MCP config:

```json
{
  "mcpServers": {
    "multimodal-reader": {
      "command": "uvx",
      "args": ["multimodal-reader-mcp"],
      "env": {
        "GOOGLE_API_KEY": "${env:GOOGLE_API_KEY}",
        "MULTIMODAL_READER_MODEL": "gemini-2.5-flash"
      }
    }
  }
}
```

## Tool

The package exposes one MCP tool:

- `read_media(file_path, question=None, model="gemini-2.5-flash")`

`file_path` must be an absolute path to a local media file.


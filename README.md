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
- `NOTION_TOKEN` (optional, required for analyzing Notion attachment files)

## Model configuration

The default model is `gemini-2.5-flash`.

You can override the default model for all requests by setting:

- `MULTIMODAL_READER_MODEL`


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
        "MULTIMODAL_READER_MODEL": "gemini-2.5-flash",
        "NOTION_TOKEN": "${env:NOTION_TOKEN}"
      }
    }
  }
}
```

## Tools

The package exposes two MCP tools:

### `read_media(file_path, question=None)`

Reads a local audio or video file and returns structured analysis.

`file_path` must be an absolute path to a local media file.

### `read_notion_page_media(notion_markdown, question=None, page_title=None, page_url=None)`

Analyzes all video and audio media embedded in a Notion page.

`notion_markdown` is the enhanced Markdown output from `notion-fetch`. The tool
extracts `<video>` and `<audio>` blocks, downloads the media files, and returns
structured Gemini analysis for each.

For Notion-hosted attachment files (the `file://` attachment format), set the
`NOTION_TOKEN` environment variable to enable automatic resolution of signed
download URLs via the Notion API.

Typical workflow with an MCP client that also has the Notion MCP configured:

1. Fetch the page: `notion-fetch(id="page-id", include_transcript=true)`
2. Pass the result: `read_notion_page_media(notion_markdown=..., question=...)`


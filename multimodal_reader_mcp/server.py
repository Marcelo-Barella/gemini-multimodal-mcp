import mimetypes
import os
from enum import StrEnum
from pathlib import Path

from google import genai
from google.genai import types
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from multimodal_reader_mcp.downloads import download_to_tempfile
from multimodal_reader_mcp.notion import extract_media_references, resolve_attachment_url
from multimodal_reader_mcp.uploads import get_or_upload_media_reference


DEFAULT_MODEL_ENV_VAR = "MULTIMODAL_READER_MODEL"
FALLBACK_MODEL = "gemini-2.5-flash"
DEFAULT_MODEL = os.environ.get(DEFAULT_MODEL_ENV_VAR, FALLBACK_MODEL)


class ConfidenceLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GeneratedMediaAnalysis(BaseModel):
    summary: str = Field(description="Short summary of the recording.")
    timeline: list[str] = Field(description="Ordered timeline entries for key moments.")
    transcript: list[str] = Field(description="Spoken or clearly visible text content.")
    key_observations: list[str] = Field(description="Most important direct observations from the media.")
    notable_signals: list[str] = Field(description="Errors, transitions, repeated actions, or unusual signals.")
    relevant_clues: list[str] = Field(description="Details most relevant to the user's question or likely follow-up tasks.")
    open_questions: list[str] = Field(description="Uncertainties or missing evidence.")
    confidence: ConfidenceLevel = Field(description="Confidence in the analysis based on media quality and clarity.")


class MediaAnalysisResult(BaseModel):
    file_path: str = Field(description="Absolute path to the analyzed file.")
    file_name: str = Field(description="Basename of the analyzed file.")
    mime_type: str = Field(description="Detected MIME type for the analyzed file.")
    model: str = Field(description="Gemini model used for the analysis.")
    question: str | None = Field(description="Optional user question that guided the analysis.")
    summary: str = Field(description="Short summary of the recording.")
    timeline: list[str] = Field(description="Ordered timeline entries for key moments.")
    transcript: list[str] = Field(description="Spoken or clearly visible text content.")
    key_observations: list[str] = Field(description="Most important direct observations from the media.")
    notable_signals: list[str] = Field(description="Errors, transitions, repeated actions, or unusual signals.")
    relevant_clues: list[str] = Field(description="Details most relevant to the user's question or likely follow-up tasks.")
    open_questions: list[str] = Field(description="Uncertainties or missing evidence.")
    confidence: ConfidenceLevel = Field(description="Confidence in the analysis based on media quality and clarity.")


NOTION_TOKEN_ENV_VAR = "NOTION_TOKEN"


class NotionMediaEntry(BaseModel):
    source_url: str = Field(description="Original URL from the Notion markdown.")
    media_type: str = Field(description="Type of media: video or audio.")
    caption: str = Field(description="Caption text from the media block.")
    is_notion_attachment: bool = Field(description="Whether this is a Notion-hosted attachment file.")
    download_url: str | None = Field(description="Resolved HTTP URL used for download.")
    analysis: GeneratedMediaAnalysis | None = Field(description="Gemini analysis result, if successful.")
    error: str | None = Field(description="Error message if download or analysis failed.")


class NotionPageMediaAnalysis(BaseModel):
    page_title: str | None = Field(description="Title of the Notion page.")
    page_url: str | None = Field(description="URL of the Notion page.")
    model: str = Field(description="Gemini model used for analysis.")
    question: str | None = Field(description="Optional user question that guided the analysis.")
    media_found: int = Field(description="Total number of media blocks found on the page.")
    media_analyzed: int = Field(description="Number of media blocks successfully analyzed.")
    entries: list[NotionMediaEntry] = Field(description="Per-media analysis entries.")


mcp = FastMCP("multimodal-reader")


def _require_api_key() -> str:
    try:
        return os.environ["GOOGLE_API_KEY"]
    except KeyError as error:
        raise EnvironmentError("GOOGLE_API_KEY is not set.") from error


def _resolve_file_path(file_path: str) -> Path:
    path = Path(file_path).expanduser().resolve()
    if not path.is_absolute():
        raise ValueError("file_path must be absolute.")
    if not path.exists():
        raise FileNotFoundError(f"Media file does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")
    return path


def _detect_mime_type(path: Path) -> str:
    guessed_mime_type, _ = mimetypes.guess_type(path.name)
    if guessed_mime_type is None:
        raise ValueError("Could not detect MIME type from file extension. Provide mime_type explicitly.")
    return guessed_mime_type


def _build_prompt(
    *,
    file_name: str,
    question: str | None,
) -> str:
    base_prompt = f"""Analyze this local media file and return JSON that matches the provided schema.

File name: {file_name}

Requirements:
- Stay grounded in direct evidence from the media.
- Distinguish observations from hypotheses.
- Preserve timing clues when possible.
- If audio or video quality is poor, reflect that in open_questions and confidence.
- Put the most important details for the user's question in relevant_clues.
"""
    if question is None:
        question_prompt = """

No user question was provided.
Focus on a useful general-purpose reading of the media.
"""
    else:
        question_prompt = f"""

User question: {question}

Tailor relevant_clues to this question while keeping the rest of the analysis general and evidence-based.
"""
    focus_prompt = """

General reading focus:
- explain what happens over time
- capture visible text and spoken content
- highlight notable actions, screens, and state changes
- include problem indicators only if they are directly relevant to what is seen or heard
"""
    return base_prompt + question_prompt + focus_prompt


def _analyze_media(
    *,
    file_path: Path,
    mime_type: str,
    question: str | None,
    model: str,
) -> GeneratedMediaAnalysis:
    client = genai.Client(api_key=_require_api_key())
    _, media_part = get_or_upload_media_reference(client, file_path, mime_type)
    response = client.models.generate_content(
        model=model,
        contents=[_build_prompt(file_name=file_path.name, question=question), media_part],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GeneratedMediaAnalysis,
        ),
    )
    if response.parsed is None:
        raise RuntimeError("Gemini returned no structured response.")
    return GeneratedMediaAnalysis.model_validate(response.parsed)


@mcp.tool()
def read_media(
    file_path: str,
    question: str | None = None,
) -> MediaAnalysisResult:
    """Read a local audio or video file and return structured analysis."""
    model = DEFAULT_MODEL
    resolved_path = _resolve_file_path(file_path)
    resolved_mime_type = _detect_mime_type(resolved_path)
    generated_analysis = _analyze_media(
        file_path=resolved_path,
        mime_type=resolved_mime_type,
        question=question,
        model=model,
    )
    return MediaAnalysisResult(
        file_path=str(resolved_path),
        file_name=resolved_path.name,
        mime_type=resolved_mime_type,
        model=model,
        question=question,
        summary=generated_analysis.summary,
        timeline=generated_analysis.timeline,
        transcript=generated_analysis.transcript,
        key_observations=generated_analysis.key_observations,
        notable_signals=generated_analysis.notable_signals,
        relevant_clues=generated_analysis.relevant_clues,
        open_questions=generated_analysis.open_questions,
        confidence=generated_analysis.confidence,
    )


def _analyze_and_build_entry(
    *,
    download_url: str,
    source_url: str,
    media_type: str,
    caption: str,
    is_notion_attachment: bool,
    filename_hint: str | None,
    question: str | None,
    model: str,
) -> NotionMediaEntry:
    downloaded = download_to_tempfile(download_url, filename_hint=filename_hint)
    try:
        generated = _analyze_media(
            file_path=downloaded.file_path,
            mime_type=downloaded.mime_type,
            question=question,
            model=model,
        )
    finally:
        downloaded.file_path.unlink(missing_ok=True)
    return NotionMediaEntry(
        source_url=source_url,
        media_type=media_type,
        caption=caption,
        is_notion_attachment=is_notion_attachment,
        download_url=download_url,
        analysis=generated,
        error=None,
    )


@mcp.tool()
def read_notion_page_media(
    notion_markdown: str,
    question: str | None = None,
    page_title: str | None = None,
    page_url: str | None = None,
) -> NotionPageMediaAnalysis:
    """Analyze all video and audio media embedded in a Notion page.

    Accepts the enhanced Markdown output from notion-fetch.
    Extracts video and audio blocks, downloads the media files,
    and returns structured Gemini analysis for each.
    Set NOTION_TOKEN env var to enable Notion attachment file resolution.
    """
    model = DEFAULT_MODEL
    notion_token = os.environ.get(NOTION_TOKEN_ENV_VAR)
    references = extract_media_references(notion_markdown)
    entries: list[NotionMediaEntry] = []
    analyzed_count = 0

    for ref in references:
        download_url = ref.download_url
        if ref.is_notion_attachment and download_url is None:
            if notion_token and ref.attachment_block_id:
                try:
                    download_url = resolve_attachment_url(ref.attachment_block_id, notion_token)
                except Exception as exc:
                    entries.append(NotionMediaEntry(
                        source_url=ref.source_url,
                        media_type=ref.media_type,
                        caption=ref.caption,
                        is_notion_attachment=True,
                        download_url=None,
                        analysis=None,
                        error=f"Failed to resolve Notion attachment URL: {exc}",
                    ))
                    continue
            else:
                entries.append(NotionMediaEntry(
                    source_url=ref.source_url,
                    media_type=ref.media_type,
                    caption=ref.caption,
                    is_notion_attachment=True,
                    download_url=None,
                    analysis=None,
                    error="NOTION_TOKEN env var is required to download Notion attachment files.",
                ))
                continue

        if download_url is None:
            entries.append(NotionMediaEntry(
                source_url=ref.source_url,
                media_type=ref.media_type,
                caption=ref.caption,
                is_notion_attachment=ref.is_notion_attachment,
                download_url=None,
                analysis=None,
                error="No downloadable URL available for this media.",
            ))
            continue

        try:
            entry = _analyze_and_build_entry(
                download_url=download_url,
                source_url=ref.source_url,
                media_type=ref.media_type,
                caption=ref.caption,
                is_notion_attachment=ref.is_notion_attachment,
                filename_hint=ref.attachment_filename,
                question=question,
                model=model,
            )
            entries.append(entry)
            analyzed_count += 1
        except Exception as exc:
            entries.append(NotionMediaEntry(
                source_url=ref.source_url,
                media_type=ref.media_type,
                caption=ref.caption,
                is_notion_attachment=ref.is_notion_attachment,
                download_url=download_url,
                analysis=None,
                error=f"Failed to download or analyze media: {exc}",
            ))

    return NotionPageMediaAnalysis(
        page_title=page_title,
        page_url=page_url,
        model=model,
        question=question,
        media_found=len(references),
        media_analyzed=analyzed_count,
        entries=entries,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

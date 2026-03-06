import mimetypes
import os
from enum import StrEnum
from pathlib import Path

from google import genai
from google.genai import types
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from multimodal_reader_mcp.uploads import get_or_upload_media_reference


DEFAULT_MODEL = "gemini-2.5-flash"


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
    model: str = DEFAULT_MODEL,
) -> MediaAnalysisResult:
    """Read a local audio or video file and return structured analysis."""
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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

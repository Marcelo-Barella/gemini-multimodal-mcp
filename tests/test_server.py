import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from multimodal_reader_mcp.server import (
    ConfidenceLevel,
    GeneratedMediaAnalysis,
    _build_prompt,
    _detect_mime_type,
    _require_api_key,
    _resolve_file_path,
    read_media,
)


class TestServer(unittest.TestCase):
    def test_require_api_key_returns_configured_value(self) -> None:
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}, clear=True):
            self.assertEqual(_require_api_key(), "test-key")

    def test_require_api_key_raises_when_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(EnvironmentError):
                _require_api_key()

    def test_resolve_file_path_returns_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "sample.mp4"
            file_path.write_bytes(b"media")

            resolved_path = _resolve_file_path(str(file_path))

            self.assertEqual(resolved_path, file_path.resolve())

    def test_resolve_file_path_rejects_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ValueError):
                _resolve_file_path(tmp_dir)

    def test_detect_mime_type_rejects_unknown_extension(self) -> None:
        unknown_file = Path("/tmp/media.unknownext")

        with self.assertRaises(ValueError):
            _detect_mime_type(unknown_file)

    def test_build_prompt_without_question_uses_general_reading(self) -> None:
        prompt = _build_prompt(file_name="sample.mp4", question=None)

        self.assertIn("File name: sample.mp4", prompt)
        self.assertIn("No user question was provided.", prompt)
        self.assertIn("General reading focus:", prompt)

    def test_build_prompt_with_question_includes_user_focus(self) -> None:
        prompt = _build_prompt(file_name="sample.mp4", question="What error appears?")

        self.assertIn("User question: What error appears?", prompt)
        self.assertNotIn("No user question was provided.", prompt)

    def test_read_media_returns_structured_analysis_result(self) -> None:
        generated_analysis = GeneratedMediaAnalysis(
            summary="Short summary",
            timeline=["00:00 opened app"],
            transcript=["hello world"],
            key_observations=["A settings screen is visible."],
            notable_signals=["A warning banner appears."],
            relevant_clues=["The warning matches the user's question."],
            open_questions=["The root cause is not visible."],
            confidence=ConfidenceLevel.MEDIUM,
        )

        with (
            patch(
                "multimodal_reader_mcp.server._resolve_file_path",
                return_value=Path("/tmp/sample.mp4"),
            ),
            patch(
                "multimodal_reader_mcp.server._detect_mime_type",
                return_value="video/mp4",
            ),
            patch(
                "multimodal_reader_mcp.server._analyze_media",
                return_value=generated_analysis,
            ),
        ):
            result = read_media(
                file_path="/tmp/sample.mp4",
                question="What warning is shown?",
            )

        self.assertEqual(result.file_path, "/tmp/sample.mp4")
        self.assertEqual(result.file_name, "sample.mp4")
        self.assertEqual(result.mime_type, "video/mp4")
        self.assertEqual(result.model, "gemini-2.5-flash")
        self.assertEqual(result.summary, generated_analysis.summary)
        self.assertEqual(result.relevant_clues, generated_analysis.relevant_clues)
        self.assertEqual(result.confidence, ConfidenceLevel.MEDIUM)


if __name__ == "__main__":
    unittest.main()

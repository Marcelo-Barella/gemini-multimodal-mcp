import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from multimodal_reader_mcp.downloads import DownloadedMedia
from multimodal_reader_mcp.server import (
    ConfidenceLevel,
    GeneratedMediaAnalysis,
    _build_prompt,
    _detect_mime_type,
    _require_api_key,
    _resolve_file_path,
    read_media,
    read_notion_page_media,
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


SAMPLE_ANALYSIS = GeneratedMediaAnalysis(
    summary="Video shows a mobile app screen.",
    timeline=["00:00 app opens"],
    transcript=["sending photos"],
    key_observations=["Upload button is visible."],
    notable_signals=["Error toast appears."],
    relevant_clues=["The error relates to photo upload."],
    open_questions=["Root cause unclear."],
    confidence=ConfidenceLevel.MEDIUM,
)


class TestReadNotionPageMedia(unittest.TestCase):
    def test_with_direct_url_video(self) -> None:
        markdown = '<video src="https://example.com/v.mp4">Demo</video>'

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(b"fake")
            tmp_path = Path(tmp.name)

        with (
            patch(
                "multimodal_reader_mcp.server.download_to_tempfile",
                return_value=DownloadedMedia(file_path=tmp_path, file_name="v.mp4", mime_type="video/mp4"),
            ),
            patch(
                "multimodal_reader_mcp.server._analyze_media",
                return_value=SAMPLE_ANALYSIS,
            ),
        ):
            result = read_notion_page_media(
                notion_markdown=markdown,
                question="What happens?",
                page_title="Test Page",
                page_url="https://notion.so/test",
            )

        self.assertFalse(tmp_path.exists())
        self.assertEqual(result.page_title, "Test Page")
        self.assertEqual(result.page_url, "https://notion.so/test")
        self.assertEqual(result.media_found, 1)
        self.assertEqual(result.media_analyzed, 1)
        self.assertEqual(result.question, "What happens?")
        self.assertEqual(len(result.entries), 1)
        entry = result.entries[0]
        self.assertEqual(entry.media_type, "video")
        self.assertEqual(entry.caption, "Demo")
        self.assertFalse(entry.is_notion_attachment)
        self.assertEqual(entry.download_url, "https://example.com/v.mp4")
        self.assertIsNotNone(entry.analysis)
        self.assertIsNone(entry.error)
        self.assertEqual(entry.analysis.summary, SAMPLE_ANALYSIS.summary)

    def test_with_attachment_and_token(self) -> None:
        attachment_src = (
            "file://%7B%22source%22%3A%22attachment%3Aabc%3Avideo.mp4%22"
            "%2C%22permissionRecord%22%3A%7B%22table%22%3A%22block%22"
            "%2C%22id%22%3A%22block-1%22%2C%22spaceId%22%3A%22space-1%22%7D%7D"
        )
        markdown = f'<video src="{attachment_src}"></video>'

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(b"fake")
            tmp_path = Path(tmp.name)

        with (
            patch.dict(os.environ, {"NOTION_TOKEN": "ntn_test"}),
            patch(
                "multimodal_reader_mcp.server.resolve_attachment_url",
                return_value="https://s3.amazonaws.com/signed-video.mp4",
            ) as mock_resolve,
            patch(
                "multimodal_reader_mcp.server.download_to_tempfile",
                return_value=DownloadedMedia(file_path=tmp_path, file_name="video.mp4", mime_type="video/mp4"),
            ),
            patch(
                "multimodal_reader_mcp.server._analyze_media",
                return_value=SAMPLE_ANALYSIS,
            ),
        ):
            result = read_notion_page_media(notion_markdown=markdown)

        self.assertFalse(tmp_path.exists())
        self.assertEqual(result.media_found, 1)
        self.assertEqual(result.media_analyzed, 1)
        entry = result.entries[0]
        self.assertTrue(entry.is_notion_attachment)
        self.assertEqual(entry.download_url, "https://s3.amazonaws.com/signed-video.mp4")
        self.assertIsNotNone(entry.analysis)
        self.assertIsNone(entry.error)
        mock_resolve.assert_called_once_with("block-1", "ntn_test")

    def test_with_attachment_no_token(self) -> None:
        attachment_src = (
            "file://%7B%22source%22%3A%22attachment%3Aabc%3Avideo.mp4%22"
            "%2C%22permissionRecord%22%3A%7B%22table%22%3A%22block%22"
            "%2C%22id%22%3A%22block-1%22%2C%22spaceId%22%3A%22space-1%22%7D%7D"
        )
        markdown = f'<video src="{attachment_src}"></video>'

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NOTION_TOKEN", None)
            result = read_notion_page_media(notion_markdown=markdown)

        self.assertEqual(result.media_found, 1)
        self.assertEqual(result.media_analyzed, 0)
        entry = result.entries[0]
        self.assertTrue(entry.is_notion_attachment)
        self.assertIsNone(entry.download_url)
        self.assertIsNone(entry.analysis)
        self.assertIn("NOTION_TOKEN", entry.error)

    def test_no_media_found(self) -> None:
        markdown = "# Just a heading\n\nSome text content."

        result = read_notion_page_media(notion_markdown=markdown)

        self.assertEqual(result.media_found, 0)
        self.assertEqual(result.media_analyzed, 0)
        self.assertEqual(result.entries, [])

    def test_download_error_does_not_block_others(self) -> None:
        markdown = (
            '<video src="https://example.com/bad.mp4">Bad</video>\n'
            '<video src="https://example.com/good.mp4">Good</video>'
        )

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(b"fake")
            tmp_path = Path(tmp.name)

        def side_effect_download(url: str, filename_hint: str | None = None) -> DownloadedMedia:
            if "bad" in url:
                raise ConnectionError("Download failed")
            return DownloadedMedia(file_path=tmp_path, file_name="good.mp4", mime_type="video/mp4")

        with (
            patch(
                "multimodal_reader_mcp.server.download_to_tempfile",
                side_effect=side_effect_download,
            ),
            patch(
                "multimodal_reader_mcp.server._analyze_media",
                return_value=SAMPLE_ANALYSIS,
            ),
        ):
            result = read_notion_page_media(notion_markdown=markdown)

        self.assertEqual(result.media_found, 2)
        self.assertEqual(result.media_analyzed, 1)
        bad_entry = result.entries[0]
        self.assertIsNone(bad_entry.analysis)
        self.assertIn("Download failed", bad_entry.error)
        good_entry = result.entries[1]
        self.assertIsNotNone(good_entry.analysis)
        self.assertIsNone(good_entry.error)


if __name__ == "__main__":
    unittest.main()

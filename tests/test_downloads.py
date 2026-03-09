import unittest
from unittest.mock import MagicMock, patch

import httpx

from multimodal_reader_mcp.downloads import (
    _detect_mime_type,
    _extract_extension_from_url,
    download_to_tempfile,
)


class TestExtractExtensionFromUrl(unittest.TestCase):
    def test_extracts_mp4_extension(self) -> None:
        self.assertEqual(_extract_extension_from_url("https://example.com/video.mp4"), ".mp4")

    def test_extracts_extension_with_query_params(self) -> None:
        self.assertEqual(
            _extract_extension_from_url("https://s3.amazonaws.com/file.mp3?X-Amz-Algorithm=AWS4"),
            ".mp3",
        )

    def test_returns_empty_for_no_extension(self) -> None:
        self.assertEqual(_extract_extension_from_url("https://example.com/media"), "")


class TestDetectMimeType(unittest.TestCase):
    def test_uses_content_type_header(self) -> None:
        self.assertEqual(_detect_mime_type("video/mp4", "https://example.com/x", None), "video/mp4")

    def test_strips_charset_from_content_type(self) -> None:
        self.assertEqual(
            _detect_mime_type("video/mp4; charset=utf-8", "https://example.com/x", None),
            "video/mp4",
        )

    def test_ignores_octet_stream_content_type(self) -> None:
        result = _detect_mime_type("application/octet-stream", "https://example.com/v.mp4", None)
        self.assertEqual(result, "video/mp4")

    def test_falls_back_to_filename_hint(self) -> None:
        result = _detect_mime_type(None, "https://example.com/media", "recording.wav")
        self.assertEqual(result, "audio/x-wav")

    def test_falls_back_to_url_extension(self) -> None:
        result = _detect_mime_type(None, "https://example.com/video.webm", None)
        self.assertEqual(result, "video/webm")

    def test_returns_octet_stream_as_last_resort(self) -> None:
        result = _detect_mime_type(None, "https://example.com/blob", None)
        self.assertEqual(result, "application/octet-stream")


class TestDownloadToTempfile(unittest.TestCase):
    def test_success_with_filename_hint(self) -> None:
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "video/mp4"}
        mock_response.iter_bytes.return_value = [b"fake video data"]
        mock_response.raise_for_status = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("multimodal_reader_mcp.downloads.httpx.Client", return_value=mock_client):
            result = download_to_tempfile("https://example.com/v", filename_hint="clip.mp4")

        try:
            self.assertTrue(result.file_path.exists())
            self.assertEqual(result.file_path.read_bytes(), b"fake video data")
            self.assertEqual(result.file_name, "clip.mp4")
            self.assertEqual(result.mime_type, "video/mp4")
            self.assertTrue(str(result.file_path).endswith(".mp4"))
        finally:
            result.file_path.unlink(missing_ok=True)

    def test_success_without_filename_hint(self) -> None:
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "audio/mpeg"}
        mock_response.iter_bytes.return_value = [b"audio"]
        mock_response.raise_for_status = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("multimodal_reader_mcp.downloads.httpx.Client", return_value=mock_client):
            result = download_to_tempfile("https://example.com/audio.mp3")

        try:
            self.assertTrue(result.file_path.exists())
            self.assertEqual(result.mime_type, "audio/mpeg")
            self.assertTrue(str(result.file_path).endswith(".mp3"))
        finally:
            result.file_path.unlink(missing_ok=True)

    def test_network_error_raises(self) -> None:
        mock_client = MagicMock()
        mock_client.stream.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("multimodal_reader_mcp.downloads.httpx.Client", return_value=mock_client):
            with self.assertRaises(httpx.ConnectError):
                download_to_tempfile("https://example.com/v.mp4")

    def test_http_error_raises(self) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Forbidden",
            request=MagicMock(),
            response=MagicMock(status_code=403),
        )
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("multimodal_reader_mcp.downloads.httpx.Client", return_value=mock_client):
            with self.assertRaises(httpx.HTTPStatusError):
                download_to_tempfile("https://example.com/v.mp4")


if __name__ == "__main__":
    unittest.main()

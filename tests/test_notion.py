import unittest
from unittest.mock import MagicMock, patch

import httpx

from multimodal_reader_mcp.notion import (
    extract_media_references,
    resolve_attachment_url,
)


REAL_ATTACHMENT_VIDEO_TAG = (
    '<video src="file://%7B%22source%22%3A%22attachment%3A4da40eff-b64b-4d2f-bcef-b20d9ae0ddd3'
    "%3AWhatsApp_Video_2026-02-25_at_15.36.45.mp4%22%2C%22permissionRecord%22%3A%7B%22table%22"
    "%3A%22block%22%2C%22id%22%3A%223128168d-f9f0-803b-b007-f0e58edc2dda%22%2C%22spaceId%22%3A"
    '%2236b8092f-f70c-4358-96b2-512c9d570451%22%7D%7D"></video>'
)


class TestExtractMediaReferences(unittest.TestCase):
    def test_extract_video_with_direct_url(self) -> None:
        markdown = '<video src="https://example.com/video.mp4"></video>'

        refs = extract_media_references(markdown)

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].media_type, "video")
        self.assertEqual(refs[0].download_url, "https://example.com/video.mp4")
        self.assertFalse(refs[0].is_notion_attachment)
        self.assertEqual(refs[0].caption, "")

    def test_extract_video_with_attachment_url(self) -> None:
        markdown = REAL_ATTACHMENT_VIDEO_TAG

        refs = extract_media_references(markdown)

        self.assertEqual(len(refs), 1)
        ref = refs[0]
        self.assertEqual(ref.media_type, "video")
        self.assertTrue(ref.is_notion_attachment)
        self.assertEqual(ref.attachment_block_id, "3128168d-f9f0-803b-b007-f0e58edc2dda")
        self.assertEqual(ref.attachment_filename, "WhatsApp_Video_2026-02-25_at_15.36.45.mp4")
        self.assertIsNone(ref.download_url)

    def test_extract_audio_with_direct_url(self) -> None:
        markdown = '<audio src="https://example.com/audio.mp3">Meeting recording</audio>'

        refs = extract_media_references(markdown)

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].media_type, "audio")
        self.assertEqual(refs[0].download_url, "https://example.com/audio.mp3")
        self.assertEqual(refs[0].caption, "Meeting recording")
        self.assertFalse(refs[0].is_notion_attachment)

    def test_extract_multiple_media(self) -> None:
        markdown = (
            "Some text\n"
            '<video src="https://example.com/v1.mp4">First</video>\n'
            "Middle text\n"
            '<audio src="https://example.com/a1.mp3">Audio</audio>\n'
            '<video src="https://example.com/v2.mp4">Second</video>\n'
        )

        refs = extract_media_references(markdown)

        self.assertEqual(len(refs), 3)
        self.assertEqual(refs[0].media_type, "video")
        self.assertEqual(refs[0].caption, "First")
        self.assertEqual(refs[1].media_type, "audio")
        self.assertEqual(refs[1].caption, "Audio")
        self.assertEqual(refs[2].media_type, "video")
        self.assertEqual(refs[2].caption, "Second")

    def test_extract_no_media(self) -> None:
        markdown = "# Hello\n\nJust some text with no media blocks.\n"

        refs = extract_media_references(markdown)

        self.assertEqual(refs, [])

    def test_extract_video_with_caption(self) -> None:
        markdown = '<video src="https://example.com/v.mp4">Screen recording of the bug</video>'

        refs = extract_media_references(markdown)

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].caption, "Screen recording of the bug")

    def test_extract_ignores_images(self) -> None:
        markdown = (
            "![screenshot](https://prod-files-secure.s3.us-west-2.amazonaws.com/img.png)\n"
            '<video src="https://example.com/v.mp4"></video>'
        )

        refs = extract_media_references(markdown)

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].media_type, "video")

    def test_extract_real_test_page_markdown(self) -> None:
        markdown = (
            '::: callout\n'
            '\t## <span color="gray">1. Registro do Analista</span> {toggle="true"}\n'
            '\t\t<span color="gray">*VIDEOS OU LINKS*</span>\n'
            "\t\t>\n"
            f"\t\t{REAL_ATTACHMENT_VIDEO_TAG}\n"
            "\t\t<empty-block/>\n"
            ":::\n"
        )

        refs = extract_media_references(markdown)

        self.assertEqual(len(refs), 1)
        ref = refs[0]
        self.assertTrue(ref.is_notion_attachment)
        self.assertEqual(ref.attachment_block_id, "3128168d-f9f0-803b-b007-f0e58edc2dda")

    def test_extract_video_with_color_attribute(self) -> None:
        markdown = '<video src="https://example.com/v.mp4" color="blue">Colored</video>'

        refs = extract_media_references(markdown)

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].download_url, "https://example.com/v.mp4")
        self.assertEqual(refs[0].caption, "Colored")

    def test_extract_audio_attachment(self) -> None:
        attachment_src = (
            "file://%7B%22source%22%3A%22attachment%3Aabc123%3Avoice.wav%22"
            "%2C%22permissionRecord%22%3A%7B%22table%22%3A%22block%22%2C%22id%22"
            "%3A%22block-id-123%22%2C%22spaceId%22%3A%22space-123%22%7D%7D"
        )
        markdown = f'<audio src="{attachment_src}">Voice memo</audio>'

        refs = extract_media_references(markdown)

        self.assertEqual(len(refs), 1)
        ref = refs[0]
        self.assertEqual(ref.media_type, "audio")
        self.assertTrue(ref.is_notion_attachment)
        self.assertEqual(ref.attachment_block_id, "block-id-123")
        self.assertEqual(ref.attachment_filename, "voice.wav")
        self.assertEqual(ref.caption, "Voice memo")


class TestResolveAttachmentUrl(unittest.TestCase):
    def test_resolve_video_block(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "type": "video",
            "video": {
                "type": "file",
                "file": {
                    "url": "https://prod-files-secure.s3.us-west-2.amazonaws.com/signed-video.mp4",
                    "expiry_time": "2026-03-09T15:00:00.000Z",
                },
            },
        }
        mock_response.raise_for_status = MagicMock()

        with patch("multimodal_reader_mcp.notion.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = resolve_attachment_url("block-123", "ntn_test_token")

        self.assertEqual(result, "https://prod-files-secure.s3.us-west-2.amazonaws.com/signed-video.mp4")
        mock_client.get.assert_called_once_with(
            "https://api.notion.com/v1/blocks/block-123",
            headers={
                "Authorization": "Bearer ntn_test_token",
                "Notion-Version": "2022-06-28",
            },
        )

    def test_resolve_audio_block(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "type": "audio",
            "audio": {
                "type": "file",
                "file": {
                    "url": "https://prod-files-secure.s3.us-west-2.amazonaws.com/signed-audio.mp3",
                    "expiry_time": "2026-03-09T15:00:00.000Z",
                },
            },
        }
        mock_response.raise_for_status = MagicMock()

        with patch("multimodal_reader_mcp.notion.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = resolve_attachment_url("block-456", "ntn_test_token")

        self.assertEqual(result, "https://prod-files-secure.s3.us-west-2.amazonaws.com/signed-audio.mp3")

    def test_resolve_external_video(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "type": "video",
            "video": {
                "type": "external",
                "external": {
                    "url": "https://www.youtube.com/watch?v=abc123",
                },
            },
        }
        mock_response.raise_for_status = MagicMock()

        with patch("multimodal_reader_mcp.notion.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = resolve_attachment_url("block-789", "ntn_test_token")

        self.assertEqual(result, "https://www.youtube.com/watch?v=abc123")

    def test_resolve_api_error_raises(self) -> None:
        with patch("multimodal_reader_mcp.notion.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Not Found",
                request=MagicMock(),
                response=MagicMock(status_code=404),
            )
            mock_client_cls.return_value = mock_client

            with self.assertRaises(httpx.HTTPStatusError):
                resolve_attachment_url("nonexistent", "ntn_test_token")

    def test_resolve_non_media_block_raises(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "type": "paragraph",
            "paragraph": {"rich_text": []},
        }
        mock_response.raise_for_status = MagicMock()

        with patch("multimodal_reader_mcp.notion.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            with self.assertRaises(ValueError):
                resolve_attachment_url("paragraph-block", "ntn_test_token")


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from google.genai import types
from google.genai.errors import ClientError

from multimodal_reader_mcp.uploads import (
    FILE_READY_POLL_INTERVAL_SECONDS,
    FILE_READY_TIMEOUT_SECONDS,
    UPLOAD_LIFETIME,
    UploadedMediaReference,
    _build_uploaded_reference,
    _find_reusable_upload,
    _normalize_datetime,
    _wait_for_active_file,
    get_or_upload_media_reference,
)


class TestUploads(unittest.TestCase):
    def test_normalize_datetime_adds_utc_to_naive_values(self) -> None:
        naive_value = datetime(2026, 1, 2, 3, 4, 5)

        normalized = _normalize_datetime(naive_value)

        self.assertEqual(normalized.tzinfo, timezone.utc)
        self.assertEqual(normalized.isoformat(), "2026-01-02T03:04:05+00:00")

    def test_build_uploaded_reference_uses_default_lifetime_when_missing_expiration(self) -> None:
        remote_file = types.File(name="files/123", uri="uri://media", state=types.FileState.ACTIVE)
        fixed_now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

        with patch("multimodal_reader_mcp.uploads._utc_now", return_value=fixed_now):
            reference = _build_uploaded_reference(remote_file, reused=False)

        self.assertEqual(reference.name, "files/123")
        self.assertEqual(reference.uri, "uri://media")
        self.assertEqual(reference.expires_at, fixed_now + UPLOAD_LIFETIME)
        self.assertFalse(reference.reused)

    def test_wait_for_active_file_polls_until_processing_finishes(self) -> None:
        processing_file = types.File(
            name="files/123",
            uri="uri://media",
            state=types.FileState.PROCESSING,
        )
        active_file = types.File(
            name="files/123",
            uri="uri://media",
            state=types.FileState.ACTIVE,
        )
        client = MagicMock()
        client.files.get.side_effect = [processing_file, active_file]

        with patch("multimodal_reader_mcp.uploads.time.sleep") as sleep:
            result = _wait_for_active_file(client, "files/123")

        self.assertEqual(result, active_file)
        sleep.assert_called_once_with(FILE_READY_POLL_INTERVAL_SECONDS)

    def test_wait_for_active_file_raises_timeout(self) -> None:
        client = MagicMock()
        client.files.get.return_value = types.File(
            name="files/123",
            uri="uri://media",
            state=types.FileState.PROCESSING,
        )

        with (
            patch(
                "multimodal_reader_mcp.uploads.time.monotonic",
                side_effect=[0.0, FILE_READY_TIMEOUT_SECONDS + 1.0],
            ),
            patch("multimodal_reader_mcp.uploads.time.sleep") as sleep,
        ):
            with self.assertRaises(TimeoutError):
                _wait_for_active_file(client, "files/123")

        sleep.assert_not_called()

    def test_find_reusable_upload_returns_none_for_missing_remote_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "sample.mp4"
            file_path.write_bytes(b"media")
            client = MagicMock()
            client.files.get.side_effect = ClientError(404, {})

            result = _find_reusable_upload(client, file_path)

        self.assertIsNone(result)

    def test_get_or_upload_media_reference_reuses_existing_upload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "sample.mp4"
            file_path.write_bytes(b"media")
            reusable_reference = UploadedMediaReference(
                name="files/123",
                uri="uri://media",
                expires_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
                reused=True,
            )
            client = MagicMock()

            with patch(
                "multimodal_reader_mcp.uploads._find_reusable_upload",
                return_value=reusable_reference,
            ):
                reference, part = get_or_upload_media_reference(
                    client,
                    file_path,
                    "video/mp4",
                )

        self.assertEqual(reference, reusable_reference)
        client.files.upload.assert_not_called()
        self.assertEqual(part.file_data.file_uri, "uri://media")
        self.assertEqual(part.file_data.mime_type, "video/mp4")

    def test_get_or_upload_media_reference_uploads_when_reuse_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "sample.mp4"
            file_path.write_bytes(b"media")
            active_file = types.File(
                name="files/456",
                uri="uri://uploaded",
                state=types.FileState.ACTIVE,
                expiration_time=datetime(2026, 1, 3, tzinfo=timezone.utc),
            )
            client = MagicMock()
            client.files.upload.return_value = types.File(
                name="files/456",
                uri="uri://uploaded",
                state=types.FileState.PROCESSING,
            )

            with (
                patch(
                    "multimodal_reader_mcp.uploads._find_reusable_upload",
                    return_value=None,
                ),
                patch(
                    "multimodal_reader_mcp.uploads._wait_for_active_file",
                    return_value=active_file,
                ),
            ):
                reference, part = get_or_upload_media_reference(
                    client,
                    file_path,
                    "video/mp4",
                )

        upload_call = client.files.upload.call_args
        self.assertEqual(upload_call.kwargs["file"], str(file_path))
        self.assertEqual(upload_call.kwargs["config"].mime_type, "video/mp4")
        self.assertEqual(upload_call.kwargs["config"].display_name, "sample.mp4")
        self.assertEqual(reference.name, "files/456")
        self.assertFalse(reference.reused)
        self.assertEqual(part.file_data.file_uri, "uri://uploaded")


if __name__ == "__main__":
    unittest.main()

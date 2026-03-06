import hashlib
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.genai.errors import ClientError
from google.genai import types, Client
from pydantic import BaseModel


UPLOAD_LIFETIME = timedelta(hours=40)
FILE_READY_TIMEOUT_SECONDS = 120
FILE_READY_POLL_INTERVAL_SECONDS = 2


class UploadedMediaReference(BaseModel):
    name: str
    uri: str
    expires_at: datetime
    reused: bool


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _build_reusable_part(upload: UploadedMediaReference, mime_type: str) -> types.Part:
    return types.Part.from_uri(file_uri=upload.uri, mime_type=mime_type)


def _local_file_sha256_hex(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _gemini_file_name(file_path: Path) -> str:
    return f"files/{_local_file_sha256_hex(file_path)[:40]}"


def _build_uploaded_reference(remote_file: types.File, *, reused: bool) -> UploadedMediaReference:
    now = _utc_now()
    if remote_file.name is None or remote_file.uri is None:
        raise RuntimeError("Gemini file did not return a reusable file reference.")
    if remote_file.expiration_time is None:
        expires_at = now + UPLOAD_LIFETIME
    else:
        expires_at = _normalize_datetime(remote_file.expiration_time)
    return UploadedMediaReference(
        name=remote_file.name,
        uri=remote_file.uri,
        expires_at=expires_at,
        reused=reused,
    )


def _wait_for_active_file(client: Client, file_name: str) -> types.File:
    deadline = time.monotonic() + FILE_READY_TIMEOUT_SECONDS
    while True:
        remote_file = client.files.get(name=file_name)
        if remote_file.state == types.FileState.ACTIVE:
            return remote_file
        if remote_file.state == types.FileState.FAILED:
            if remote_file.error is not None and remote_file.error.message is not None:
                raise RuntimeError(f"Gemini file processing failed: {remote_file.error.message}")
            raise RuntimeError("Gemini file processing failed.")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Gemini file did not become ACTIVE within {FILE_READY_TIMEOUT_SECONDS} seconds.")
        time.sleep(FILE_READY_POLL_INTERVAL_SECONDS)


def _find_reusable_upload(client: Client, file_path: Path) -> UploadedMediaReference | None:
    now = _utc_now()
    try:
        remote_file = client.files.get(name=_gemini_file_name(file_path))
    except ClientError as error:
        if error.code in {403, 404}:
            return None
        raise
    if remote_file.expiration_time is not None and _normalize_datetime(remote_file.expiration_time) <= now:
        return None
    if remote_file.name is None:
        return None
    active_file = _wait_for_active_file(client, remote_file.name)
    return _build_uploaded_reference(active_file, reused=True)


def get_or_upload_media_reference(client: Client, file_path: Path, mime_type: str) -> tuple[UploadedMediaReference, types.Part]:
    reusable_upload = _find_reusable_upload(client, file_path)
    if reusable_upload is not None:
        return reusable_upload, _build_reusable_part(reusable_upload, mime_type)

    uploaded_file = client.files.upload(
        file=str(file_path),
        config=types.UploadFileConfig(
            name=_gemini_file_name(file_path),
            mime_type=mime_type,
            display_name=file_path.name,
        ),
    )
    if uploaded_file.name is None:
        raise RuntimeError("Gemini file upload did not return a reusable file reference.")
    active_file = _wait_for_active_file(client, uploaded_file.name)
    uploaded_reference = _build_uploaded_reference(active_file, reused=False)
    return uploaded_reference, _build_reusable_part(uploaded_reference, mime_type)

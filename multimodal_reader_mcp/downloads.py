import mimetypes
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel


DOWNLOAD_TIMEOUT_SECONDS = 300
CHUNK_SIZE = 1024 * 1024


class DownloadedMedia(BaseModel):
    file_path: Path
    file_name: str
    mime_type: str


def _extract_extension_from_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path
    if "." in path.split("/")[-1]:
        return "." + path.split("/")[-1].rsplit(".", 1)[-1]
    return ""


def _detect_mime_type(content_type: str | None, url: str, filename_hint: str | None) -> str:
    if content_type:
        base_type = content_type.split(";")[0].strip()
        if base_type and base_type != "application/octet-stream":
            return base_type
    if filename_hint:
        guessed, _ = mimetypes.guess_type(filename_hint)
        if guessed:
            return guessed
    guessed, _ = mimetypes.guess_type(urlparse(url).path)
    if guessed:
        return guessed
    return "application/octet-stream"


def download_to_tempfile(url: str, filename_hint: str | None = None) -> DownloadedMedia:
    extension = ""
    if filename_hint and "." in filename_hint:
        extension = "." + filename_hint.rsplit(".", 1)[-1]
    else:
        extension = _extract_extension_from_url(url)

    with httpx.Client(timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type")
            mime_type = _detect_mime_type(content_type, url, filename_hint)

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=extension)
            try:
                for chunk in response.iter_bytes(chunk_size=CHUNK_SIZE):
                    tmp.write(chunk)
            except BaseException:
                tmp.close()
                Path(tmp.name).unlink(missing_ok=True)
                raise
            tmp.close()

    file_path = Path(tmp.name)
    file_name = filename_hint or file_path.name
    return DownloadedMedia(file_path=file_path, file_name=file_name, mime_type=mime_type)

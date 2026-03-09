import json
import re
from typing import Literal
from urllib.parse import unquote

import httpx
from pydantic import BaseModel


NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_API_VERSION = "2022-06-28"

_MEDIA_TAG_PATTERN = re.compile(
    r"<(?P<tag>video|audio)\s+src=\"(?P<src>[^\"]*)\""
    r"(?:\s+[^>]*)?"
    r">(?P<caption>[^<]*)</(?P=tag)>",
)

_ATTACHMENT_SOURCE_PATTERN = re.compile(
    r"^attachment:(?P<attachment_id>[^:]+):(?P<filename>.+)$",
)


class NotionMediaReference(BaseModel):
    media_type: Literal["video", "audio"]
    source_url: str
    caption: str
    is_notion_attachment: bool
    attachment_block_id: str | None = None
    attachment_filename: str | None = None
    download_url: str | None = None


def _parse_attachment_url(decoded_url: str) -> tuple[str | None, str | None]:
    prefix = "file://"
    if not decoded_url.startswith(prefix):
        return None, None
    raw_json = decoded_url[len(prefix):]
    try:
        payload = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return None, None
    block_id: str | None = None
    filename: str | None = None
    permission_record = payload.get("permissionRecord")
    if isinstance(permission_record, dict):
        block_id = permission_record.get("id")
    source = payload.get("source")
    if isinstance(source, str):
        match = _ATTACHMENT_SOURCE_PATTERN.match(source)
        if match:
            filename = match.group("filename")
    return block_id, filename


def extract_media_references(markdown: str) -> list[NotionMediaReference]:
    references: list[NotionMediaReference] = []
    for match in _MEDIA_TAG_PATTERN.finditer(markdown):
        tag = match.group("tag")
        raw_src = match.group("src")
        caption = match.group("caption").strip()
        decoded_src = unquote(raw_src)
        if decoded_src.startswith("file://"):
            block_id, filename = _parse_attachment_url(decoded_src)
            references.append(
                NotionMediaReference(
                    media_type=tag,
                    source_url=raw_src,
                    caption=caption,
                    is_notion_attachment=True,
                    attachment_block_id=block_id,
                    attachment_filename=filename,
                    download_url=None,
                )
            )
        elif decoded_src.startswith("http://") or decoded_src.startswith("https://"):
            references.append(
                NotionMediaReference(
                    media_type=tag,
                    source_url=raw_src,
                    caption=caption,
                    is_notion_attachment=False,
                    download_url=decoded_src,
                )
            )
    return references


def resolve_attachment_url(block_id: str, notion_token: str) -> str:
    url = f"{NOTION_API_BASE}/blocks/{block_id}"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": NOTION_API_VERSION,
    }
    with httpx.Client() as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
    data = response.json()
    block_type = data.get("type")
    if block_type not in ("video", "audio"):
        raise ValueError(f"Block {block_id} is not a media block (type={block_type}).")
    media_obj = data.get(block_type, {})
    file_obj = media_obj.get("file") or media_obj.get("external")
    if file_obj is None:
        raise ValueError(f"Block {block_id} has no file or external reference.")
    download_url = file_obj.get("url")
    if not download_url:
        raise ValueError(f"Block {block_id} file object has no URL.")
    return download_url

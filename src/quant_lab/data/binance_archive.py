from __future__ import annotations

import hashlib
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from xml.etree import ElementTree

import httpx2

BUCKET: Final = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
DOWNLOAD: Final = "https://data.binance.vision"
NS: Final = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}


class ArchiveError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ArchiveEntry:
    key: str
    size: int
    modified: str


def archive_client() -> httpx2.Client:
    """Caller owns the returned public-data HTTP session."""
    transport = httpx2.HTTPTransport(
        http2=True,
        retries=3,
        limits=httpx2.Limits(
            max_connections=20, max_keepalive_connections=16, keepalive_expiry=30.0
        ),
        socket_options=[(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)],
    )
    return httpx2.Client(
        transport=transport,
        timeout=httpx2.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0),
        follow_redirects=True,
    )


def list_archives(client: httpx2.Client, prefix: str) -> tuple[ArchiveEntry, ...]:
    """Read every S3 page, rejecting pagination stalls."""
    marker = ""
    entries: list[ArchiveEntry] = []
    while True:
        response = client.get(BUCKET, params={"prefix": prefix, "marker": marker})
        _ = response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        page: list[ArchiveEntry] = []
        for item in root.findall("s:Contents", NS):
            key = item.findtext("s:Key", namespaces=NS)
            size = item.findtext("s:Size", namespaces=NS)
            modified = item.findtext("s:LastModified", namespaces=NS)
            if key is None or size is None or modified is None:
                raise ArchiveError("missing S3 object metadata")
            page.append(ArchiveEntry(key, int(size), modified))
        entries.extend(entry for entry in page if entry.key.endswith(".zip"))
        if root.findtext("s:IsTruncated", namespaces=NS) == "false":
            return tuple(entries)
        if not page or page[-1].key <= marker:
            raise ArchiveError("S3 pagination did not advance")
        marker = page[-1].key


def verified_download(client: httpx2.Client, entry: ArchiveEntry, root: Path) -> Path:
    """Cache exact archive bytes alongside Binance's SHA256 checksum."""
    path = root / Path(entry.key).name
    checksum_path = path.with_suffix(".zip.CHECKSUM")
    if not checksum_path.exists():
        response = client.get(f"{DOWNLOAD}/{entry.key}.CHECKSUM")
        _ = response.raise_for_status()
        _ = checksum_path.write_bytes(response.content)
    if not path.exists():
        response = client.get(f"{DOWNLOAD}/{entry.key}")
        _ = response.raise_for_status()
        _ = path.write_bytes(response.content)
    expected = checksum_path.read_text().split()[0]
    payload = path.read_bytes()
    if len(payload) != entry.size or hashlib.sha256(payload).hexdigest() != expected:
        raise ArchiveError(f"archive size/SHA256 mismatch: {entry.key}")
    return path

import hashlib
from pathlib import Path
from zipfile import ZipFile

import pytest

from quant_lab.data.binance_archive import (
    ArchiveEntry,
    ArchiveError,
    archive_client,
    verified_download,
)
from quant_lab.data.participation_data import read_archive


def test_corrupt_cached_zip_is_rejected_without_network(tmp_path: Path) -> None:
    entry = ArchiveEntry("data/test.zip", 3, "2026-09-11")
    _ = (tmp_path / "test.zip").write_bytes(b"bad")
    _ = (tmp_path / "test.zip.CHECKSUM").write_text(
        hashlib.sha256(b"yes").hexdigest() + " test.zip"
    )
    with archive_client() as client, pytest.raises(ArchiveError, match="SHA256"):
        _ = verified_download(client, entry, tmp_path)


def test_headerless_futures_csv_preserves_first_data_row(tmp_path: Path) -> None:
    path = tmp_path / "historical.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("historical.csv", "0,1,2,1,2,10,3599999,15,2,5,7,0\n")
    result = read_archive(path)
    assert result.height == 1
    assert result["open_time"][0] == 0
    assert result["count"][0] == 2

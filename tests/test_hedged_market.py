from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

import pytest

from quant_lab.data.binance_archive import ArchiveEntry, ArchiveError
from quant_lab.data.hedged_market import normalized_spot
from quant_lab.data.participation_data import SourceFile


@pytest.mark.parametrize(("year", "unit"), [(2024, 1000), (2025, 1_000_000)])
def test_spot_archive_timestamp_epoch_and_first_row_are_preserved(
    tmp_path: Path, year: int, unit: int
) -> None:
    timestamp = datetime(year, 1, 1, tzinfo=UTC)
    start = int(timestamp.timestamp()) * unit
    end = start + 3600 * unit - 1
    key = f"data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-{year}-01.zip"
    path = tmp_path / "source.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("source.csv", f"{start},100,101,99,100,2,{end},200,5,1,100,0\n")
    source = SourceFile("BTCUSDT", "spot", ArchiveEntry(key, 0, ""), path, "")
    frame = normalized_spot(source)
    assert frame.height == 1
    assert frame["timestamp"][0] == timestamp


def test_wrong_timestamp_unit_fails_instead_of_silent_alignment(tmp_path: Path) -> None:
    path = tmp_path / "source.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "source.csv", "1735689600000,100,101,99,100,2,1735693199999,200,5,1,100,0\n"
        )
    source = SourceFile("BTCUSDT", "spot", ArchiveEntry("BTCUSDT-1h-2025-01.zip", 0, ""), path, "")
    with pytest.raises(ArchiveError, match="timestamp-unit"):
        _ = normalized_spot(source)


def test_zero_trade_shortened_hour_stays_unavailable_without_rewriting_time(tmp_path: Path) -> None:
    path = tmp_path / "source.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("source.csv", "1679659200000,100,100,100,100,0,1679661581646,0,0,0,0,0\n")
    source = SourceFile("BTCUSDT", "spot", ArchiveEntry("BTCUSDT-1h-2023-03.zip", 0, ""), path, "")
    frame = normalized_spot(source)
    assert frame["spot_available"][0] is False
    assert frame["close_time"][0] == 1679661581646


def test_traded_partial_hour_inside_evaluation_still_fails(tmp_path: Path) -> None:
    path = tmp_path / "source.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "source.csv", "1679659200000,100,101,99,100,5,1679661581646,500,50,0,0,0\n"
        )
    source = SourceFile("BTCUSDT", "spot", ArchiveEntry("BTCUSDT-1h-2023-03.zip", 0, ""), path, "")
    with pytest.raises(ArchiveError, match="incomplete traded"):
        _ = normalized_spot(source)

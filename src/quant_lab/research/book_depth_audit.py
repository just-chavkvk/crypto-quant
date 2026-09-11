from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Final
from zipfile import ZipFile

import polars as pl
import typer

from quant_lab.data.binance_archive import (
    ArchiveEntry,
    ArchiveError,
    archive_client,
    list_archives,
    verified_download,
)
from quant_lab.data.book_depth_quality import audit_book_day

ROOT: Final = Path("artifacts/edge_search/order_book")
app = typer.Typer()


@app.command()
def main(
    root: Annotated[Path, typer.Option(exists=True, file_okay=False)] = ROOT,
    refresh_inventory: bool = False,
) -> None:
    first, cutoff = date(2023, 1, 1), date(2026, 9, 11)
    expected = [first + timedelta(days=i) for i in range((cutoff - first).days)]
    summaries: list[dict[str, str | int | float]] = []
    hourly_frames: list[pl.DataFrame] = []
    inventories: list[dict[str, str | int | float]] = []
    missing_rows: list[dict[str, str]] = []
    gate_failed = False
    for symbol in ("BTCUSDT", "ETHUSDT"):
        if refresh_inventory:
            with archive_client() as client:
                entries = list_archives(client, f"data/futures/um/daily/bookDepth/{symbol}/")
            pl.DataFrame([asdict(e) for e in entries]).write_json(root / f"{symbol}_inventory.json")
        inventory = pl.read_json(root / f"{symbol}_inventory.json")
        known = {date.fromisoformat(key[-14:-4]) for key in inventory["key"].to_list()}
        longest = run = 0
        for day in expected:
            missing = day not in known
            run = run + 1 if missing else 0
            longest = max(longest, run)
            if missing:
                missing_rows.append({"symbol": symbol, "day": day.isoformat()})
        gate_failed = gate_failed or longest > 1
        inventories.append(
            {
                "symbol": symbol,
                "first": min(known).isoformat(),
                "last": max(known).isoformat(),
                "expected_days": len(expected),
                "archive_days": len(known),
                "missing_days": len(set(expected) - known),
                "longest_missing_hours": longest * 24,
                "inventory_verdict": "REJECTED" if longest > 1 else "CONTENTS_AUDIT_REQUIRED",
            }
        )
        sample_dates = {d for d in expected if d.day == 1} | {
            date(2023, 12, 31),
            date(2024, 12, 31),
            date(2025, 12, 31),
            date(2026, 9, 10),
        }
        for day in sorted(sample_dates & known):
            path = root / f"{symbol}-bookDepth-{day.isoformat()}.zip"
            if not path.exists() or not path.with_suffix(".zip.CHECKSUM").exists():
                row = inventory.filter(pl.col("key").str.ends_with(path.name)).row(0)
                with archive_client() as client:
                    _ = verified_download(client, ArchiveEntry(*row), root)
            payload = path.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            if digest != path.with_suffix(".zip.CHECKSUM").read_text().split()[0]:
                raise ArchiveError(f"bookDepth sample checksum mismatch: {path}")
            with ZipFile(path) as archive:
                members = archive.namelist()
                if len(members) != 1:
                    raise ArchiveError(f"expected one CSV: {path}")
                csv = archive.read(members[0])
            hourly, quality = audit_book_day(csv, day)
            raw = pl.read_csv(csv)
            levels = ",".join(str(v) for v in raw["percentage"].unique().sort().to_list())
            summaries.append(
                {"symbol": symbol, **asdict(quality), "sha256": digest, "levels": levels}
            )
            hourly_frames.append(hourly.with_columns(pl.lit(symbol).alias("symbol")))
    pl.DataFrame(inventories).write_csv(root / "inventory_quality.csv")
    pl.DataFrame(missing_rows).write_csv(root / "missing_days.csv")
    summary = pl.DataFrame(summaries)
    summary.write_csv(root / "sample_quality.csv")
    pl.concat(hourly_frames).write_parquet(root / "sample_hourly.parquet")
    print(pl.DataFrame(inventories))
    print(
        summary.group_by("symbol").agg(
            pl.len().alias("sample_days"),
            pl.sum("rows"),
            pl.sum("snapshots"),
            pl.sum("invalid_snapshots"),
            pl.sum("valid_hours"),
        )
    )
    decision = "REJECTED (BLOCKED-DATA)" if gate_failed else "FULL CONTENTS AUDIT STILL REQUIRED"
    print(f"Order-book parameter trials executed: 0; data decision: {decision}.")


if __name__ == "__main__":
    app()

from __future__ import annotations

import argparse
import socket
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Final, TypedDict

import httpx2
import polars as pl

LEADERBOARD_URL: Final = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
INFO_URL: Final = "https://api.hyperliquid.xyz/info"
TARGET_COINS: Final = ("BTC", "ETH")
MINIMUM_ACCOUNT_VALUE: Final = 100_000.0
ROSTER_LIMIT: Final = 20


class PerformanceRaw(TypedDict):
    pnl: str
    roi: str
    vlm: str


class LeaderboardRowRaw(TypedDict):
    ethAddress: str
    accountValue: str
    displayName: str | None
    windowPerformances: list[tuple[str, PerformanceRaw]]


class LeaderboardPayloadRaw(TypedDict):
    leaderboardRows: list[LeaderboardRowRaw]


class PositionRaw(TypedDict):
    coin: str
    szi: str
    positionValue: str


class AssetPositionRaw(TypedDict):
    position: PositionRaw


class ClearinghouseRaw(TypedDict):
    assetPositions: list[AssetPositionRaw]


class WhaleShadowError(ValueError):
    reason: str

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class LeaderboardEntry:
    address: str
    account_value: float
    week_pnl: float
    month_pnl: float
    all_time_pnl: float


@dataclass(frozen=True, slots=True)
class WhalePosition:
    address: str
    coin: str
    signed_size: float
    position_value: float


@dataclass(frozen=True, slots=True)
class AssetSnapshot:
    coin: str
    mid_price: float
    long_accounts: int
    short_accounts: int
    signed_notional: float
    gross_notional: float
    crowding_score: float
    signal: int


def hyperliquid_client() -> httpx2.Client:
    limits = httpx2.Limits(
        max_connections=40,
        max_keepalive_connections=20,
        keepalive_expiry=30.0,
    )
    transport = httpx2.HTTPTransport(
        http2=True,
        retries=3,
        limits=limits,
        socket_options=[(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)],
    )
    return httpx2.Client(
        transport=transport,
        timeout=httpx2.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0),
        follow_redirects=True,
    )


def parse_leaderboard(payload: LeaderboardPayloadRaw) -> tuple[LeaderboardEntry, ...]:
    rows: list[LeaderboardEntry] = []
    for raw in payload["leaderboardRows"]:
        performances = {name: performance for name, performance in raw["windowPerformances"]}
        missing = {"week", "month", "allTime"}.difference(performances)
        if missing:
            raise WhaleShadowError(f"leaderboard row missing windows: {sorted(missing)}")
        rows.append(
            LeaderboardEntry(
                address=raw["ethAddress"].lower(),
                account_value=float(raw["accountValue"]),
                week_pnl=float(performances["week"]["pnl"]),
                month_pnl=float(performances["month"]["pnl"]),
                all_time_pnl=float(performances["allTime"]["pnl"]),
            )
        )
    return tuple(rows)


def select_frozen_roster(
    rows: tuple[LeaderboardEntry, ...],
    *,
    minimum_account_value: float = MINIMUM_ACCOUNT_VALUE,
    limit: int = ROSTER_LIMIT,
) -> tuple[LeaderboardEntry, ...]:
    eligible = (
        row
        for row in rows
        if row.account_value >= minimum_account_value and row.week_pnl > 0.0 and row.month_pnl > 0.0
    )
    return tuple(sorted(eligible, key=lambda row: row.all_time_pnl, reverse=True)[:limit])


def aggregate_asset(
    positions: tuple[WhalePosition, ...], coin: str, *, mid_price: float
) -> AssetSnapshot:
    matching = tuple(position for position in positions if position.coin == coin)
    long_accounts = sum(position.signed_size > 0.0 for position in matching)
    short_accounts = sum(position.signed_size < 0.0 for position in matching)
    signed_notional = sum(
        position.position_value if position.signed_size > 0.0 else -position.position_value
        for position in matching
    )
    gross_notional = sum(position.position_value for position in matching)
    crowding_score = 0.0 if gross_notional == 0.0 else signed_notional / gross_notional
    signal = 1 if crowding_score > 0.0 else -1 if crowding_score < 0.0 else 0
    return AssetSnapshot(
        coin=coin,
        mid_price=mid_price,
        long_accounts=long_accounts,
        short_accounts=short_accounts,
        signed_notional=signed_notional,
        gross_notional=gross_notional,
        crowding_score=crowding_score,
        signal=signal,
    )


def _fetch_leaderboard(client: httpx2.Client) -> tuple[LeaderboardEntry, ...]:
    response = client.get(LEADERBOARD_URL)
    _ = response.raise_for_status()
    payload: LeaderboardPayloadRaw = response.json()
    return parse_leaderboard(payload)


def _fetch_positions(client: httpx2.Client, address: str) -> tuple[WhalePosition, ...]:
    response = client.post(INFO_URL, json={"type": "clearinghouseState", "user": address})
    _ = response.raise_for_status()
    payload: ClearinghouseRaw = response.json()
    positions: list[WhalePosition] = []
    for raw in payload["assetPositions"]:
        position = raw["position"]
        coin = position["coin"]
        if coin not in TARGET_COINS:
            continue
        signed_size = float(position["szi"])
        position_value = abs(float(position["positionValue"]))
        if signed_size == 0.0 or position_value == 0.0:
            continue
        positions.append(WhalePosition(address, coin, signed_size, position_value))
    return tuple(positions)


def _fetch_mids(client: httpx2.Client) -> dict[str, float]:
    response = client.post(INFO_URL, json={"type": "allMids"})
    _ = response.raise_for_status()
    raw: dict[str, str] = response.json()
    return {coin: float(raw[coin]) for coin in TARGET_COINS}


def _write_roster(path: Path, roster: tuple[LeaderboardEntry, ...]) -> None:
    pl.DataFrame([asdict(row) for row in roster]).write_csv(path)


def _read_roster(path: Path) -> tuple[LeaderboardEntry, ...]:
    frame = pl.read_csv(path)
    return tuple(
        LeaderboardEntry(
            address=str(row["address"]),
            account_value=float(row["account_value"]),
            week_pnl=float(row["week_pnl"]),
            month_pnl=float(row["month_pnl"]),
            all_time_pnl=float(row["all_time_pnl"]),
        )
        for row in frame.to_dicts()
    )


def _append_snapshots(path: Path, snapshot_time: datetime, snapshots: tuple[AssetSnapshot, ...]) -> None:
    rows = [
        {
            "snapshot_date": snapshot_time.date().isoformat(),
            "snapshot_time_utc": snapshot_time.isoformat(),
            **asdict(snapshot),
        }
        for snapshot in snapshots
    ]
    current = pl.DataFrame(rows)
    if path.exists():
        existing = pl.read_csv(path)
        same_day = existing.filter(pl.col("snapshot_date") == snapshot_time.date().isoformat())
        if same_day.height:
            raise WhaleShadowError("a whale shadow snapshot already exists for this UTC date")
        current = pl.concat((existing, current), how="vertical_relaxed")
    current.write_csv(path)


def evaluate_completed_horizons(snapshots: pl.DataFrame) -> pl.DataFrame:
    if snapshots.is_empty():
        return pl.DataFrame()
    rows: list[dict[str, str | int | float]] = []
    for coin in TARGET_COINS:
        coin_frame = snapshots.filter(pl.col("coin") == coin).sort("snapshot_date")
        prices = {
            date.fromisoformat(str(row["snapshot_date"])): float(row["mid_price"])
            for row in coin_frame.to_dicts()
        }
        for row in coin_frame.to_dicts():
            signal = int(row["signal"])
            if signal == 0:
                continue
            start = date.fromisoformat(str(row["snapshot_date"]))
            start_price = float(row["mid_price"])
            for horizon in (1, 7):
                end_price = prices.get(start + timedelta(days=horizon))
                if end_price is None:
                    continue
                signed_return = signal * (end_price / start_price - 1.0)
                rows.append(
                    {
                        "coin": coin,
                        "signal_date": start.isoformat(),
                        "horizon_days": horizon,
                        "signal": signal,
                        "signed_return": signed_return,
                    }
                )
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def take_snapshot(root: Path) -> tuple[tuple[LeaderboardEntry, ...], tuple[AssetSnapshot, ...]]:
    root.mkdir(parents=True, exist_ok=True)
    roster_path = root / "frozen_roster.csv"
    snapshot_time = datetime.now(UTC)
    with hyperliquid_client() as client:
        if roster_path.exists():
            roster = _read_roster(roster_path)
        else:
            roster = select_frozen_roster(_fetch_leaderboard(client))
            if len(roster) != ROSTER_LIMIT:
                raise WhaleShadowError(f"expected {ROSTER_LIMIT} eligible whale accounts, got {len(roster)}")
            _write_roster(roster_path, roster)
        mids = _fetch_mids(client)
        positions = tuple(
            position
            for row in roster
            for position in _fetch_positions(client, row.address)
        )

    snapshot_id = snapshot_time.strftime("%Y%m%dT%H%M%SZ")
    pl.DataFrame([asdict(position) for position in positions]).write_parquet(
        root / f"positions_{snapshot_id}.parquet"
    )
    snapshots = tuple(
        aggregate_asset(positions, coin, mid_price=mids[coin]) for coin in TARGET_COINS
    )
    snapshots_path = root / "snapshots.csv"
    _append_snapshots(snapshots_path, snapshot_time, snapshots)
    evaluations = evaluate_completed_horizons(pl.read_csv(snapshots_path))
    if not evaluations.is_empty():
        evaluations.write_csv(root / "evaluations.csv")
    return roster, snapshots


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture the frozen Hyperliquid whale shadow cohort")
    _ = parser.add_argument(
        "--root",
        type=Path,
        default=Path("artifacts/edge_search/hyperliquid_whale_shadow"),
    )
    args = parser.parse_args()
    root: Path = args.root
    roster, snapshots = take_snapshot(root)
    print(f"state=SHADOW/TRACKING frozen_roster={len(roster)}")
    for snapshot in snapshots:
        message = f"{snapshot.coin} signal={snapshot.signal:+d} "
        message += f"crowding={snapshot.crowding_score:+.4f} "
        message += f"long={snapshot.long_accounts} short={snapshot.short_accounts} "
        message += f"gross_notional=${snapshot.gross_notional:,.0f} mid={snapshot.mid_price:,.2f}"
        print(message)


if __name__ == "__main__":
    main()

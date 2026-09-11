from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd  # noqa: PANDAS_OK
from numpy.typing import NDArray

from quant_lab.data.market import load_market_data


class RotationResearchError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RotationSpec:
    momentum_hours: int = 168
    trend_ema_hours: int = 400
    fee_bps: float = 5.0
    slippage_bps: float = 2.0

    def __post_init__(self) -> None:
        if self.momentum_hours <= 0 or self.trend_ema_hours <= 0:
            raise RotationResearchError("momentum and trend windows must be positive")
        if self.fee_bps < 0.0 or self.slippage_bps < 0.0:
            raise RotationResearchError("fee and slippage must be non-negative")


@dataclass(frozen=True, slots=True)
class RotationEvaluation:
    timeframe_hours: int
    period: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    target_changes: int
    invested_fraction: float


def _bars(hours: int, timeframe_hours: int) -> int:
    return max(1, round(hours / timeframe_hours))


def load_rotation_frame(root: Path, timeframe_hours: int) -> pd.DataFrame:
    if timeframe_hours not in (1, 4):
        raise RotationResearchError("rotation research supports 1h and 4h data")
    suffix = f"{timeframe_hours}h_microstructure.parquet"
    btc = load_market_data(root / f"BTC_USDT_{suffix}")[["open", "close"]].rename(
        columns={"open": "btc_open", "close": "btc_close"}
    )
    eth = load_market_data(root / f"ETH_USDT_{suffix}")[["open", "close"]].rename(
        columns={"open": "eth_open", "close": "eth_close"}
    )
    return btc.join(eth, how="inner").sort_index()


def generate_rotation_targets(
    frame: pd.DataFrame,
    spec: RotationSpec,
    *,
    timeframe_hours: int,
) -> pd.Series:
    if timeframe_hours not in (1, 4):
        raise RotationResearchError("rotation targets support 1h and 4h data")
    required = {"btc_close", "eth_close"}
    missing = required.difference(frame.columns)
    if missing:
        raise RotationResearchError(f"missing required columns: {sorted(missing)}")
    momentum_bars = _bars(spec.momentum_hours, timeframe_hours)
    ema_bars = _bars(spec.trend_ema_hours, timeframe_hours)
    btc_momentum = frame["btc_close"] / frame["btc_close"].shift(momentum_bars) - 1.0
    eth_momentum = frame["eth_close"] / frame["eth_close"].shift(momentum_bars) - 1.0
    btc_eligible = frame["btc_close"] > frame["btc_close"].ewm(span=ema_bars, adjust=False).mean()
    eth_eligible = frame["eth_close"] > frame["eth_close"].ewm(span=ema_bars, adjust=False).mean()
    candidate = pd.Series(0.0, index=frame.index, dtype=float)
    candidate.loc[btc_eligible & ~eth_eligible] = 1.0
    candidate.loc[eth_eligible & ~btc_eligible] = -1.0
    both = btc_eligible & eth_eligible & btc_momentum.notna() & eth_momentum.notna()
    candidate.loc[both & (btc_momentum >= eth_momentum)] = 1.0
    candidate.loc[both & (eth_momentum > btc_momentum)] = -1.0
    decision_hour = 24 - timeframe_hours
    decisions = pd.Series(np.nan, index=frame.index, dtype=float)
    decisions.loc[pd.DatetimeIndex(frame.index).hour == decision_hour] = candidate.loc[
        pd.DatetimeIndex(frame.index).hour == decision_hour
    ]
    return decisions.ffill().shift(1).fillna(0.0).astype(float)


def evaluate_rotation(
    frame: pd.DataFrame,
    targets: pd.Series,
    spec: RotationSpec,
    *,
    timeframe_hours: int,
    period: str,
    start: str,
    end: str,
) -> RotationEvaluation:
    if not targets.index.equals(frame.index):
        raise RotationResearchError("targets index must exactly match the price frame")
    index = pd.DatetimeIndex(frame.index)
    start_timestamp = pd.Timestamp(start, tz="UTC")
    end_timestamp = pd.Timestamp(end, tz="UTC")
    btc_open: NDArray[np.float64] = np.asarray(
        frame["btc_open"].to_numpy(dtype=np.float64), dtype=np.float64
    )
    eth_open: NDArray[np.float64] = np.asarray(
        frame["eth_open"].to_numpy(dtype=np.float64), dtype=np.float64
    )
    target_values: NDArray[np.float64] = np.asarray(
        targets.to_numpy(dtype=np.float64), dtype=np.float64
    )
    offsets = [
        offset
        for offset in range(len(frame) - 1)
        if index[offset] >= start_timestamp and index[offset + 1] <= end_timestamp
    ]
    if not offsets:
        return RotationEvaluation(timeframe_hours, period, 0.0, 0.0, 0.0, 0, 0.0)
    one_way_cost = (spec.fee_bps + spec.slippage_bps) / 10_000.0
    interval_returns: list[float] = []
    invested = 0
    target_changes = 0
    previous_target = 0.0
    for offset in offsets:
        target = float(target_values[offset])
        if target != previous_target:
            target_changes += 1
        transition_cost = abs(target - previous_target) * one_way_cost
        btc_return = float(btc_open[offset + 1] / btc_open[offset] - 1.0)
        eth_return = float(eth_open[offset + 1] / eth_open[offset] - 1.0)
        if target > 0.0:
            asset_return = btc_return
        elif target < 0.0:
            asset_return = eth_return
        else:
            asset_return = 0.0
        interval_returns.append(asset_return - transition_cost)
        invested += int(target != 0.0)
        previous_target = target
    if previous_target != 0.0:
        interval_returns[-1] -= one_way_cost
    values = np.asarray(interval_returns, dtype=np.float64)
    equity = 1.0
    peak_equity = 1.0
    max_drawdown = 0.0
    for interval_return in values.tolist():
        equity *= 1.0 + float(interval_return)
        peak_equity = max(peak_equity, equity)
        max_drawdown = min(max_drawdown, equity / peak_equity - 1.0)
    volatility = float(np.std(values, ddof=0))
    sharpe_ratio = (
        float(np.mean(values) / volatility * np.sqrt(8760.0 / timeframe_hours))
        if volatility > 0.0
        else 0.0
    )
    return RotationEvaluation(
        timeframe_hours=timeframe_hours,
        period=period,
        total_return=equity - 1.0,
        sharpe_ratio=sharpe_ratio,
        max_drawdown=max_drawdown,
        target_changes=target_changes,
        invested_fraction=invested / len(offsets),
    )


def _run_period(
    root: Path,
    spec: RotationSpec,
    period: str,
    start: str,
    end: str,
) -> tuple[RotationEvaluation, RotationEvaluation]:
    evaluations: list[RotationEvaluation] = []
    for timeframe_hours in (1, 4):
        frame = load_rotation_frame(root, timeframe_hours)
        targets = generate_rotation_targets(frame, spec, timeframe_hours=timeframe_hours)
        evaluations.append(
            evaluate_rotation(
                frame,
                targets,
                spec,
                timeframe_hours=timeframe_hours,
                period=period,
                start=start,
                end=end,
            )
        )
    return evaluations[0], evaluations[1]


def run_research(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    spec = RotationSpec()
    discovery = _run_period(root, spec, "discovery", "2022-01-01", "2024-01-01")
    validation = _run_period(root, spec, "validation", "2024-01-01", "2026-01-01")
    pre_pass = all(
        evaluation.total_return > 0.0
        and evaluation.sharpe_ratio > 0.0
        and evaluation.target_changes >= 10
        for evaluation in (*discovery, *validation)
    )
    pre_stress = pd.DataFrame(
        [
            {**asdict(evaluation), "pre_holdout_pass": pre_pass}
            for evaluation in (*discovery, *validation)
        ]
    )
    stress = _run_period(root, spec, "stress_2026", "2026-01-01", "2026-09-11")
    stress_frame = pd.DataFrame(
        [{**asdict(evaluation), "pre_holdout_pass": pre_pass} for evaluation in stress]
    )
    shadow_rows: list[dict[str, float | int | str]] = []
    for timeframe_hours in (1, 4):
        frame = load_rotation_frame(root, timeframe_hours)
        if bool((pd.DatetimeIndex(frame.index) >= pd.Timestamp("2026-09-11", tz="UTC")).any()):
            targets = generate_rotation_targets(frame, spec, timeframe_hours=timeframe_hours)
            evaluation = evaluate_rotation(
                frame,
                targets,
                spec,
                timeframe_hours=timeframe_hours,
                period="future_shadow",
                start="2026-09-11",
                end="2100-01-01",
            )
            shadow_rows.append(asdict(evaluation))
    return pre_stress, stress_frame, pd.DataFrame(shadow_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the preregistered BTC/ETH strength rotation")
    _ = parser.add_argument("--root", type=Path, default=Path("artifacts/edge_search"))
    args = parser.parse_args()
    root: Path = args.root
    pre_stress, stress, shadow = run_research(root)
    pre_stress.to_csv(root / "relative_strength_rotation_pre_stress.csv", index=False)
    stress.to_csv(root / "relative_strength_rotation_stress_2026.csv", index=False)
    shadow.to_csv(root / "relative_strength_rotation_shadow.csv", index=False)
    print("pre-stress")
    print(pre_stress.to_string(index=False))
    print("stress")
    print(stress.to_string(index=False))
    print("future shadow")
    print("no completed shadow window yet" if shadow.empty else shadow.to_string(index=False))


if __name__ == "__main__":
    main()

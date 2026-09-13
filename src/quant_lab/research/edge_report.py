from __future__ import annotations

from pathlib import Path

import pandas as pd

from quant_lab.backtest.models import BacktestConfig
from quant_lab.data.market import load_market_data
from quant_lab.research.edge_discovery import EdgeDataset, EdgeSearchReport, discover_edges


def run_edge_search_paths(
    btc_1h_path: Path,
    eth_1h_path: Path,
    btc_4h_path: Path,
    eth_4h_path: Path,
    backtest_config: BacktestConfig,
) -> EdgeSearchReport:
    datasets = (
        EdgeDataset("BTC_1h", "BTC/USDT", 1, load_market_data(btc_1h_path)),
        EdgeDataset("ETH_1h", "ETH/USDT", 1, load_market_data(eth_1h_path)),
        EdgeDataset("BTC_4h", "BTC/USDT", 4, load_market_data(btc_4h_path)),
        EdgeDataset("ETH_4h", "ETH/USDT", 4, load_market_data(eth_4h_path)),
    )
    return discover_edges(datasets, backtest_config)


def edge_report_lines(report: EdgeSearchReport) -> tuple[str, ...]:
    lines: list[str] = []
    for champion in report.champions:
        verdict = "SURVIVED" if champion.holdout_pass is True else "REJECTED"
        lines.append(" ".join((
            f"EDGE {champion.family.value}: {verdict}",
            f"params={champion.parameter_key}",
            f"pre_score={champion.pre_holdout_score:.4f}",
            f"validation_min_return={champion.validation_min_return:.4f}",
            f"holdout_min_return={champion.holdout_min_return:.4f}",
            f"holdout_min_sharpe={champion.holdout_min_sharpe:.4f}",
        )))
        for detail in champion.datasets:
            lines.append(" ".join((
                f"  {detail.label}",
                f"validation={detail.validation_return:.4f}",
                f"holdout={detail.holdout_return:.4f}",
                f"holdout_sharpe={detail.holdout_sharpe:.4f}",
            )))
    return tuple(lines)


def write_edge_report_csv(report: EdgeSearchReport, path: Path) -> None:
    champion_by_family = {champion.family: champion for champion in report.champions}
    rows: list[dict[str, str | float | int | bool | None]] = []
    for candidate in report.candidates:
        champion = champion_by_family.get(candidate.family)
        if champion is not None and champion.parameter_key == candidate.parameter_key:
            selected = True
            holdout_min_return = champion.holdout_min_return
            holdout_min_sharpe = champion.holdout_min_sharpe
            holdout_min_trades = champion.holdout_min_trades
            holdout_pass = champion.holdout_pass
        else:
            selected = False
            holdout_min_return = None
            holdout_min_sharpe = None
            holdout_min_trades = None
            holdout_pass = None
        rows.append(
            {
                "family": candidate.family.value,
                "parameter_key": candidate.parameter_key,
                "selected_family_champion": selected,
                "pre_holdout_pass": candidate.pre_holdout_pass,
                "pre_holdout_score": candidate.pre_holdout_score,
                "discovery_min_return": candidate.discovery_min_return,
                "validation_min_return": candidate.validation_min_return,
                "validation_min_sharpe": candidate.validation_min_sharpe,
                "validation_min_trades": candidate.validation_min_trades,
                "holdout_min_return": holdout_min_return,
                "holdout_min_sharpe": holdout_min_sharpe,
                "holdout_min_trades": holdout_min_trades,
                "holdout_pass": holdout_pass,
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)

# Crypto Quant Lab

Personal BTC/ETH quant research platform built around a simple idea: **research fast, validate realistically, trade only after forward testing**.

The code is framework-agnostic. It borrows design ideas from mature open-source systems, but strategy logic stays independent so adapters for vectorbt, NautilusTrader, Freqtrade, or custom execution can be added later without rewriting the core strategy.

## v0.1 architecture

```text
Market Data
   ↓
Strategy (framework-agnostic target exposure)
   ↓
Risk / Position Sizing
   ↓
Fast Backtester
   ├─ one-bar delayed execution
   ├─ fees
   └─ slippage
   ↓
Walk-forward validation
   ↓
Report / later realistic-engine adapter
```

## Included now

- BTC/ETH-oriented OHLCV CSV/Parquet loader
- framework-independent `Strategy` protocol
- EMA + breakout example strategy
- cost-aware vectorized fast backtester
- lookahead guard via one-bar signal shift
- total return, MDD and Sharpe metrics
- stop-distance/risk-budget position sizing helper
- chronological walk-forward splitter
- CLI entry point
- smoke tests

## Install

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e ".[dev]"
```

## Run a backtest

Input must contain `open, high, low, close, volume`; `timestamp` is optional and will be parsed as UTC.

```bash
quant test data/BTCUSDT-1h.parquet
```

Customize costs/strategy parameters:

```bash
quant test data/BTCUSDT-1h.parquet --fee-bps 5 --slippage-bps 2 --fast 50 --slow 200 --breakout 20
```

## Next milestones

1. Exchange data downloader/cache for BTC/ETH.
2. Richer metrics and trade ledger.
3. Parameter sweep / fast research adapter.
4. Out-of-sample and walk-forward report aggregation.
5. Realistic event-driven validation adapter.
6. Paper-trading execution adapter.
7. Funding/OI/liquidation/order-book feature datasets.

The project should not send live orders until realistic validation and paper trading are implemented and explicitly enabled.

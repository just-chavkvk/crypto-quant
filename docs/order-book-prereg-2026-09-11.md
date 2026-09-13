# Order-book data gate and prospective research contract

Registered 2026-09-11 07:32 UTC, before loading price-aligned book features or returns.
One BTC 2023-01-01 file was opened only to establish schema: timestamp, percentage,
depth, notional; cumulative signed levels -5..-1 and +1..+5, approximately 30s snapshots.

## Protection and novelty

The existing position-cap, breadth and dual-confirmed SHADOW strategies, starts,
parameters and refresh runner remain frozen. Their source hashes are saved in
`artifacts/edge_search/order_book/frozen_shadow_before.sha256`.
This study measures *resting displayed liquidity*, unlike rejected executed taker
flow, OHLCV impact fade, OI turnover and momentum filters. No price trend filter,
threshold grid, reversed-direction retry or ex-post holding-period search is allowed.

## Data gate, fixed before the full audit

- Official Binance USD-M BTCUSDT and ETHUSDT daily bookDepth only.
- Inspect the complete archive inventory, SHA256 CHECKSUMs and actual contents.
- Historical cutoff: 2026-09-11 00:00 UTC (exclusive).
- Required periods: discovery 2023; validation 2024-2025; stress 2026 to cutoff.
  Book data cannot establish performance in 2022. No claim of a pristine holdout.
- Each asset/year must have >=99% of calendar days present and >=99% valid hours;
  no run of invalid hours may exceed 24 hours. All downloaded checksums must match.
- A snapshot must have each of the ten signed levels exactly once, positive finite
  depth/notional, monotone cumulative size on each side, lower bid than ask implied
  VWAP, and a timestamp inside its named UTC day. Duplicate/conflicting snapshots
  are invalid, never silently deduplicated. Report observed cadence and invalidity.
- An hour needs >=90 complete snapshots, a first observation within 120 seconds
  of its start, last within 120 seconds of its end, and no internal gap >120s.
  Incomplete hours are unavailable; no forward/backward fill or compressed-time hold.
- These are aggregated percentage bands, not best-bid/ask, order messages, queue
  position or a full order-book reconstruction. Only an hourly pressure hypothesis
  is eligible. Failure of the gate means no order-book profitability backtest.

## One conditional trial, fixed before returns

If the data gate passes, register and execute exactly one joint BTC/ETH trial:
hourly median I = (bid notional within 1% - ask notional within 1%) /
(bid notional within 1% + ask notional within 1%). Event is I >= +0.20 (long) or
I <= -0.20 (short); otherwise cash. No momentum, taker, OI or funding entry filter.
The 0.20 threshold means a 1.5:1 displayed-notional ratio. Use only fully completed
hours, enter at the following hour open, hold four actual hours, no overlapping
trades or same-hour re-entry; 5% stop; fixed 20% equity allocation at entry, no leverage.
Use matching USD-M futures klines and actual funding settlements. Both fills cost
5bp fee + 2bp slippage plus 0.02 times the previous completed candle range/open.
No financing omissions or realized future-bar range in opening slippage.
Missing execution candles/funding coverage invalidate the affected sample; do not
convert missing values to zero funding. Funding timestamp entry <= t < exit is charged.

BTC and ETH must each have return >0, calendar-hour Sharpe >0 and >=10 completed
trades in discovery and validation. Stress must meet the same gates. A historical
success is SHADOW only, with a newly frozen future window starting no earlier than
2026-09-12 00:00 UTC; PASS requires completion of that future window, positive net
return/Sharpe and >=10 trades in both assets. Fix its end before starting tracking.
Report net and zero execution-cost diagnostics on the same trades, keeping funding.
Do not let a diagnostic overturn the primary verdict.

## Conditional fallback

If order-book data fails, record final research decision REJECTED (data contract),
retaining BLOCKED-DATA as the reason rather than claiming the mechanism is disproven.
Then audit futures kline trade count and average quote trade size. Before looking at
its returns, create a separate participation-intensity registration with one fixed
mechanism/rule and explicit distinction from the rejected volume/OI/taker families.
Do not backtest this fallback merely because the valid order-book trial loses money.

## Work evidence

1. Freeze SHADOW source and refresh unchanged tracker.
2. Audit order-book inventory and contents; apply the fixed data gate.
3. Execute only the eligible preregistered trial (or conditional fallback).
4. Record verdicts, actual counts, limitations and reproducibility evidence in the
   dated note and research ledger; commit implementation and research separately.

# Participation-intensity trial: fragmented activity exhaustion

Registered 2026-09-11 07:40 UTC, before collecting or evaluating participation
features/returns. Order-book was disqualified by the inventory's consecutive missing
2023-02-08 and 2023-02-09 daily files in both BTC and ETH (48h > registered 24h).
Its 98 calendar-selected sample files are still being audited for the data record.

## Distinct economic hypothesis and exactly one trial

A large number of executions combined with unusually small average execution size
may indicate fragmented participation that exhausts a contemporaneous price move.
This is a hypothesis about execution-size composition, not proof of retail identity.
Unlike rejected volume breakout, taker divergence and OI-turnover, no total-volume
trigger, aggressor direction, OI, long/short ratio or momentum trend filter is used.
OHLC direction supplies the fade direction only, without a return threshold.

- BTCUSDT and ETHUSDT USD-M perpetuals, 1h completed candles only.
- count = kline `count`; average size = `quote_volume / count`, measured in USDT.
- Prior 720 *calendar* hours, excluding the signal hour, must all be valid.
- Event: count >= prior-720h count q95 AND average size <= prior-720h size q25.
- If close > open, short; if close < open, long; equal prices mean no event.
- One joint rule across both assets, no grid, alternative signs, threshold/window/
  hold changes or fallback variants after results. Number of parameter trials = 1.

## Data gate and historical periods

Use checksum-verified official `futures/um/monthly/klines/<symbol>/1h` files,
monthly fundingRate and markPriceKlines (for funding notional valuation).
Download 2021-12 warm-up through 2026-08, the most recent complete monthly window.
No pre-existing cache is assumed to be futures based on its filename.

Require full 1h calendar continuity, unique timestamps, exactly completed 1h bars,
positive finite OHLC, valid high/low bounds, positive integer count and positive
finite base/quote volumes. Report trade-size/count distributions, duplicates, gaps,
year coverage and source checksum manifest. Exclude invalid feature hours and the
following 720h warm-up; no fills or compressed rows. Each asset/year must retain
>=99% valid input hours, with no execution-data gap >24h; otherwise reject for data.
Funding settlement sequence must agree with archive `funding_interval_hours`,
contain finite rates and have an exact valid mark-price candle for each settlement.
Missing settlement coverage is not zero funding.

- Discovery: [2022-01-01, 2024-01-01) UTC.
- Validation: [2024-01-01, 2026-01-01) UTC.
- Stress: [2026-01-01, 2026-09-01) UTC. This is reused stress history, not holdout.

## Execution contract

After the signal candle closes, enter at the next hour open. Allocate 20% of equity
at entry with fixed quantity, no leverage or within-position additions. Hold exactly
4 actual hours unless a 5% reference-entry stop triggers. No overlapping trades;
the next signal may be formed in the exit hour, giving a later entry. Require all
entry/exit/held candles; skip and report period-boundary truncated events.

For each fill use fee 5bp, adverse slippage 2bp + 0.02 * prior-completed-bar
(high-low)/open. Stop reference is the worse of stop price and gap open. No current
execution-bar range is used in slippage. For intrabar stops, funding at that hour's
open is charged before the stop; a gap-open exit occurs before that settlement.
Funding cashflow = -side * fixed quantity * mark open at settlement * actual rate,
for entry <= settlement < exit; opening settlement is conservatively charged.
This hourly convention cannot establish tick-level stop/funding order or fillability.

Calendar-hour equity (including cash hours, mark-to-market holdings, fees and funding)
defines return, Sharpe (sqrt(8760)) and max drawdown. Zero execution-cost diagnostics
use the identical entry/exit decisions, retain actual funding, and may not overturn
the verdict. Report count, gross, execution cost and funding separately.

## Verdict and prohibition on tuning

All six asset-period evaluations must exist. Each must have net return >0, calendar
Sharpe >0 and >=10 completed trades. Any failure is REJECTED for this family, with
no post-result parameter tuning. Historical success is SHADOW only, prospective
window [2026-09-12, 2026-12-12) UTC, rule and costs frozen. PASS requires the complete
future window and positive net return/Sharpe with >=10 trades for both assets.
Existing three SHADOW strategies and their tracking are unchanged.

# Same-asset hedged Edge research: preregistration

Registered on 2026-09-12; the Git commit timestamp is authoritative. This document
is committed before joining spot/perpetual data or calculating either candidate's
returns. Each candidate has exactly one fixed rule. 2026 is reused stress history.

## Preserved scope and novelty

The three existing SHADOW strategies and their seven strategy/tracking source files
are frozen and hashed in `artifacts/edge_search/carry/frozen_shadow_before.sha256`.
Previous order-book and participation trials remain closed with their original rules.

A. **Cash-funded spot/perpetual funding carry** receives the signed funding cashflow
on a short perpetual hedged with the same base quantity of owned spot. It does not
predict a price direction, filter a momentum strategy or trade a BTC/ETH funding
spread. It uses no funding-rate entry threshold or trailing funding filter.

B. **Executable same-asset spot/perpetual dislocation convergence** holds the same
hedge after an unusually positive *actual tradable market* spread. This materially
changes the execution/data contract from the rejected premium/BTC-ETH relative-value
fade: one physical asset with spot backing, matching base quantity in the derivative,
actual two-market execution costs and actual funding. The pricing link, not BTC/ETH
relative performance or mark/index premium alone, is the hypothesis.

Both are registered now. A failure cannot trigger different holding periods, entry
thresholds, asset subsets, reverse directions or rate filters in this family.

## Data contract

- BTCUSDT and ETHUSDT separately; Binance official spot and USD-M 1h klines,
  USD-M fundingRate and markPriceKlines. Reverify existing USD-M archive hashes.
- Full monthly archives 2021-12 through 2026-08. 2021-12 is context, not an evaluated
  discovery month. Historical cutoff is 2026-09-01 00:00 UTC exclusive.
- Reuse the seven checksum-verified daily mark-price repairs already documented in
  the participation study; never infer missing prices or funding.
- Spot timestamps switch from milliseconds to microseconds starting 2025-01-01,
  per the official repository. Normalize explicitly by source month; verify exact
  hourly open and close times after conversion. Headerless first rows are data.
- Require unique, full contiguous hourly calendars in both markets, positive finite
  OHLC and valid high/low bounds; no forward/backward fill or compressed time.
- Source checksum manifest includes every spot, futures, funding and mark archive.
  Record zero-volume hours. Both entry and exit must have positive volume in both
  markets. A prescribed monthly cycle with an untradable boundary fails its data
  gate; an untradable boundary for B is counted and blocks promotion rather than
  silently improving the sample. A zero-volume hour during a passive hold is marked
  using the reported OHLC without pretending a fill occurred.
- Actual funding intervals and rates must be complete. Archive offsets of 0..1000ms
  from the scheduled hour map only to that hour, with raw timestamps preserved in
  the immutable source. Exact event valuation uses that hour's mark open as a proxy.

## Fixed execution and capital accounting

Each asset-period starts with 10,000 USDT, flat. At entry buy spot quantity
`q = 0.40 * entry_equity / spot_open` and short exactly q units of USD-M perpetual.
Spot is fully paid; the remaining cash after spot outlay and both entry costs is
futures collateral. No borrowing, yield on idle cash, collateral transfers, leverage
increase, automatic hedge resizing, compounding within a cycle or partial fills.

Fill costs, in each direction: spot fee 10bp, perpetual fee 5bp, and each market's
adverse slippage 2bp + 0.02 * its preceding completed hour's (high-low)/open.
These are conservative research assumptions, not a claim of exact historical VIP
fees. Ignore fee promotions/BNB discounts. Cost is calculated on the actual adverse
fill; quantity is identical on both legs. Failure to fund the spot leg is a data/
capital error, never a synthetic negative cash balance treated as collateral.

During a hold, signed funding on the short is `+q * mark_open * funding_rate_event`.
Only settlements with entry <= time < exit accrue; exit is before that hour's
settlement. Use spot close + short unrealized PnL against mark close + available
collateral for hourly account equity; actual perpetual kline open sets the realized
exit, so mark-versus-executable basis is not erased. Record spot PnL, perpetual PnL,
funding and costs separately and prove they sum to final account PnL.

Conservative collateral audit every held hour: use mark high for the short's adverse
unrealized loss, debit negative funding before that high, and count positive funding
only after that high. Require remaining futures collateral / (q*mark_high) >=25%.
Any breach REJECTS the entire candidate, regardless of its nominal PnL; do not label
an unmodeled liquidation path profitable. This buffer is a declared research gate,
not a reconstruction of exchange margin tiers or an operational safety guarantee.

Two fills are modeled at the same hourly timestamp. Tick-level legging/spread,
exchange/custody default, margin tier changes and withdrawal risks are unmeasured.
Historical success therefore permits prospective SHADOW only, never live execution.

## A. Monthly carry schedule

Enter on the first UTC calendar day at 01:00 and exit on the same month's final day
at 23:00, open prices on both legs. This avoids incomplete end-of-window prices and
funding earned before entry. Freeze q for the month. All available full months are
included; both positive and negative funding are accrued. No outcome-dependent skips.

Slow carry cycles are the sampling unit: >=6 fully closed calendar months per primary
period, not the >=10 short trades used by earlier intraday families. This gate is
fixed before returns. All complete months must be represented (24/24/8 below).

## B. Positive dislocation schedule

At each completed hour calculate `perp_close / spot_close - 1`. If this is >=0.005
(50bp), enter the hedge at the NEXT hourly open. Hold exactly 24 real hours. No entry
when already holding; the earliest new signal is the completed exit hour, hence
no same-hour re-entry. Exit at the scheduled open regardless of subsequent spread
or funding; no adaptive profit taking, price stops or threshold search.

Signal, entry and exit must lie inside the period. Report boundary-truncated signals
separately. Require >=10 completed trades per primary asset-period; zero or sparse
samples cannot be counted as passed. The same capital/collateral gate applies.

## Periods, diagnostics and final states

Primary periods: discovery [2022-01-01,2024-01-01), validation [2024-01-01,2026-01-01),
stress [2026-01-01,2026-09-01), all UTC. Exactly six asset-period evaluations per
candidate must exist. Each must have net return >0, calendar-hour Sharpe >0, maximum
drawdown better than -10%, required completed cycles and zero collateral violations.
Also require net return >0 in each separate calendar-year replay (2022..2025 and
2026 Jan-Aug) for both assets. Do not choose winners from stress results.

Zero-execution-cost diagnostic removes only fees/slippage, retains funding, and
uses identical entry/exit times and directions. It cannot overturn the verdict.
Net PnL attribution separates actual funding from spot/perpetual basis changes.

Fail any primary/year/risk/sample gate: REJECTED, no same-family tuning. Data gate
failure: REJECTED with BLOCKED-DATA reason, not proof the economic idea is false.
A historical pass: SHADOW. Future carry window [2026-10-01,2027-10-01) UTC, requiring
12 completed monthly cycles for each asset, positive net return/Sharpe, max drawdown
better than -10%, no collateral breach. Future B window [2026-09-13,2027-09-13) UTC,
>=10 trades per asset with the same return/risk gates. PASS only after the full
predeclared future window completes. No paper/live promotion in this research run.

## Pre-return contract clarification / data gate v2

The initial exact-close-time gate stopped before any strategy return was calculated.
Monthly, daily and REST cross-checks are recorded in
`artifacts/edge_search/carry/spot_checks/cross_source_check.csv`. The anomalies are:
2021-12-24 04:00 (BTC/ETH, shortened traded candles in UNUSED context) and
2023-03-24 12:00 (BTC/ETH, zero trades/zero volume with constant OHLC).

Keep all original timestamps and values. Never rewrite a shortened close time.
Only the complete hourly evaluation calendar from 2022-01-01 is eligible for signals
and trades; the 2021 anomalies cannot affect any entry, prior-cost candle or hold.
Inside evaluated time, a shortened candle is accepted solely as a known UNAVAILABLE
market hour if volume=count=0 and OHLC is constant. Such an hour cannot produce B's
signal or either strategy's entry/exit. Passive existing holdings may retain the
reported mark with the declared collateral risk gate; no synthetic fill occurs.
Any other malformed evaluated bar still fails. This explicit market-availability
contract supersedes v1's global exact-close-time rejection, before the first
backtest; it is not a profitability-driven data repair or parameter relaxation.

Read-only pre-return audit also fixes these accounting/measurement ambiguities:

- B is a **trade-price basis signal with modeled fills**, not an observed executable
  bid/ask arbitrage. Hourly trade close/open cannot prove simultaneous fillability.
- `cash wallet` excludes unrealized futures PnL. NAV adds unrealized PnL exactly once;
  margin equity includes it. Do not subtract a margin reservation from cash again.
- Both leg PnLs use reference market prices. Adverse slippage and fees are charged
  once in execution_cost; no additional subtraction of the same fill difference.
- Yearly gates use natural-year segments of PRIMARY hourly equity, anchored to the
  preceding hour's NAV, preserving PnL on B trades spanning December/January.
  Separate flat-at-January replays are not the annual gate. All sign/risk thresholds
  and family rules remain as originally registered.

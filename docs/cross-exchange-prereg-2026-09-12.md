# Binance–Bybit same-asset funding differential: preregistration

The Git commit timestamp is authoritative. Registered before downloading the full
Bybit series or computing portfolio returns. Earlier work only checked 18 one-day
API samples in BTC/ETH during 2022, 2024 and 2026; those were access checks, not a
complete data-quality pass or profitability test.

## Novelty and one fixed trial

Same BTC or ETH base quantity, opposite USDT-linear perpetual positions on Binance
and Bybit. The economic source is a difference in ACTUAL funding cashflows across
venues. This changes the data and execution contract materially from rejected
BTC/ETH post-settlement funding-difference price fade, same-venue directional
funding signals, and spot/perpetual carry blocked by a missing spot-market hour.
There is no spot leg, token-universe expansion, momentum or price-return filter.

One fixed monthly rule across both BTCUSDT and ETHUSDT, with no threshold grid:
At each UTC month start, sum settled funding rates over the preceding seven COMPLETE
UTC days [month_start-7d, month_start) separately for each venue. If Bybit's sum is
larger, short Bybit and long Binance; reverse both sides if Binance's sum is larger.
An exactly zero difference means cash for that month. Do not use the current month's
00:00 funding value or any future funding in the entry decision.

Enter first calendar day 01:00 UTC, exit that month's final day 23:00 UTC using
both venues' trade-kline opens. Freeze side and identical base quantity for the month.
No intramonth reversal, stop, resizing, rate threshold, asset selection or adaptation.

## Capital, costs, funding, margin

Start each asset-period with 10,000 USDT: 5,000 in each venue's independent cash
wallet. No transfers, borrowing, interest, added funds or cross-venue margin netting.
At each entry q = 0.40*min(wallet_binance,wallet_bybit)/max(entry_price_binance,
entry_price_bybit). Both legs use q; no short-notional cash receipt or purchase of
spot principal. After each exit, each venue retains its own realized PnL and costs;
wallets are NOT rebalanced for free.

Per fill, assume Binance taker fee 5bp and Bybit 5.5bp, plus adverse slippage 2bp +
0.02*(previous completed hour high-low)/open for the respective venue. These are
conservative declared research assumptions, not asserted historical account fees.
No rebates or VIP discounts. Base round-trip cost across the two venues is 29bp of
one-leg notional; realized volatility slippage adds to it. Leg PnL uses reference
prices, with fees and adverse fill differences charged exactly once as execution cost.

During entry <= settlement < exit, funding payment at each venue is
-side*q*mark_open_at_settlement*actual_rate. No funding is earned/paid after the exit
open. Hourly equity is the sum of the two cash wallets and both unrealized PnLs
marked at the respective mark closes. Exit PnL uses trade-kline open, not mark open.

Audit each venue separately every held hour: adverse mark low for the long or mark
high for the short, debit negative current funding before that extreme, receive
positive current funding after that extreme. Margin equity/notional must remain
>=25% in both wallets. Any breach disqualifies the complete candidate even if combined
NAV is positive. A nominal path after a breach is not a valid liquidation simulation.
No transfer-speed, exchange-default, stablecoin-depeg or tick-level legging guarantee.

## Data contract, fixed before full download

Official Bybit V5 historical funding, trade klines and mark-price klines and the
349 checksum-verified Binance USD-M source archives used previously. Reverify cache
hashes. Bybit responses are saved with exact endpoint/query, retrieval timestamp and
local SHA256; local hashes preserve observations, not an exchange-issued checksum.
Use 2021-12-01 through 2026-08-31 inclusive, UTC 1h, with December as signal context.

Require full unique continuous hourly price calendars, positive finite OHLC and
valid high/low bounds. No interpolation, compressed time or wrong-market fallback.
Verify complete BTC/ETH funding at 00/08/16 UTC from source event times through the
whole sample. If a historical interval change or unresolvable event gap appears,
stop and record the contract as BLOCKED-DATA; do not assume missing rates are zero.
Offsets of 0..1000ms can associate an event with its scheduled hour, retaining raw
source bytes. Funding valuation uses that hour's mark open, a timing proxy.

Zero-volume hours may retain reported marks during a passive hold, with no synthetic
fill. Entry/exit requires positive volume on both venues. Untradable cycle boundaries
are reported and block promotion. Inspect a small overlapping API request against
cached page values to check pagination and timestamp alignment before backtesting.

## Evaluation and no retuning

Discovery [2022-01-01,2024-01-01), validation [2024-01-01,2026-01-01), stress
[2026-01-01,2026-09-01), all UTC. 2026 is reused stress history, not pristine holdout.
All six asset-period rows must exist and have net return>0, calendar-hour Sharpe>0,
max drawdown better than -10%, >=6 completed monthly cycles, zero unavailable cycle
boundaries and zero per-venue margin breaches. Months with zero lagged spread are
reported cash months, not silently removed from the calendar. Natural-year returns
from PRIMARY equity, anchored to preceding NAV, must also be positive for all ten
asset-years (2022..2025 and 2026 Jan-Aug).

Report funding, reference-price PnL and execution costs separately. Zero-execution-
cost diagnostics retain the same months/sides, actual funding and wallet rules;
they are derived checks, not additional parameter trials or grounds to reverse failure.

Failure: REJECTED for this fixed family; no 7d/lookback/holding/side/fee/universe tuning.
Data-contract failure: REJECTED with BLOCKED-DATA reason, not an economic falsification.
Historical success: SHADOW only, fixed prospective window [2026-10-01,2027-10-01) UTC,
with >=6 completed cycles per asset, positive return/Sharpe, drawdown>-10% and no
collateral breach/unavailable boundaries. PASS requires the full future window.
Existing three SHADOW source files, starts, parameters and automation remain unchanged.

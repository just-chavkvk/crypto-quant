# Funding-cycle pre-settlement pressure: one fixed trial

Registered on 2026-09-12, Git timestamp authoritative, before inspecting returns.
The two spot/perpetual hypotheses remain REJECTED (BLOCKED-DATA): both spot archives
lack 2023-03-24 13:00 UTC. Do not fill this gap to make a hedged backtest pass.

## Novelty and fixed rule

Some perpetual longs may close before a funding payment, producing temporary selling
pressure before the scheduled boundary. This is a CLOCK-BASED hypothesis, not a claim
that observed traders have that motive. It differs from the rejected negative-funding
rebound, funding-filtered momentum and BTC/ETH post-settlement funding-difference fade:
no funding-rate threshold, price trend, cross-asset spread or contrarian return trigger.

BTCUSDT and ETHUSDT USD-M, 1h. Generate a short signal at completion of the hours
opened at 06:00, 14:00, 22:00 UTC. Enter at the following hourly open (07:00,15:00,23:00)
and exit at the next hourly open (08:00,16:00,00:00), before its funding settlement.
No rate-sign filter. Exactly one fixed clock rule, no UTC-shift/window/side search.

## Data and timing

Use the 349 already checksum-verified official USD-M kline, mark-price and funding
archives from the participation collector, rechecking hashes. Both assets have full
hourly calendars 2021-12 through 2026-08. Verify the known funding regime is 00/08/16
UTC across evaluated history, with no observed settlement inside the held hour.
A regime discrepancy rejects the contract; never silently omit financing.

Both entry and exit must have positive kline volume. Report unavailable boundaries;
any such skipped trade blocks promotion. Signal/entry/exit must lie within each
period; report final-boundary truncation. No missing-price fill or row compression.

## Execution and verdict

Start each asset-period at 10,000 USDT. Fixed 20% of entry equity notional, short,
no leverage increase or position additions. Exit after one actual hour, with a 5%
stop: if held-hour high reaches entry*1.05, exit at that stop with adverse costs and
timestamp hour-end minus1us (an ordering convention, not a measured fill timestamp).
Spot is never traded. No funding cashflow is due with scheduled exit before payment.
Each fill costs 5bp fee + adverse slippage 2bp + previous-completed-bar
(high-low)/open *0.02. Opening slippage cannot use the held candle's future range.
Zero-execution-cost diagnostic retains the same times/sides/stops; not another trial.

Discovery [2022-01-01,2024-01-01), validation [2024-01-01,2026-01-01), stress
[2026-01-01,2026-09-01), UTC; exactly six primary asset-period rows required. All need
net return>0, calendar-hour Sharpe>0, max drawdown better than -10%, >=10 closed trades
and zero unavailable-boundary skips. Annual net returns, calculated from PRIMARY
hourly equity with preceding NAV anchors, must also be positive for each asset/year.
2026 is reused stress history. Any failure is REJECTED; no post-result clock/side/
fee/hold/threshold tuning. Historical success alone is SHADOW, with frozen future
window [2026-09-13,2027-09-13) UTC; PASS only after its full completion and the same
return/risk/sample gates. Existing 3 SHADOW strategies/tracking stay unchanged.

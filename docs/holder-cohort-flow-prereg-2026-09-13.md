# BTC holder-cohort flow regime: preregistration

Registered on 2026-09-13 before downloading candidate feature series or calculating candidate returns. Historical 2026 data is reused stress history and cannot promote the rule without future shadow validation.

Use exactly three Bitview daily series: `lth_supply_delta_1m_rate_ratio`, `sth_supply_delta_1m_rate_ratio`, and `utxos_over_10k_btc_supply_delta_1w_rate_ratio`.

For completed UTC day D, accumulation +1 requires LTH > 0, STH < 0, and the >10k-BTC cohort > 0. Distribution -1 requires all three signs reversed. Otherwise signal 0. Only a transition into a non-zero regime is an event.

No MVRV threshold, price filter, momentum filter, realized-P/L filter, quantile search, alternate wallet bucket, or alternate sign rule belongs to this trial.

Because the daily label lacks a historical publication-time series, event day D enters at the Bitview daily BTC price on D+2 and exits on D+9. Missing prices reject the event. Primary event return is `signal * (exit_price / entry_price - 1) - 0.0014`, a fixed 14 bp round trip.

Evaluation windows: discovery 2022-01-01 through 2023-12-31, validation 2024-01-01 through 2025-12-31, stress 2026-01-01 through 2026-08-31. Report event count, long/short counts, mean and median net signed return, win rate, compounded event return, and worst event return.

Reject if discovery or validation has fewer than 10 completed events, mean net signed return <= 0, or win rate < 50%. If both pass, 2026 remains stress history only and the best possible state is PRE-SCREEN pending future shadow validation.

Use the public Bitview Series API directly. Require equal array lengths, unique ascending dates, finite features, and finite positive entry/exit prices. Record source hashes. Do not tune signs, horizons, lag, holding period, wallet threshold, costs, or asset after seeing results.

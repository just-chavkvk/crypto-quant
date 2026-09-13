# Hyperliquid whale crowding — prospective preregistration

Registered on 2026-09-13 before the first leaderboard/position snapshot is evaluated.
This is a prospective shadow study. Historical winners are not selected and replayed backward.

## Frozen cohort

- Source: Hyperliquid public leaderboard snapshot.
- Minimum account value: 100,000 USDC.
- Require positive 7-day PnL and positive 30-day PnL at registration.
- Rank the remaining accounts by all-time PnL and freeze the top 20 addresses from the first run.
- Later refreshes reuse those same addresses; no replacement for accounts that later lose or close positions.

## Frozen signal

- Query each frozen address with `clearinghouseState` and use only open BTC/ETH perpetual positions.
- Signed notional is `sign(szi) * positionValue`; aggregate across the frozen cohort.
- Crowding score is `sum(signed notional) / sum(abs notional)` separately for BTC and ETH.
- Signal is the sign of the crowding score: positive = long, negative = short, exactly zero = neutral.
- Record the contemporaneous Hyperliquid mid from `allMids` at every snapshot.

## Evaluation

- First snapshot starts the clock; no historical PnL is claimed.
- Evaluate each non-zero BTC/ETH signal on the next 1-day and 7-day mid-price return.
- Do not change the cohort rule, account-value floor, top-20 count, signal direction, horizons, or asset set after seeing outcomes.
- Minimum evidence before any promotion review: at least 30 daily snapshots and at least 10 completed non-zero observations for each evaluated horizon.
- Until then the state is `SHADOW/TRACKING`; it is never paper/live trading approval.

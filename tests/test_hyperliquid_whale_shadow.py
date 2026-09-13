from quant_lab.research.hyperliquid_whale_shadow import (
    LeaderboardEntry,
    WhalePosition,
    aggregate_asset,
    select_frozen_roster,
)


def test_roster_selection_requires_equity_and_positive_week_month_pnl() -> None:
    # Given: profitable and ineligible leaderboard entries with different all-time PnL.
    rows = (
        LeaderboardEntry("0xaaa", 500_000.0, 10.0, 20.0, 5_000.0),
        LeaderboardEntry("0xbbb", 250_000.0, 20.0, 30.0, 9_000.0),
        LeaderboardEntry("0xccc", 50_000.0, 50.0, 50.0, 50_000.0),
        LeaderboardEntry("0xddd", 500_000.0, -1.0, 50.0, 60_000.0),
    )

    # When: the preregistered roster rule is applied.
    selected = select_frozen_roster(rows, minimum_account_value=100_000.0, limit=2)

    # Then: only eligible rows remain and ranking uses all-time PnL.
    assert [row.address for row in selected] == ["0xbbb", "0xaaa"]


def test_asset_aggregation_uses_position_size_sign_and_absolute_notional() -> None:
    # Given: two longs and one larger short in BTC.
    positions = (
        WhalePosition("0xaaa", "BTC", 1.0, 100_000.0),
        WhalePosition("0xbbb", "BTC", 2.0, 50_000.0),
        WhalePosition("0xccc", "BTC", -1.0, 200_000.0),
    )

    # When: crowding is aggregated for BTC.
    result = aggregate_asset(positions, "BTC", mid_price=100_000.0)

    # Then: signed notional is -50k over 350k gross, so the signal is short.
    assert result.long_accounts == 2
    assert result.short_accounts == 1
    assert result.signed_notional == -50_000.0
    assert result.gross_notional == 350_000.0
    assert result.crowding_score == -50_000.0 / 350_000.0
    assert result.signal == -1

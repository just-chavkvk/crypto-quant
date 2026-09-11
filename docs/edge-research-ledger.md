# Edge research ledger

이 파일은 같은 Edge를 모르고 두 번 연구하지 않기 위한 **단일 연구 원장**입니다. 상세 수치와 근거는 날짜별 연구 노트에 두고, 여기에는 무엇을 시험했는지와 다시 볼 가치가 있는지를 빠르게 판별할 정보만 남깁니다.

## 운영 규칙

- 새 연구를 시작하기 전에 이 원장을 먼저 검색합니다.
- 연구 한 묶음이 끝날 때마다 날짜, 가설, 데이터, 시험 수, 판정, 재검토 조건을 기록하고 문서 커밋을 만듭니다.
- `REJECTED`는 동일 데이터·동일 메커니즘·동일 실행 가정으로 재시험하지 않습니다.
- `PRE-SCREEN`은 일부 구간을 통과했지만 Edge 승격 근거가 없다는 뜻입니다. 최종 Edge로 취급하지 않습니다.
- `BLOCKED-DATA`는 아이디어가 나쁜 것이 아니라 현재 데이터 계약으로 공정한 검증이 불가능하다는 뜻입니다.
- 2026 데이터는 이미 여러 연구에서 확인했으므로 더 이상 pristine holdout이 아닙니다. 새 후보의 최종 승격에는 **사전에 기간을 고정한 미래 shadow 구간**이 필요합니다.
- trial 수는 같은 CSV의 행 수 기준입니다. 서로 파생된 CSV끼리는 후보가 겹칠 수 있으므로 파일 간 행 수를 무조건 합산하지 않습니다.
- 대용량 원시/결과 파일은 `artifacts/`에 두고 Git에는 넣지 않습니다. 대신 이 원장에서 파일명과 판정을 연결합니다.

## 판정 상태

| 상태 | 의미 |
| --- | --- |
| `ARCHIVED` | 후속 정식 연구로 대체된 초기 탐색. 중복 탐색 방지용으로만 보존 |
| `REJECTED` | 현재 가설/데이터/실행 가정에서 폐기 |
| `PRE-SCREEN` | 일부 사전 구간 통과. 승격 아님 |
| `NEXT` | 다음 정식 검증 후보 |
| `BLOCKED-DATA` | 데이터 완전성/시점 계약 때문에 검증 보류 |
| `SHADOW` | 역사 검증 후 미래 관찰 중 |
| `PROMOTED` | 미래 shadow까지 통과해 paper 후보로 승격 |

## 연구 이력

| 날짜 | Edge 가족 / 가설 | 시험 범위 | 판정 | 핵심 이유 / 다음 조건 | 근거 |
| --- | --- | --- | --- | --- | --- |
| 2026-09-10 | Momentum trend | 공식 가족 검색 9개 설정 | `REJECTED` | 사전 검증은 가장 강했지만 2026 BTC 1h가 약 -0.20% | `docs/edge-search-2026-09-10.md`, `edge_families.csv` |
| 2026-09-10 | Donchian breakout | 공식 가족 검색 5개 설정 | `REJECTED` | 2026 네 시장 최저 수익 -2.38% | 같은 문서/CSV |
| 2026-09-10 | Volume breakout | 공식 가족 검색 8개 설정 | `REJECTED` | 2026 네 시장 최저 수익 -0.97% | 같은 문서/CSV |
| 2026-09-10 | Volatility breakout | 공식 가족 검색 8개 설정 | `REJECTED` | 2026 네 시장 최저 수익 -3.20% | 같은 문서/CSV |
| 2026-09-10 | Mean reversion / EMA breakout 등 초기 OHLCV 탐색 | `edge_screen_pre_holdout.csv` 63행 중 관련 가족 | `ARCHIVED` | 공식 가족 검색 전 탐색 단계. 동일 조합을 무심코 다시 돌리지 말고 후속 정식 연구 판정을 우선 | `edge_screen_pre_holdout.csv` |
| 2026-09-10 | Negative funding rebound | 12개 | `REJECTED` | 2024~2025 일부 양호, ETH 2022~2023 약 -9%로 붕괴 | `docs/edge-search-2026-09-10.md` |
| 2026-09-10 | OI expansion momentum | 18개 | `REJECTED` | 검증 구간 최소 수익/Sharpe 음수 | 같은 문서 |
| 2026-09-10 | OI flush rebound | 36개 | `REJECTED` | 탐색/2026 stress 안정성 부족 | 같은 문서 |
| 2026-09-10 | Funding-filtered momentum | 36개 | `REJECTED` | 13개가 사전 통과했지만 기존 momentum의 2026 약점 해소 실패 | 같은 문서 |
| 2026-09-10 | OI-filtered momentum | 72개 | `REJECTED` | OI 필터가 성과 악화 | 같은 문서 |
| 2026-09-10 | Funding + OI crowd-filtered momentum | 12개 | `REJECTED` | 네 시장 동시 안정성 부족 | 같은 문서 |
| 2026-09-10 | Positive funding fade short | 12개 | `REJECTED` | 검증 구간부터 손실 | 같은 문서 |
| 2026-09-10 | OI expansion fade short | 48개 | `REJECTED` | 사전 검증 실패 | 같은 문서 |
| 2026-09-10 | Funding + OI crowd fade short | 16개 | `REJECTED` | 사전 검증 실패 | 같은 문서 |
| 2026-09-11 | Taker continuation | 4h 16개 | `REJECTED` | strict pre-4h pass 0/16 | `microstructure_4h_screen.csv` |
| 2026-09-11 | Taker rebound | 4h 16개 | `REJECTED` | strict pre-4h pass 0/16 | 같은 CSV |
| 2026-09-11 | Absolute positioning crowd fade | 4h 24개 | `REJECTED` | strict pre-4h pass 0/24 | 같은 CSV |
| 2026-09-11 | Position divergence follow | 4h 8개 | `REJECTED` | 일부 양수 조합이 있어도 strict pre-4h pass 0/8 | 같은 CSV |
| 2026-09-11 | Premium fade / premium-filtered momentum | 4h 22개 | `REJECTED` | strict pre-4h pass 0/22 | 같은 CSV |
| 2026-09-11 | Premium continuation / extreme fade | pre-stress 24개 | `REJECTED` | 전부 pre-pass 실패 | `premium_edge_screen_pre_stress.csv` |
| 2026-09-11 | Premium filtered momentum | pre-stress 6개 | `REJECTED` | pre-pass 0/6 | 같은 CSV |
| 2026-09-11 | Position-filtered momentum | 4h 6개 | `PRE-SCREEN` | pre-4h 6/6 통과. pristine holdout이 남아 있지 않아 Edge 승격 불가 | `microstructure_4h_screen.csv` |
| 2026-09-11 | Taker-filtered momentum | 4h 6개 | `PRE-SCREEN` | pre-4h 2/6 통과. 미래 shadow 전 승격 금지 | 같은 CSV |
| 2026-09-11 | Position cap filter | 18개 | `PRE-SCREEN` | pre-pass 6/18. 독립 Edge가 아니라 momentum 필터 후보 | `microstructure_momentum_filters_pre_stress.csv` |
| 2026-09-11 | Taker floor filter | 10개 | `PRE-SCREEN` | pre-pass 1/10 | 같은 CSV |
| 2026-09-11 | Taker + positioning combo | 18개 | `REJECTED` | pre-pass 0/18 | 같은 CSV |
| 2026-09-11 | Top-vs-global positioning filter | 6개 | `PRE-SCREEN` | pre-pass 2/6. 절대값보다 변화율/불일치로 재정의할 가치 있음 | 같은 CSV |
| 2026-09-11 | Taker-flow shock × price divergence / absorption | 초기 연구 설계 | `ARCHIVED` | 아래 정식 사전 등록·실행 결과로 대체 | `docs/edge-search-2026-09-11.md` |
| 2026-09-11 | Taker-flow shock × price divergence / absorption → flow 반대 방향 | 사전 등록 6개 후보, BTC/ETH × 5m/15m | `REJECTED` | 6/6 pre-stress 실패. 가장 덜 나쁜 4h strict 후보도 discovery 최저 -4.19%, validation 최저 -2.10% / Sharpe -1.27. 비용 0에서도 ETH 양 timeframe 음수 | `docs/edge-search-2026-09-11.md`, `taker_divergence_*csv` |
| 2026-09-11 | 같은 자산 Long/Short velocity / acceleration + OI/price state | 사전 등록 144개, BTC/ETH 1h | `REJECTED` | pre-pass 0/144. 양수 조합은 표본 부족·비용 민감성·연도별 반전. OI value 144개와 account-position disagreement 72행도 회복 실패 | `docs/edge-search-2026-09-11.md`, `ls_velocity_*csv` |
| 2026-09-11 | BTC global positioning/OI shock → ETH cross-asset lead-lag | 사전 등록 2개 hold | `REJECTED` | pre-pass 0/2. 4h는 validation +10.75%였지만 discovery -0.38%, 2026 stress -1.21%. 비용 0 discovery +3.17%로 gross 반응은 있으나 평균 +0.129%/trade가 왕복 비용 약 0.14% 미만 | `docs/edge-search-2026-09-11.md`, `cross_asset_lead_lag_*csv` |
| 2026-09-11 | BTC top-trader position velocity/OI shock → ETH cross-asset lead-lag | 사전 등록 2개 hold | `REJECTED` | pre-pass 0/2. 1h discovery -13.07% / validation -19.22%, 4h discovery -7.70% / validation -22.15%, 2026 stress -19.66%. 비용 0에서도 4h discovery -1.96% / validation -13.88%라 gross 방향성도 약함 | `docs/edge-search-2026-09-11.md`, `top_trader_position_lead_lag_*csv` |
| 2026-09-11 | BTC positioning shock → ETH/BTC catch-up pair | global/top-position × 1h/4h, 4개 사전 등록 | `REJECTED` | 0/4 pre-pass. 가장 덜 나쁜 top-position 4h도 discovery -7.46%, validation -11.72%, 2026 -2.65%. 비용 0에서도 discovery -0.61% | `docs/edge-search-2026-09-11.md`, `relative_value_wave_*csv` |
| 2026-09-11 | BTC/ETH premium + OI relative crowding fade | 1h/4h, 2개 사전 등록 | `REJECTED` | 0/2 pre-pass. 4h discovery -10.61%, validation -45.33%, 2026 -11.40%. 비용 0도 validation -15.82% | `docs/edge-search-2026-09-11.md`, `relative_value_wave_*csv` |
| 2026-09-11 | BTC/ETH taker relative chase fade | 1h/4h, 2개 사전 등록 | `REJECTED` | 0/2 pre-pass. 4h discovery -17.41%, validation -45.34%, 2026 -18.48%. 비용 0도 validation -5.99% | `docs/edge-search-2026-09-11.md`, `relative_value_wave_*csv` |
| 2026-09-11 | BTC/ETH funding settlement differential fade | pure/premium-confirmed × 1h/4h, 4개 사전 등록 | `REJECTED` | 0/4 pre-pass. best pure 4h도 discovery -16.19%, validation -27.51%, 2026 -7.86%. 비용 0 validation -10.66%, 연도별 전부 음수 | `docs/edge-search-2026-09-11.md`, `funding_relative_value_*csv` |
| 2026-09-11 | Global-position cap momentum q90 / 2160h | BTC/ETH × 1h/4h 정식화 | `SHADOW` | 정식 재현에서 discovery/validation/2026 stress 네 데이터셋 모두 양수. 2026 stress: BTC1h +2.04%, ETH1h +4.11%, BTC4h +2.22%, ETH4h +2.57%. 기존 탐색에서 2026을 이미 확인했으므로 2026-09-11 이후 새 데이터만 최종 증거로 사용 | `docs/edge-search-2026-09-11.md`, `position_cap_momentum_*csv` |
| 2026-09-11 | BTC/ETH relative-strength rotation | 168h relative momentum + EMA400, daily rebalance, 1h/4h | `REJECTED` | 1h/4h 모두 discovery 약 -4.5%~-4.9%. validation +14.5%, 2026 +34.7%로 최근 regime은 강했지만 multi-regime 사전 기준 실패 | `docs/edge-search-2026-09-11.md`, `relative_strength_rotation_*csv` |
| 2026-09-11 | BTC/ETH breadth-confirmed momentum | 기존 336h/EMA400 momentum + 양 자산 EMA400 breadth, BTC/ETH × 1h/4h | `SHADOW` | discovery/validation 네 데이터셋 전부 통과, 2026 stress도 모두 양수. 다만 BTC1h 2026 +0.09% / Sharpe +0.05로 margin이 얇아 2026-09-11 이후 future shadow 필요 | `docs/edge-search-2026-09-11.md`, `breadth_momentum_*csv` |
| 2026-09-11 | BTC/ETH high-correlation relative-shock fade | corr168h >= 0.70 + relative return 24h z>=2, hold24h | `REJECTED` | discovery -14.89%, validation -21.72%, 2026 -11.73%. 비용 0도 discovery -1.95%, validation -9.43%라 mean-reversion 방향 자체가 약함 | `docs/edge-search-2026-09-11.md`, `relative_shock_fade_*csv` |
| 2026-09-11 | BTC price shock → lagging ETH continuation | BTC 1h return prior-720h z>=2 + ETH same-direction underreaction <=50%, hold4h | `REJECTED` | discovery +9.73%였지만 validation -4.96% / Sharpe -1.48, 2026 -4.33%. 비용 0 validation은 +2.66%지만 평균 +7.1bp/trade로 왕복 비용 약 14bp 미만이고 2026 비용 0도 -2.84% | `docs/edge-search-2026-09-11.md`, `price_lead_lag_*csv` |
| 2026-09-11 | Weekend move → Monday reversal | 주말 48h 수익 반대 방향, 월요일 00:00 UTC 진입, hold24h, BTC/ETH × 1h/4h | `REJECTED` | discovery/validation 8/8 구간 음수. 비용 0도 모두 음수. 2026만 +1.28%~+3.31%라 최근 regime에만 나타난 효과 | `docs/edge-search-2026-09-11.md`, `weekend_reversal_*csv` |
| 2026-09-11 | Extreme wick rejection | 현재 range >= prior 168h median ×2, 한쪽 wick >= range 50%, wick 반대 방향, hold4h | `REJECTED` | 비용 포함 discovery/validation/2026 전 데이터셋 음수. 비용 0도 구간별 부호 반전으로 안정성 없음 | `docs/edge-search-2026-09-11.md`, `wick_rejection_*csv` |
| 2026-09-11 | Low-volatility managed momentum | 336h momentum + EMA400, recent 24h realized vol <= prior 2160h median | `REJECTED` | 비용 포함 discovery/validation 8/8 음수. 비용 0도 ETH1h/BTC4h/ETH4h discovery 음수라 multi-regime 안정성 없음 | `docs/edge-search-2026-09-11.md`, `volatility_managed_momentum_*csv` |
| 2026-09-11 | High-correlation gated momentum | 336h momentum + EMA400 + BTC/ETH 168h return corr >= 0.70, BTC/ETH × 1h/4h | `REJECTED` | discovery/validation 8/8 통과했지만 2026 stress에서 BTC1h -0.20%, ETH4h -0.03%. 비용 0 stress는 4/4 양수라 gross 효과는 있으나 현재 실행비용에서 margin 부족 | `docs/edge-search-2026-09-11.md`, `correlation_gated_momentum_*csv` |
| 2026-09-11 | Liquidity-impact shock fade | `abs(log return)/(volume×close)` prior 720h q95 이상 → 반대 방향 hold4h, BTC/ETH × 1h/4h | `REJECTED` | 비용 포함 discovery/validation/2026 전 데이터셋 음수. 비용 0에서도 BTC/ETH 4h validation과 2026이 음수라 thin-liquidity fade 방향이 multi-regime에서 불안정 | `docs/edge-search-2026-09-11.md`, `liquidity_impact_fade_*csv` |
| 2026-09-11 | Trend-efficiency gated momentum | 336h momentum + EMA400 + 168h log-price efficiency ratio >= 0.25, BTC/ETH × 1h/4h | `REJECTED` | BTC와 4h는 대체로 양수였지만 ETH1h discovery -4.45%, 비용 0도 -3.02%. 2026 1h 거래 수 1~2건으로 표본도 부족 | `docs/edge-search-2026-09-11.md`, `trend_efficiency_momentum_*csv` |
| 2026-09-11 | Signed-volume confirmed momentum | 336h momentum + EMA400 + 168h signed-volume balance >= +0.10, BTC/ETH × 1h/4h | `REJECTED` | 7/8 discovery·validation 구간 양수, 2026 4/4 양수였지만 BTC4h discovery -0.19%. 비용 0에서는 +4.33%라 gross 방향성은 있으나 현재 실행비용에서 strict 기준 실패 | `docs/edge-search-2026-09-11.md`, `signed_volume_momentum_*csv` |
| 2026-09-11 | OI-turnover confirmed momentum | 336h momentum + EMA400 + 24h volume/current OI >= prior 2160h median, BTC/ETH × 1h/4h | `REJECTED` | discovery/validation 8/8 통과. 2026 stress에서 BTC1h -0.64%, BTC4h -0.68%. 비용 0은 전 구간 양수지만 BTC4h stress +0.07%로 margin이 너무 얇음 | `docs/edge-search-2026-09-11.md`, `turnover_momentum_*csv` |
| 2026-09-11 | Premium-stability confirmed momentum | 336h momentum + EMA400 + 24h premium std <= prior 2160h median, BTC/ETH × 1h/4h | `REJECTED` | discovery/validation 8/8 음수. 비용 0에서도 BTC4h discovery, ETH4h validation, BTC4h 2026이 음수라 gross 안정성도 없음 | `docs/edge-search-2026-09-11.md`, `premium_stability_momentum_*csv` |
| 2026-09-11 | Dual-confirmed momentum | frozen breadth-confirmed momentum AND global-position cap momentum, BTC/ETH × 1h/4h | `SHADOW` | discovery/validation 8/8 통과, 2026 stress도 4/4 양수: +2.65%, +2.75%, +2.57%, +1.45%. 기존 두 SHADOW의 역사 결과를 이미 본 뒤 만든 composite이므로 2026-09-11 08:00 UTC 이후 새 데이터만 최종 증거로 사용 | `docs/edge-search-2026-09-11.md`, `dual_confirmed_momentum_*csv` |
| 2026-09-11 | Liquidation burst | 데이터 조사 | `BLOCKED-DATA` | Binance USD-M 역사 liquidationSnapshot이 2024-03-31 이후 끊겼고 forceOrder도 완전한 이벤트 테이프가 아님 | 같은 문서 |

## 다음 연구 순서

1. global-position cap momentum q90 / 2160h는 future shadow에서 파라미터를 동결해 관찰합니다.
2. BTC/ETH breadth-confirmed momentum도 파라미터 동결 상태로 future shadow에서 관찰합니다.
3. dual-confirmed momentum은 2026-09-11 08:00 UTC 이후 future shadow에서 두 component의 frozen rule을 그대로 유지합니다.
4. OI-turnover와 premium-stability momentum은 동일 family의 threshold/window 재튜닝 없이 닫습니다.
5. relative-strength rotation과 high-correlation relative-shock fade도 동일 family 재튜닝 없이 닫습니다.
6. BTC price shock → lagging ETH continuation은 같은 z/underreaction/hold 조정으로 재시험하지 않습니다. 실제 체결·호가처럼 시점 계약이 달라지거나 target universe가 달라질 때만 재검토합니다.
7. global/top-position ETH outright, BTC/ETH relative-value, funding differential 가족의 threshold/lookback/holding 조정은 반복하지 않습니다.
8. Liquidation은 완전한 historical event source를 확보하기 전까지 정식 백테스트를 시작하지 않습니다.
9. 다음 새 정식 후보는 기존 `REJECTED`와 다른 데이터 계약 또는 경제 메커니즘으로 사전 등록합니다.

## Future shadow 운영 상태

- 공통 실행: `uv run python -m quant_lab.research.shadow_status --root artifacts/edge_search --refresh`
- 2026-09-11 첫 refresh 후 공통 최신 완성 bar: `2026-09-11 00:00 UTC`
- global-position cap momentum: `TRACKING`, 4/4 데이터셋 평가 시작, 최소 거래 수 0
- BTC/ETH breadth-confirmed momentum: `TRACKING`, 4/4 데이터셋 평가 시작, 최소 거래 수 0
- dual-confirmed momentum: `WAITING_FOR_DATA`, shadow 시작 `2026-09-11 08:00 UTC`, 최소 거래 수 0
- `READY_FOR_PAPER_REVIEW`가 되기 전까지 `PROMOTED` 또는 paper/live 연결 금지

## 커밋 규칙

- 연구 설계/결과 기록: `docs: record <edge> edge research`
- 데이터 수집기/전략/백테스터 구현: 기능별 별도 커밋
- 실험 결과가 바뀌면 원장의 기존 행을 지우지 말고 새 날짜 행을 추가해 이유와 변경된 데이터/가정을 남깁니다.

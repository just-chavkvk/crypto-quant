# Derivatives microstructure Edge research — 2026-09-11

Funding/OI의 단순 방향성 가설 다음에 무엇을 연구할지 조사하고, 현재 로컬 artifact에 남아 있는 미시구조 실험도 함께 복구해 정리했습니다.

## 결론

Taker-flow absorption, 같은 자산의 Long/Short 변화속도·가속도 + OI/가격 상태, BTC global positioning/OI shock → ETH lead-lag, BTC top-trader position velocity/OI shock → ETH lead-lag는 정식 검증에서 모두 탈락했습니다. Liquidation burst는 신뢰할 수 있는 역사 데이터가 없어 계속 보류합니다.

top-trader position source는 비용을 제거해도 discovery와 validation이 모두 음수여서 global-ratio 실험보다 더 약했습니다. BTC/ETH 상대가치 wave 8개와 funding settlement 상대가치 wave 4개도 전부 pre-pass에 실패했습니다. 같은 source에서 threshold/lookback/holding만 바꾼 재시험은 하지 않습니다.

## 이미 수행된 미시구조 실험

`artifacts/edge_search/microstructure_4h_screen.csv` 기준:

| 가족 | 시험 수 | strict pre-4h 통과 | 판정 |
| --- | ---: | ---: | --- |
| taker continuation | 16 | 0 | REJECTED |
| taker rebound | 16 | 0 | REJECTED |
| position crowd fade | 24 | 0 | REJECTED |
| position divergence follow | 8 | 0 | REJECTED |
| premium fade | 16 | 0 | REJECTED |
| premium-filtered momentum | 6 | 0 | REJECTED |
| position-filtered momentum | 6 | 6 | PRE-SCREEN only |
| taker-filtered momentum | 6 | 2 | PRE-SCREEN only |

`microstructure_momentum_filters_pre_stress.csv`에서는 position cap 6/18, taker floor 1/10, top-vs-global 2/6이 사전 기준을 통과했고 taker+position combo는 0/18이었습니다. 이 결과는 최종 Edge 승격이 아니라 후속 가설을 좁히는 용도로만 사용합니다.

## 1. Taker-flow shock × price divergence / absorption

Binance USD-M futures kline에는 전체 volume과 taker-buy base/quote volume이 포함되어 있으므로 과거 데이터를 제3자 공급자 없이 재구성할 수 있습니다.

기본 예시는 다음처럼 닫힌 봉에서 계산합니다.

```text
taker_sell_quote = quote_volume - taker_buy_quote_volume
signed_flow = taker_buy_quote_volume - taker_sell_quote
flow_imbalance = signed_flow / quote_volume
```

새 가설은 “매수가 많으면 오른다”가 아니라 **공격적 주문량에 비해 가격이 얼마나 덜/더 반응했는지**입니다.

- 극단적 sell flow인데 하락 반응이 약함: sell absorption 후보
- 극단적 buy flow인데 상승 반응이 약함: buy absorption 후보
- 극단적 flow와 가격, OI가 같은 방향으로 움직임: toxic-flow continuation 후보

5m/15m feature를 완전히 닫은 뒤 다음 bar부터만 거래하고, 15m/1h/4h forward return을 먼저 event study로 확인합니다. 같은 봉의 종가를 진입가로 사용하지 않습니다.

## 2. Long/Short 변화속도

Global account ratio, top-trader account ratio, top-trader position ratio는 서로 다른 모집단/가중치를 측정합니다. 절대 수준을 다시 contrarian 신호로 쓰지 않고 다음처럼 변화 자체를 봅니다.

```text
x_t = log(long_short_ratio_t)
velocity = x_t - x_{t-k}
acceleration = velocity_t - velocity_{t-k}
```

rolling mean/std/quantile은 현재 관측치를 제외한 과거 데이터만 사용합니다. 주요 후보는 다음입니다.

- positioning velocity와 가격, OI 증가가 같은 방향일 때 추세 지속
- 가격과 positioning이 급변하면서 OI가 감소할 때 deleveraging 이후 continuation/rebound 비교
- top-trader account와 position ratio의 변화가 반대로 갈 때 disagreement state
- BTC positioning 급변이 ETH에 선행하는지 cross-asset 전이

Binance Data Vision의 5분 metrics는 사용할 수 있지만 결측/중복과 실제 이용 가능 시점을 검증해야 합니다. bar timestamp와 데이터가 실제로 관측 가능한 `available_at`을 같은 것으로 가정하지 않습니다.

## 3. Liquidation burst 보류 이유

Binance USD-M `liquidationSnapshot` 공개 아카이브는 2024-03-31 이후 업데이트가 끊겼다는 공개 이슈가 있고, 2025-01-01 BTCUSDT 파일 직접 확인에서도 metrics/5m kline은 HTTP 200이지만 USD-M liquidationSnapshot은 HTTP 404였습니다.

실시간 `forceOrder` stream도 짧은 시간에 발생한 모든 청산을 완전한 이벤트 테이프로 보장하지 않으므로, 이를 이용해 과거 `count`나 `sum(notional)`을 실제 총청산량처럼 백테스트하지 않습니다. 신뢰할 수 있는 complete-event source를 확보할 때 다시 엽니다.

## 검증 규칙

- 2026은 이미 여러 번 확인했으므로 pristine holdout이 아니라 stress history입니다.
- 모든 feature는 닫힌 source bar만 사용하고 진입은 다음 bar 이후입니다.
- metrics 결측을 미래값으로 선형 보간하지 않습니다.
- threshold/lookback/holding period를 바꿀 때마다 trial ledger에 포함합니다.
- 짧은 horizon은 기존 5 bps fee + 2 bps base slippage보다 실제 spread/impact에 더 민감하므로 break-even cost도 함께 계산합니다.
- 역사 walk-forward 생존 후보도 최종 Edge로 부르지 않고, 사전 등록한 새로운 future shadow period를 통과해야 paper 후보로 승격합니다.

## Taker-flow divergence 백테스트 사전 등록

결과를 보기 전에 첫 정식 검증 규칙을 다음과 같이 고정합니다.

- 데이터: Binance USD-M BTCUSDT / ETHUSDT 공식 futures kline
- 시간봉: 5m, 15m
- discovery: 2020-01-01 ~ 2023-12-31
- validation: 2024-01-01 ~ 2025-12-31
- 2026: stress check 전용
- flow imbalance: `2 * taker_buy_quote_volume / quote_volume - 1`
- 표준화: 직전 24시간의 완전히 닫힌 bar만 사용한 mean/std; 현재 bar는 기준 통계에서 제외
- 주 absorption 조건: `|flow_z| >= 2.0`이면서 같은 방향 price-return z-score가 `0.5` 이하
- 민감도 조건: `|flow_z| >= 2.5`이면서 같은 방향 price-return z-score가 `0.0` 이하
- 주 방향 가설: 공격적 flow를 받아낸 반대편 유동성이 이긴다고 보고 flow의 반대 방향으로 진입
- 진입: 신호 bar 다음 bar open
- 보유: 15m, 1h, 4h
- 겹치는 이벤트: 기존 포지션 보유 중 새 이벤트는 무시
- 비용: 기존 연구와 동일하게 fee 5 bps, base slippage 2 bps, volatility slippage multiplier 0.02
- 리스크: 거래당 1%, stop loss 5%

주 방향 가설이 실패하고 같은-flow 방향 수익률이 좋아 보여도 이번 결과에서 즉시 방향을 뒤집어 Edge로 승격하지 않습니다. 그 경우 별도 가설로 다시 사전 등록한 뒤 검증합니다.

## Taker-flow divergence 실제 백테스트 결과

사전 등록한 규칙 그대로 공식 Binance USD-M 월별 futures kline을 내려받아 실행했습니다.

- 데이터 범위: 2020-01-01 ~ 2026-08-31
- 데이터셋: BTCUSDT / ETHUSDT × 5m / 15m
- 누락 candle: 네 데이터셋 모두 0
- 중복 timestamp: 네 데이터셋 모두 0
- 2020~2021 월별 파일은 헤더가 없고 2022년 이후 파일은 헤더가 있으므로 두 형식을 구분해 결합
- 후보 수: 주 조건 / strict 조건 × 15m / 1h / 4h 보유 = 6개
- 2026 결과는 후보 선택에 사용하지 않고, 2020~2025 결과로 1개를 고른 뒤 stress check만 수행

### 2020~2025 사전 판정

| 후보 | Discovery 최저 수익 | Validation 최저 수익 | Validation 최저 Sharpe | Validation 최소 거래 수 | 판정 |
| --- | ---: | ---: | ---: | ---: | --- |
| strict 2.5σ / response 0σ / 4h | -4.19% | -2.10% | -1.27 | 11 | FAIL |
| strict 2.5σ / response 0σ / 1h | -1.80% | -3.00% | -2.73 | 11 | FAIL |
| strict 2.5σ / response 0σ / 15m | -2.28% | -1.50% | -3.19 | 11 | FAIL |
| primary 2σ / response 0.5σ / 4h | -55.22% | -26.82% | -3.45 | 576 | FAIL |
| primary 2σ / response 0.5σ / 1h | -61.95% | -38.93% | -9.71 | 687 | FAIL |
| primary 2σ / response 0.5σ / 15m | -66.98% | -45.83% | -21.04 | 738 | FAIL |

사전 구간에서 한 후보도 엄격한 통과 기준을 만족하지 못했습니다. 결과를 보기 전에 정한 규칙에 따라 가장 덜 나쁜 `strict 2.5σ / response 0σ / 4h` 조합만 2026 stress 구간을 열었습니다.

### 사전 1위 후보의 2024~2025 세부 결과

| 데이터셋 | 수익 | Sharpe | 거래 수 |
| --- | ---: | ---: | ---: |
| BTCUSDT 5m | -0.44% | -0.32 | 23 |
| BTCUSDT 15m | -0.01% | -0.00 | 11 |
| ETHUSDT 5m | -1.51% | -0.68 | 45 |
| ETHUSDT 15m | -2.10% | -1.27 | 20 |

### 2026 stress check

| 데이터셋 | 수익 | Sharpe | 거래 수 |
| --- | ---: | ---: | ---: |
| BTCUSDT 5m | -0.59% | -0.69 | 40 |
| BTCUSDT 15m | -1.26% | -2.50 | 18 |
| ETHUSDT 5m | -1.55% | -1.43 | 35 |
| ETHUSDT 15m | -0.48% | -0.66 | 19 |

### 비용 0 진단

같은 사전 1위 후보의 2024~2025 구간에서 fee/slippage를 0으로 둔 진단도 수행했습니다. BTC 5m/15m은 각각 약 +0.24%, +0.34%였지만 ETH 5m/15m은 약 -0.17%, -1.47%였습니다. 즉 비용이 전부 사라져도 BTC/ETH에 공통으로 유지되는 방향성 Edge가 아니었습니다.

### 판정

**`Taker-flow shock × 가격 divergence/absorption → flow 반대 방향` 가설은 REJECTED입니다.**

강한 공격 주문을 가격이 흡수하면 반대편 유동성이 이후에도 이긴다는 주가설은 discovery/validation에서 재현되지 않았고 2026 stress에서도 네 데이터셋 모두 손실이었습니다. 결과를 본 뒤 같은-flow 방향으로 뒤집어 성공으로 취급하지 않습니다. 같은-flow continuation을 다시 보려면 별도 가설로 사전 등록해야 합니다.

재현 결과 파일:

- `artifacts/edge_search/taker_divergence_summary_pre_stress.csv`
- `artifacts/edge_search/taker_divergence_details_pre_stress.csv`
- `artifacts/edge_search/taker_divergence_champion_stress_2026.csv`
- `artifacts/edge_search/taker_divergence_champion_validation_zero_cost.csv`

## Long/Short velocity / acceleration 백테스트 사전 등록

다음 연구는 절대 Long/Short ratio 수준을 신호로 쓰지 않고, ratio의 로그 변화속도와 가속도에 OI/가격 상태를 결합한다. 결과를 보기 전에 아래 범위와 판정 규칙을 고정한다.

- 데이터: Binance USD-M `metrics` 5분 자료와 같은 거래소의 1시간 선물 kline
- 대상: BTCUSDT / ETHUSDT
- 1시간 metrics 관측값: 각 시간의 닫힌 시간봉에 해당하는 `:55` 5분 snapshot만 사용. `:55`가 없거나 필드가 비어 있으면 그 시간을 채우지 않고 제외
- ratio series: global account ratio, top-trader account ratio, top-trader position ratio 및 세 series의 median velocity composite
- feature: `x_t = log(ratio_t)`, `velocity_L = x_t - x_{t-L}`, `acceleration_L = velocity_L(t) - velocity_L(t-L)`
- 표준화: 현재 관측치를 제외한 직전 720개 시간 관측치의 mean/std. 720개가 완전하지 않으면 해당 z-score를 사용하지 않음
- OI 상태: `sum_open_interest` 계약 수의 `L`시간 로그 변화. OI value는 가격과 중복될 수 있어 주 신호에서 사용하지 않음
- 가격 상태: 1시간 close의 `L`시간 로그 변화
- lookback: `L ∈ {4h, 12h, 24h}`
- velocity threshold: `|velocity_z| >= 2.0`
- acceleration threshold: `|acceleration_z| >= 1.0`
- holding: `H ∈ {4h, 12h, 24h}`
- 후보 가족: velocity/acceleration 동방향 + price/OI 동방향 continuation, velocity/acceleration 동방향 + OI 반대방향 continuation, acceleration 반전 + price/OI 동방향 reversal, acceleration 반전 + OI 반대방향 reversal
- source × family × lookback × holding으로 4 × 4 × 3 × 3 = 144개 조합을 사전 등록
- 신호 계산은 현재 시간봉이 닫힌 뒤, 진입은 다음 1시간 봉 open, 청산은 진입 후 H시간 뒤 open
- 보유 중 겹치는 이벤트는 무시
- 비용: 왕복 fee 5 bps + base slippage 2 bps, 즉 거래당 최소 14 bps. 이 단계는 고정 보유 event/backtest이므로 stop/volume cap은 적용하지 않으며, 통과 후보만 기존 엔진의 risk/stop 계약으로 재검증
- 탐색: 2023년, 검증: 2024~2025년, 2026년은 champion을 고른 뒤 stress 확인 전용
- 사전 통과: BTC/ETH 양쪽에서 discovery 수익률 > 0, validation 수익률 > 0, validation Sharpe > 0, validation 거래 수 ≥ 10
- 2026년 수익률은 후보 선택이나 방향 전환에 사용하지 않음

세 series의 top-account velocity와 top-position velocity가 반대인 disagreement 이벤트는 별도 진단으로 기록하되, 본 144개 champion 선정에 섞지 않는다. 결측 metrics를 forward-fill하거나 gap을 lookback bar로 건너뛰지 않는다.

## Long/Short velocity / acceleration 실제 결과

사전 등록한 144개 조합을 BTCUSDT와 ETHUSDT에 적용했습니다. 결과 CSV는 144행이 모두 고유하며 4개 source × 4개 family × 3개 lookback × 3개 holding의 전체 조합을 포함합니다. 사전 통과 후보는 **0/144**였습니다.

### 데이터 계약과 품질

- 공식 Binance USD-M metrics의 `count_long_short_ratio`, `count_toptrader_long_short_ratio`, `sum_toptrader_long_short_ratio`와 계약 수 OI를 사용했습니다.
- top-account와 top-position series는 2022년에 장기간 비어 있어 2023년을 discovery로 고정했습니다.
- 1시간마다 `:55` snapshot만 사용했고, 누락된 시간이나 필드는 채우지 않았습니다.
- 검증 artifact는 `ls_velocity_acceleration_summary_pre_stress.csv` 144행, `ls_velocity_acceleration_champions_stress_2026.csv` 8행, `ls_velocity_disagreement_diagnostic.csv` 72행입니다.

### 가족별 결과

| 가족 | 사전 최고 조합 | Discovery 최저 수익 | Validation 최저 수익 | Validation 최소 거래 | 판정 |
| --- | --- | ---: | ---: | ---: | --- |
| OI build continuation | top-account, 4h velocity, 4h hold | -4.49% | +2.34% | 6 | discovery 손실·표본 부족 |
| OI cover continuation | median composite, 4h velocity, 4h hold | +0.68% | +4.38% | 8 | 최소 거래 수 미달 |
| OI build reversal | 유효 champion 없음 | — | — | 0 | 이벤트 부족 |
| OI cover reversal | 유효 champion 없음 | — | — | 0 | 이벤트 부족 |

수익 부호 기준으로 discovery와 validation을 모두 통과한 조합은 `median composite / cover continuation / 4h lookback / 4h hold` 하나뿐이었습니다. 그러나 discovery 거래가 BTC 5건, ETH 1건이고 validation도 BTC 8건, ETH 10건이어서 사전 등록한 최소 표본 조건을 넘지 못했습니다. 2026 stress에서도 BTC -0.45%, ETH +0.54%로 방향이 갈렸고 각각 3건뿐이었습니다.

최소 validation 거래 수 10건을 만족한 21개 조합 중 가장 가까운 후보는 `global ratio / cover continuation / 4h lookback / 12h hold`였습니다. Validation은 BTC +19.36%, ETH +3.91%였지만 discovery의 ETH가 -0.49%였습니다. 연도별로도 ETH는 2024 +8.70%에서 2025 -4.41%, 2026 -0.51%로 뒤집혔고 BTC도 2026 -2.11%였습니다. 여러 해에 유지되는 Edge로 볼 수 없습니다.

### 비용과 OI 정의 민감도

`global ratio / cover continuation / 4h lookback / 4h hold`는 현재 비용에서 discovery BTC +1.15%, ETH -0.02%, validation BTC +14.22%, ETH +1.79%였습니다. fee와 slippage를 0으로 두면 discovery BTC +4.61%, ETH +0.82%, validation BTC +16.79%, ETH +3.66%였습니다. gross 방향성은 보이지만 ETH discovery의 거래당 평균 gross 수익 약 0.137%가 가정한 최소 왕복 비용 0.14%보다 작아, 현재 실행 가정에서는 거래 가능한 Edge가 아닙니다.

계약 수 OI를 명목가치 OI로 바꾼 별도 민감도 144개도 사전 통과 0개였습니다. 명목가치 OI의 가장 나은 충분표본 build 후보는 discovery BTC -7.99%, ETH -5.37%였고, cover 후보도 discovery BTC -8.40%, ETH -4.59%였습니다. 가격이 포함된 OI value로 바꿔도 결론은 회복되지 않았습니다.

### Top-account와 top-position 불일치

불일치 진단 72행도 승격할 후보가 없었습니다. `position-follow / 12h lookback / 4h hold`는 validation BTC +1.06%, ETH +0.51%였지만 discovery BTC -7.25%였고 validation 거래도 각각 3건과 4건뿐이었습니다. `account-follow / 12h lookback / 24h hold`도 validation은 양수였으나 discovery ETH -1.83%, validation 거래 3건씩에 그쳤습니다.

### 판정

**`같은 자산의 Long/Short velocity/acceleration + OI/price state` 가족은 REJECTED입니다.**

현재 데이터·비용·실행 가정에서 144개 중 사전 통과가 없었고, 양수로 보이는 조합은 표본 부족·비용 민감성·연도별 방향 전환 중 하나 이상을 피하지 못했습니다. 같은 source와 같은 자산에서 threshold/lookback/holding만 바꿔 재시험하지 않습니다. 재검토하려면 cross-asset 전달, 더 낮은 실제 체결비용의 입증, 또는 새로운 미래 데이터처럼 메커니즘이나 실행 계약이 실질적으로 달라져야 합니다.

다음 후보는 BTC의 global positioning velocity와 OI 감소 shock가 ETH의 다음 1h/4h 수익에 선행하는지 보는 cross-asset lead-lag입니다. BTC 신호가 닫힌 뒤 ETH 다음 봉에서만 진입하도록 시점을 고정하고, 이번 결과에서 상대적으로 나았던 4h velocity를 새 결과를 보기 전에 하나의 기준값으로 사전 등록하는 것이 적절합니다.

## BTC positioning/OI shock → ETH cross-asset lead-lag 사전 등록

같은 자산 Long/Short 가족의 결과를 보고 threshold를 다시 조정하지 않고, 정보가 BTC에서 ETH로 전달되는지 별도 가설로 검증합니다. 결과를 보기 전에 아래 규칙을 고정합니다.

- source asset: BTCUSDT
- target asset: ETHUSDT
- source data: Binance USD-M BTCUSDT 5분 metrics의 매시간 `:55` snapshot + BTCUSDT 1시간 futures kline
- target data: Binance USD-M ETHUSDT 1시간 futures kline
- positioning source: global account long/short ratio만 사용
- lookback: 4시간으로 고정
- velocity: `log(global_ratio_t) - log(global_ratio_{t-4h})`
- acceleration: `velocity_t - velocity_{t-4h}`
- 표준화: 현재 관측치를 제외한 직전 720개 시간의 완전한 관측치만 사용
- shock threshold: `|velocity_z| >= 2.0` 및 `|acceleration_z| >= 1.0`
- BTC state: velocity와 acceleration, BTC 4시간 가격 변화가 같은 방향이고 계약 수 OI 4시간 변화는 반대 방향인 deleveraging/cover state
- ETH 방향 가설: BTC positioning velocity 방향을 ETH가 뒤따른다
- holding: 1시간과 4시간의 2개 사전 등록 trial
- signal time: BTC의 해당 1시간 봉이 완전히 닫힌 뒤
- entry: 다음 ETH 1시간 봉 open
- exit: 진입 후 각각 1시간/4시간 뒤 ETH open
- 보유 중 겹치는 이벤트는 무시
- 결측 시계열은 forward-fill하지 않고 완전한 시간 grid에서 해당 feature를 결측 처리
- 비용: 기존과 동일하게 편도 fee 5 bps + slippage 2 bps, 왕복 최소 약 14 bps
- discovery: 2023-01-01 ~ 2023-12-31
- validation: 2024-01-01 ~ 2025-12-31
- 2026-01-01 ~ 2026-08-31은 두 trial의 pre-stress 결과로 champion을 고른 뒤에만 stress history로 확인
- pre-pass: discovery와 validation 모두 수익률 > 0, Sharpe > 0, 거래 수 >= 10
- champion: pre-pass 우선, 이후 `validation Sharpe + 0.25 * validation return`; 동률이면 1시간 hold 우선
- 비용 0 결과는 판정을 뒤집는 용도가 아니라 실행비용 민감도 진단으로만 사용

이 가설이 실패하면 BTC global positioning/OI → ETH 전달을 같은 threshold나 holding만 바꿔 반복하지 않습니다. 재검토는 source series 변경, 다른 target asset, 또는 독립적인 새 미래 데이터처럼 정보 전달 메커니즘이 달라질 때만 엽니다.

## BTC positioning/OI shock → ETH cross-asset lead-lag 실제 결과

사전 등록한 1시간/4시간 hold 두 trial은 모두 pre-pass에 실패했습니다.

| Hold | Discovery | Sharpe | 거래 수 | Validation | Sharpe | 거래 수 | 판정 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1h | -3.55% | -15.35 | 31 | -0.003% | +0.31 | 17 | discovery/validation 수익 실패 |
| 4h | -0.38% | -0.58 | 25 | +10.75% | +17.90 | 16 | discovery 실패 |

pre-stress score가 높은 4시간 hold를 champion으로 고른 뒤 2026 stress history를 열었습니다. 결과는 **-1.21%, Sharpe -6.95, 6건**이었습니다. 2024 +8.67%, 2025 +1.92%였던 양수 구간이 2026에는 다시 음수로 바뀌었습니다.

### 비용 민감도

4시간 champion에서 fee/slippage를 0으로 두면 discovery는 +3.17%, validation은 +13.25%였습니다. discovery 25건의 평균 gross 거래 수익은 약 +0.129%로, 사전 등록한 왕복 최소 비용 약 0.14%보다 작습니다. 따라서 gross 방향성은 있었지만 현재 실행비용을 포함한 거래 가능한 Edge로는 남지 않았습니다.

### 판정

**`BTC global positioning velocity + OI 감소 shock → ETH follow` 가설은 REJECTED입니다.**

1시간 hold는 discovery와 validation 모두 수익이 없었고, 4시간 hold는 validation만 강했으며 discovery와 2026 stress에서 음수였습니다. 비용 0 진단은 underlying gross 반응을 보여주지만 사전 비용 계약을 넘지 못하므로 판정을 뒤집지 않습니다. 같은 global-ratio source에서 threshold나 holding만 조정한 재시험은 하지 않습니다.

재현 결과 파일:

- `artifacts/edge_search/cross_asset_lead_lag_pre_stress.csv`
- `artifacts/edge_search/cross_asset_lead_lag_champion_stress_2026.csv`
- `artifacts/edge_search/cross_asset_lead_lag_champion_zero_cost.csv`
- `artifacts/edge_search/cross_asset_lead_lag_champion_yearly.csv`
- 실행 모듈: `src/quant_lab/research/cross_asset_lead_lag.py`

## BTC top-trader position velocity/OI shock → ETH cross-asset lead-lag 사전 등록

global account ratio 결과를 본 뒤 threshold나 holding을 다시 조정하지 않고, Binance metrics의 별도 source인 top-trader position ratio로 같은 정보 전달 가설을 검증합니다. 결과를 열기 전에 아래 규칙을 고정합니다.

- source asset: BTCUSDT
- target asset: ETHUSDT
- source data: Binance USD-M BTCUSDT 5분 metrics의 매시간 `:55` snapshot + BTCUSDT 1시간 futures kline
- target data: Binance USD-M ETHUSDT 1시간 futures kline
- positioning source: `sum_toptrader_long_short_ratio`만 사용
- lookback: 4시간으로 고정
- velocity: `log(top_position_ratio_t) - log(top_position_ratio_{t-4h})`
- acceleration: `velocity_t - velocity_{t-4h}`
- 표준화: 현재 관측치를 제외한 직전 720개 시간의 완전한 관측치만 사용
- shock threshold: `|velocity_z| >= 2.0` 및 `|acceleration_z| >= 1.0`
- BTC state: velocity와 acceleration, BTC 4시간 가격 변화가 같은 방향이고 계약 수 OI 4시간 변화는 반대 방향인 deleveraging/cover state
- ETH 방향 가설: BTC top-trader position velocity 방향을 ETH가 뒤따른다
- holding: 1시간과 4시간의 2개 trial
- signal time: BTC의 해당 1시간 봉이 완전히 닫힌 뒤
- entry: 다음 ETH 1시간 봉 open
- exit: 진입 후 각각 1시간/4시간 뒤 ETH open
- 보유 중 겹치는 이벤트는 무시
- 결측 시계열은 forward-fill하지 않고 완전한 시간 grid에서 해당 feature를 결측 처리
- 비용: 편도 fee 5 bps + slippage 2 bps
- discovery: 2023-01-01 ~ 2023-12-31
- validation: 2024-01-01 ~ 2025-12-31
- 2026-01-01 ~ 2026-08-31은 두 trial의 pre-stress 결과로 champion을 고른 뒤에만 stress history로 확인
- pre-pass: discovery와 validation 모두 수익률 > 0, Sharpe > 0, 거래 수 >= 10
- champion: pre-pass 우선, 이후 `validation Sharpe + 0.25 * validation return`; 동률이면 1시간 hold 우선
- 비용 0 결과는 실행비용 민감도 진단으로만 사용하고 판정을 뒤집지 않음

이 source도 실패하면 같은 top-trader position series에서 threshold/lookback/holding만 바꿔 재시험하지 않습니다. 재검토는 target asset, source series, 실행 가정, 또는 독립적인 미래 데이터처럼 정보 전달 메커니즘이 바뀔 때만 엽니다.

## BTC top-trader position velocity/OI shock → ETH cross-asset lead-lag 실제 결과

사전 등록한 1시간/4시간 hold 두 trial은 모두 discovery와 validation에서 손실이 나 pre-pass에 실패했습니다.

| Hold | Discovery | Sharpe | 거래 수 | Validation | Sharpe | 거래 수 | 판정 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1h | -13.07% | -48.71 | 55 | -19.22% | -38.99 | 90 | discovery/validation 모두 실패 |
| 4h | -7.70% | -7.63 | 43 | -22.15% | -6.32 | 72 | discovery/validation 모두 실패 |

pre-stress score가 덜 나쁜 4시간 hold를 champion으로 고른 뒤 2026 stress history를 열었습니다. 결과는 **-19.66%, Sharpe -33.68, 26건**이었습니다. 연도별로도 2025년만 +4.29%였고 2023 -7.70%, 2024 -25.36%, 2026 -19.66%로 일관성이 없었습니다.

### 비용 민감도

4시간 champion에서 fee/slippage를 0으로 제거해도 discovery **-1.96%, Sharpe -1.69**, validation **-13.88%, Sharpe -3.54**였습니다. 따라서 이번 실패는 왕복 비용 때문에 양수 gross Edge가 사라진 경우가 아니라, 비용 전에도 source 방향성이 약한 경우입니다.

### 판정

**`BTC top-trader position velocity + OI 감소 shock → ETH follow` 가설은 REJECTED입니다.**

global account ratio에서 보였던 일부 validation 양수 반응도 재현되지 않았고, top-trader position source는 discovery/validation/2026 stress에서 모두 음수였습니다. 같은 series에서 threshold/lookback/holding만 조정한 재시험은 하지 않습니다.

재현 결과 파일:

- `artifacts/edge_search/top_trader_position_lead_lag_pre_stress.csv`
- `artifacts/edge_search/top_trader_position_lead_lag_champion_stress_2026.csv`
- `artifacts/edge_search/top_trader_position_lead_lag_champion_zero_cost.csv`
- `artifacts/edge_search/top_trader_position_lead_lag_champion_yearly.csv`
- 실행 모듈: `src/quant_lab/research/top_trader_position_lead_lag.py`

## BTC/ETH 상대가치 Edge wave 사전 등록

앞선 cross-asset 실험은 ETH 절대수익을 목표로 했기 때문에 BTC와 ETH가 같이 움직이는 시장 beta가 결과를 지배할 수 있었습니다. 이번 wave는 **다음 봉 open에서 ETH와 BTC를 50/50 dollar-neutral pair로 거래한 상대수익**을 목표로 바꿉니다. 결과를 보기 전에 아래 세 가족과 파라미터를 고정합니다.

공통 계약:

- 데이터: Binance USD-M BTCUSDT / ETHUSDT 1시간 futures + 같은 시점의 metrics/premium/taker 자료
- feature time: 완전히 닫힌 1시간 bar만 사용
- entry: 신호 다음 1시간 bar open에서 ETH/BTC 두 leg 동시 진입
- exit: 1시간 또는 4시간 뒤 두 leg open에서 동시 청산
- pair return: ETH leg 50% + BTC leg 50%의 dollar-neutral gross notional 기준
- 비용: 각 leg 편도 fee 5 bps + slippage 2 bps, 두 leg 모두 반영
- 겹치는 이벤트: 기존 pair 보유 중 새 이벤트 무시
- discovery: 2023-01-01 ~ 2023-12-31
- validation: 2024-01-01 ~ 2025-12-31
- 2026-01-01 ~ 2026-08-31: 가족별 pre-stress champion을 고른 뒤에만 stress history로 확인
- pre-pass: discovery와 validation 모두 수익률 > 0, Sharpe > 0, 거래 수 >= 10
- champion: pre-pass 우선, 이후 `validation Sharpe + 0.25 * validation return`; 동률이면 1시간 hold 우선
- 비용 0 결과는 진단 전용이며 판정을 뒤집지 않음

### 가족 A: BTC positioning shock → ETH/BTC catch-up

- source variant 2개: global account ratio, top-trader position ratio
- lookback: 4시간
- velocity/acceleration z-score window: 현재 관측치를 제외한 직전 720시간
- threshold: `|velocity_z| >= 2.0`, `|acceleration_z| >= 1.0`
- state: velocity, acceleration, BTC 4시간 가격 변화가 같은 방향이고 BTC 계약 수 OI 4시간 변화는 반대 방향
- pair 방향: BTC shock 방향으로 ETH가 뒤늦게 따라온다는 가설. bullish shock면 long ETH / short BTC, bearish shock면 short ETH / long BTC
- hold: 1시간, 4시간
- trial 수: 4

### 가족 B: premium + OI 상대 혼잡도 fade

- premium spread: `ETH premium_close - BTC premium_close`
- premium z-score: 현재 관측치를 제외한 직전 720시간
- threshold: `|premium_spread_z| >= 2.0`
- OI confirmation: `log(ETH OI value_t / ETH OI value_{t-4h}) - log(BTC OI value_t / BTC OI value_{t-4h})`가 premium spread와 같은 방향
- price confirmation: ETH/BTC 4시간 상대수익이 premium spread와 같은 방향
- pair 방향: 더 비싸고 OI가 더 빠르게 쌓이며 상대가격도 같은 방향으로 간 leg를 fade
- hold: 1시간, 4시간
- trial 수: 2

### 가족 C: taker 상대 chase fade

- taker spread: `log(ETH taker_ratio) - log(BTC taker_ratio)`
- taker spread z-score: 현재 관측치를 제외한 직전 720시간
- threshold: `|taker_spread_z| >= 2.0`
- confirmation: ETH/BTC 4시간 상대수익이 taker spread와 같은 방향
- pair 방향: 공격적 taker flow와 상대가격이 동시에 한쪽으로 쏠린 leg를 fade
- hold: 1시간, 4시간
- trial 수: 2

총 8개 trial만 실행합니다. 결과를 본 뒤 threshold/lookback/holding 또는 방향을 바꿔 같은 wave 안에서 재탐색하지 않습니다. 모두 실패하면 다음 wave는 source/target 또는 실행 메커니즘이 다른 가족으로 넘어갑니다.

## BTC/ETH 상대가치 Edge wave 실제 결과

사전 등록한 8개 trial은 모두 pre-pass에 실패했습니다.

| 가족 | Variant | Hold | Discovery | Validation | Validation Sharpe | Validation 거래 수 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| positioning catch-up | global | 1h | -6.57% | -2.15% | -59.98 | 17 |
| positioning catch-up | global | 4h | -4.72% | -3.71% | -31.75 | 16 |
| positioning catch-up | top-position | 1h | -9.49% | -15.73% | -67.07 | 109 |
| positioning catch-up | top-position | 4h | -7.46% | -11.72% | -9.70 | 90 |
| premium + OI crowding fade | premium/OI | 1h | -13.52% | -43.32% | -37.70 | 352 |
| premium + OI crowding fade | premium/OI | 4h | -10.61% | -45.33% | -16.01 | 308 |
| taker chase fade | taker | 1h | -21.37% | -45.79% | -72.02 | 423 |
| taker chase fade | taker | 4h | -17.41% | -45.34% | -19.94 | 387 |

가족별로 pre-stress score가 덜 나쁜 4시간 후보만 2026 stress history에 열었습니다. positioning catch-up은 -2.65%, premium/OI crowding fade는 -11.40%, taker chase fade는 -18.48%였습니다.

비용 0 진단에서도 구조적 안정성은 없었습니다. positioning top-position 4h는 discovery -0.61%, validation +0.15%였고, premium/OI 4h는 discovery +3.26%에서 validation -15.82%로 반전했습니다. taker 4h도 discovery +2.61%에서 validation -5.99%로 반전했습니다. 따라서 세 가족 모두 거래비용만 낮추면 살아나는 형태가 아닙니다.

**`BTC/ETH relative-value wave`는 REJECTED입니다.** 같은 세 가족에서 threshold/lookback/holding 또는 방향만 바꾼 재시험은 하지 않습니다.

재현 결과 파일:

- `artifacts/edge_search/relative_value_wave_pre_stress.csv`
- `artifacts/edge_search/relative_value_wave_champions_stress_2026.csv`
- `artifacts/edge_search/relative_value_wave_champions_zero_cost.csv`
- `artifacts/edge_search/relative_value_wave_champions_yearly.csv`
- 실행 모듈: `src/quant_lab/research/relative_value_wave.py`

## Funding settlement 상대가치 wave 사전 등록

hourly microstructure 신호와 다른 구조적 이벤트를 보기 위해 Binance perpetual funding settlement 직후의 BTC/ETH 상대가치 unwind를 검증합니다. BTC/ETH funding event는 2020-01부터 같은 timestamp에 7,333건 존재하며, 0/8/16 UTC에 정산됩니다. timestamp가 정각보다 수십 ms 늦는 이벤트가 있으므로 해당 시간을 신호 시각으로만 사용하고 **다음 1시간 bar open**에서 진입합니다.

공통 계약:

- source: BTCUSDT / ETHUSDT 실제 funding settlement rate
- funding spread: `ETH funding_rate - BTC funding_rate`
- 표준화: 현재 settlement를 제외한 직전 90개 공통 funding event의 mean/std
- event threshold: `|funding_spread_z| >= 2.0`
- pair 방향: raw funding spread가 양수면 ETH가 상대적으로 더 crowded long이라고 보고 short ETH / long BTC, 음수면 반대
- entry: funding settlement가 관측된 시간의 다음 1시간 bar open
- hold: 1시간, 4시간
- exit: hold 종료 시 두 leg open에서 동시 청산
- pair return: ETH/BTC 각 50% dollar-neutral gross notional
- 비용: 각 leg 편도 fee 5 bps + slippage 2 bps
- 4시간 hold까지만 사용해 다음 8시간 funding settlement를 포지션 보유 중 통과하지 않음
- discovery: 2022-01-01 ~ 2023-12-31
- validation: 2024-01-01 ~ 2025-12-31
- 2026-01-01 ~ 2026-08-31: pre-stress champion을 고른 뒤에만 stress history로 확인
- pre-pass: discovery와 validation 모두 수익률 > 0, Sharpe > 0, 거래 수 >= 10
- champion: pre-pass 우선, 이후 `validation Sharpe + 0.25 * validation return`; 동률이면 1시간 hold 우선
- 비용 0 결과는 진단 전용

두 variant를 사전 등록합니다.

1. `funding_diff_fade`: funding spread extreme만 사용합니다.
2. `funding_premium_confirmed_fade`: funding spread 방향과 같은 시점의 `ETH premium_close - BTC premium_close` 방향이 같을 때만 거래합니다.

각 variant에 1h/4h hold를 적용해 총 4개 trial만 실행합니다. 결과를 본 뒤 z-threshold, rolling window, hold, 방향을 바꿔 같은 funding wave를 반복하지 않습니다.

## Funding settlement 상대가치 wave 실제 결과

사전 등록한 4개 trial은 모두 pre-pass에 실패했습니다.

| Variant | Hold | Discovery | Validation | Validation Sharpe | Validation 거래 수 |
| --- | ---: | ---: | ---: | ---: | ---: |
| funding diff fade | 1h | -20.10% | -29.21% | -47.97 | 149 |
| funding diff fade | 4h | -16.19% | -27.51% | -17.43 | 149 |
| funding + premium confirm | 1h | -15.79% | -25.58% | -46.82 | 119 |
| funding + premium confirm | 4h | -9.51% | -25.22% | -18.62 | 119 |

pre-stress score가 가장 높은 pure funding 4시간 후보를 2026 stress에 열었고 결과는 **-7.86%, Sharpe -26.48, 48건**이었습니다. 비용 0에서는 discovery +3.11%였지만 validation -10.66%로 반전해, execution cost만 낮추면 살아나는 형태도 아니었습니다.

연도별 champion 결과도 2022 -9.69%, 2023 -7.21%, 2024 -8.65%, 2025 -20.64%, 2026 -7.86%로 전 구간 음수였습니다.

**`BTC/ETH funding settlement differential fade`는 REJECTED입니다.** 같은 funding spread에서 threshold/window/hold/방향만 바꾼 재시험은 하지 않습니다.

재현 결과 파일:

- `artifacts/edge_search/funding_relative_value_pre_stress.csv`
- `artifacts/edge_search/funding_relative_value_champion_stress_2026.csv`
- `artifacts/edge_search/funding_relative_value_champion_zero_cost.csv`
- `artifacts/edge_search/funding_relative_value_champion_yearly.csv`
- 실행 모듈: `src/quant_lab/research/funding_relative_value.py`

## Global-position cap momentum 정식화

초기 pre-screen artifact를 만든 당시 실행 세션을 복원해 정확한 규칙을 확인했습니다. 이 가족은 새로 threshold를 고르는 탐색이 아니라, 이미 관찰된 parameter plateau를 하나의 고정 규칙으로 정식화하는 단계입니다.

- base momentum: `close_t > close_{t-336h}` 이고 `close_t > EMA_400h`
- crowding source: Binance `count_long_short_ratio` (global account long/short ratio)
- crowding history: 직전 2160시간
- cap: 현재 값을 제외한 직전 2160시간의 90% quantile
- filter: 현재 global ratio가 cap 이하일 때만 base momentum long 허용
- timeframe: BTC/ETH × 1h/4h 모두 같은 시간 단위 규칙으로 환산
- execution: 닫힌 bar에서 signal 계산, 기존 backtester가 다음 bar open에서 target 실행
- 비용/리스크: fee 5 bps, slippage 2 bps, 거래당 risk 1%, stop 5%, volatility slippage multiplier 0.02

q90은 사후 최고점 선택이 아니라 기존에 q75/q90/q95 세 값이 모두 2022~2025 pre-screen과 2026 stress를 통과한 plateau의 중앙값으로 고정합니다. 당시 이미 2026 결과를 확인했으므로 2026은 독립 holdout으로 재사용하지 않습니다. 정식 모듈은 과거 artifact를 **재현성 검증**하고, 최종 판정은 2026-09-11 이후 새 데이터만 사용하는 future shadow로 넘깁니다.

future shadow 규칙:

- shadow start: 2026-09-11 00:00 UTC 이후 새로 생기는 완전한 bar
- q90 / 2160h / 336h / EMA 400h를 shadow 동안 변경하지 않음
- BTC/ETH × 1h/4h 네 데이터셋 모두 누적 수익률 > 0, Sharpe > 0, 거래 수 >= 10이 될 때까지 `PROMOTED` 판정을 금지
- 하나라도 누적 수익률 또는 Sharpe가 음수인 상태에서 충분한 표본이 쌓이면 `REJECTED`로 닫음
- shadow 전에는 paper/live trading에 연결하지 않음

### 재현 결과와 SHADOW 판정

정식 모듈로 과거 일회성 스크립트를 재현했습니다. q90 / 2160h 규칙은 discovery, validation, 2026 stress에서 BTC/ETH × 1h/4h 네 데이터셋 모두 양수였습니다.

| 데이터셋 | 2022~2023 Discovery | 2024~2025 Validation | Validation Sharpe | 2026 Stress | 2026 Sharpe | 2026 거래 수 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BTC 1h | +8.20% | +4.22% | +0.40 | +2.04% | +0.68 | 47 |
| ETH 1h | +5.41% | +14.79% | +0.91 | +4.11% | +1.03 | 45 |
| BTC 4h | +9.39% | +5.87% | +0.54 | +2.22% | +0.74 | 26 |
| ETH 4h | +5.26% | +11.54% | +0.74 | +2.57% | +0.65 | 28 |

이 수치는 과거 pre-screen artifact와 동일한 규칙을 재현하며, 2026 q90 stress도 당시 기록한 값과 일치합니다. 그러나 q75/q90/q95와 2026 결과를 과거 탐색 과정에서 이미 확인했으므로 독립적인 holdout 증거는 아닙니다.

따라서 **`global-position cap momentum q90 / 2160h`를 `SHADOW`로 이동합니다.** 현재 로컬 artifact에는 shadow 시작인 2026-09-11 이후 완성된 데이터가 없어 shadow 결과는 아직 0건입니다. 다음 새 데이터에서 파라미터를 동결한 채 누적 관찰합니다.

재현 결과 파일:

- `artifacts/edge_search/position_cap_momentum_historical.csv`
- `artifacts/edge_search/position_cap_momentum_shadow.csv`
- 실행 모듈: `src/quant_lab/research/position_cap_momentum.py`

## BTC/ETH relative-strength rotation 사전 등록

crowding/flow/funding 계열과 다른 cross-sectional momentum 메커니즘을 한 번만 검증합니다. 두 자산을 동시에 long/short하지 않고, 장기 상승 추세에 있는 자산 중 최근 7일 상대강도가 더 높은 하나로 자본을 이동합니다.

- universe: BTCUSDT, ETHUSDT perpetual futures
- 데이터: 1h와 4h 공식 futures/microstructure OHLCV
- relative momentum: 현재 close / 168시간 전 close - 1
- absolute trend gate: 현재 close > EMA 400시간
- 선택: trend gate를 통과한 자산 중 168h return이 더 높은 하나; 둘 다 gate 실패면 cash
- rebalance: 하루 한 번 00:00 UTC open
- signal time: 1h는 직전 23:00 bar가 완전히 닫힌 뒤, 4h는 직전 20:00 bar가 완전히 닫힌 뒤
- execution: 다음 00:00 UTC open부터 새 target 적용
- 비용: target 변경 때마다 각 매수/매도 leg에 fee 5 bps + slippage 2 bps
- 같은 자산 유지 중에는 재진입 비용을 부과하지 않음
- discovery: 2022-01-01 ~ 2023-12-31
- validation: 2024-01-01 ~ 2025-12-31
- stress: 2026-01-01 ~ 2026-09-10, validation 결과 확인 후에만 열기
- pre-pass: 1h와 4h 모두 discovery return > 0, validation return > 0, validation Sharpe > 0, target 변경 횟수 >= 10
- trial 수: 고정 규칙 1개. 결과를 보고 lookback/EMA/rebalance 주기를 바꾸지 않음

이 규칙이 역사 stress까지 살아도 2026은 pristine holdout이 아니므로 바로 paper 후보로 승격하지 않고, 2026-09-11 이후 future shadow가 필요합니다.

### 실제 결과

고정 규칙 1개를 1h/4h 양쪽에서 실행했습니다. 두 timeframe은 거의 같은 결과를 냈지만 discovery에서 손실이 나 사전 기준을 통과하지 못했습니다.

| Timeframe | Discovery 2022~2023 | Validation 2024~2025 | Validation Sharpe | 2026 Stress | 2026 Sharpe | Validation target 변경 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1h | -4.46% | +14.55% | +0.37 | +34.74% | +1.40 | 156 |
| 4h | -4.89% | +14.54% | +0.37 | +34.73% | +1.41 | 156 |

2024년 이후에는 매우 강했지만 2022~2023 discovery의 최대 drawdown이 약 -40%이고 누적 수익도 음수였습니다. 최근 regime에 특화된 전략 가능성은 있으나 사전 등록한 multi-regime 기준에서는 탈락입니다.

**`BTC/ETH relative-strength rotation`은 REJECTED입니다.** 이번 결과를 보고 lookback, EMA, rebalance 시간 또는 cash gate를 재조정하지 않습니다. 다시 열려면 독립적인 regime-switching 가설처럼 메커니즘을 명시적으로 바꿔 별도 연구로 등록해야 합니다.

재현 결과 파일:

- `artifacts/edge_search/relative_strength_rotation_pre_stress.csv`
- `artifacts/edge_search/relative_strength_rotation_stress_2026.csv`
- `artifacts/edge_search/relative_strength_rotation_shadow.csv`
- 실행 모듈: `src/quant_lab/research/relative_strength_rotation.py`

## BTC/ETH breadth-confirmed momentum 사전 등록

기존 momentum의 parameter를 다시 탐색하지 않고, 시장 전체가 같은 상승 regime인지 확인하는 cross-asset breadth gate만 추가합니다. 한 자산만 강한 국면보다 BTC와 ETH가 동시에 장기 추세 위에 있을 때 추세 지속성이 높다는 가설입니다.

- universe: BTCUSDT, ETHUSDT
- timeframe: 1h, 4h
- own momentum: `close_t > close_{t-336h}`
- own trend: `close_t > EMA_400h`
- breadth gate: 같은 timeframe에서 **BTC와 ETH 둘 다** 각자의 EMA 400h 위
- target: 각 자산은 own momentum + own trend + breadth gate가 모두 참일 때만 long, 아니면 cash
- execution: 닫힌 signal bar 다음 bar open
- 비용/리스크: fee 5 bps, slippage 2 bps, risk 1%, stop 5%, volatility slippage multiplier 0.02
- discovery: 2022-01-01 ~ 2023-12-31
- validation: 2024-01-01 ~ 2025-12-31
- stress: 2026-01-01 ~ 2026-09-10, pre-stress 판정 뒤에만 확인
- pre-pass: BTC/ETH × 1h/4h 네 데이터셋 모두 discovery return > 0, validation return > 0, validation Sharpe > 0, validation trades >= 10
- trial 수: 고정 규칙 1개. 결과를 보고 lookback/EMA/breadth 정의를 바꾸지 않음

역사 stress까지 살아도 2026은 이미 stress history이므로 최종 승격은 2026-09-11 이후 future shadow에서만 가능합니다.

### 실제 결과와 SHADOW 판정

고정 규칙 1개가 discovery와 validation에서 BTC/ETH × 1h/4h 네 데이터셋을 모두 통과했습니다.

| 데이터셋 | Discovery | Validation | Validation Sharpe | 2026 Stress | 2026 Sharpe | 2026 거래 수 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BTC 1h | +4.44% | +7.28% | +0.63 | +0.09% | +0.05 | 74 |
| ETH 1h | +6.21% | +34.64% | +1.78 | +1.69% | +0.39 | 72 |
| BTC 4h | +5.27% | +9.25% | +0.78 | +0.89% | +0.29 | 38 |
| ETH 4h | +6.78% | +31.54% | +1.62 | +1.22% | +0.30 | 40 |

2026 stress도 모두 양수지만 BTC 1h의 +0.09%, Sharpe +0.05는 여유가 매우 작습니다. 따라서 역사 생존은 확인했지만 실거래 후보로 부르기에는 아직 증거가 약합니다.

**`BTC/ETH breadth-confirmed momentum`을 `SHADOW`로 이동합니다.** 파라미터를 그대로 동결하고 2026-09-11 이후 새 데이터에서 네 데이터셋 모두 누적 return > 0, Sharpe > 0, 거래 수 >= 10을 확인해야만 다음 단계로 갈 수 있습니다.

재현 결과 파일:

- `artifacts/edge_search/breadth_momentum_pre_stress.csv`
- `artifacts/edge_search/breadth_momentum_stress_2026.csv`
- `artifacts/edge_search/breadth_momentum_shadow.csv`
- 실행 모듈: `src/quant_lab/research/breadth_momentum.py`

## BTC/ETH high-correlation relative-shock fade 사전 등록

premium, taker, funding 같은 파생 지표가 아니라 **가격 관계 자체의 일시적 이탈**을 검증합니다. BTC와 ETH가 최근 일주일 동안 높은 상관을 유지했는데 24시간 상대수익만 역사적으로 극단까지 벌어지면, 일시적 dislocation이 평균회귀한다는 가설입니다.

- 데이터: BTCUSDT / ETHUSDT 1h perpetual futures
- BTC/ETH hourly return correlation: 현재 bar를 제외한 직전 168시간
- correlation gate: `corr >= 0.70`
- relative shock: `log(ETH_close_t / ETH_close_{t-24h}) - log(BTC_close_t / BTC_close_{t-24h})`
- shock z-score: 현재 관측치를 제외한 직전 720시간의 relative-shock mean/std
- threshold: `|relative_shock_z| >= 2.0`
- direction: ETH 상대수익이 양의 극단이면 short ETH / long BTC, 음의 극단이면 long ETH / short BTC
- entry: signal 다음 1시간 bar open
- hold: 24시간 고정
- 겹치는 이벤트: 포지션 보유 중 새 이벤트 무시
- 비용: 두 leg 모두 편도 fee 5 bps + slippage 2 bps
- discovery: 2022-01-01 ~ 2023-12-31
- validation: 2024-01-01 ~ 2025-12-31
- stress: 2026-01-01 ~ 2026-09-10, pre-stress 판정 후에만 확인
- pre-pass: discovery와 validation 모두 return > 0, Sharpe > 0, trades >= 10
- trial 수: 고정 규칙 1개. 결과를 보고 correlation/z/hold를 재조정하지 않음

통과하더라도 2026은 stress history이므로 future shadow 전에는 paper 후보로 승격하지 않습니다.

### 실제 결과

사전 등록한 고정 규칙 1개는 pre-pass에 실패했습니다.

- discovery 2022~2023: **-14.89%, Sharpe -2.60, 101건**
- validation 2024~2025: **-21.72%, Sharpe -2.61, 104건**
- 2026 stress: **-11.73%, Sharpe -6.02, 35건**
- 비용 0 진단: discovery **-1.95%**, validation **-9.43%**

비용을 제거해도 validation이 명확히 음수라 실행비용 문제가 아니라 상대가격 shock를 fade하는 방향 자체가 안정적이지 않았습니다.

**`BTC/ETH high-correlation relative-shock fade`는 REJECTED입니다.** correlation threshold, z-score threshold, lookback, hold 또는 방향만 바꿔 같은 가족을 다시 탐색하지 않습니다.

재현 결과 파일:

- `artifacts/edge_search/relative_shock_fade_pre_stress.csv`
- `artifacts/edge_search/relative_shock_fade_stress_2026.csv`
- `artifacts/edge_search/relative_shock_fade_zero_cost.csv`
- `artifacts/edge_search/relative_shock_fade_shadow.csv`
- 실행 모듈: `src/quant_lab/research/relative_shock_fade.py`

## BTC price shock → lagging ETH continuation 사전 등록

앞선 cross-asset 연구는 BTC positioning/OI 변화가 ETH에 전달되는지를 보거나, BTC/ETH 상대가격 이탈을 pair mean-reversion으로 거래했습니다. 이번 가설은 데이터 계약과 경제 메커니즘을 바꿔 **BTC 자체의 급격한 가격 정보충격이 같은 시간에 덜 반영된 ETH로 뒤늦게 전달되는지**만 검증합니다. relative-shock fade의 방향만 뒤집는 재시험이 되지 않도록 relative 24h z-score, correlation gate, pair 포지션은 사용하지 않습니다.

- 데이터: Binance USD-M BTCUSDT / ETHUSDT 1시간 futures kline
- BTC shock: 현재 1시간 log return의 z-score를 현재 관측치를 제외한 직전 720시간으로 계산
- shock threshold: `|BTC return z| >= 2.0`
- ETH underreaction: 같은 1시간 ETH return이 BTC와 같은 방향이고, 절대 크기가 BTC 절대 return의 `50% 이하`
- 방향: BTC shock 방향으로 ETH 단일 leg 추종
- signal time: BTC/ETH 해당 1시간 봉이 완전히 닫힌 뒤
- entry: signal 다음 1시간 bar open
- hold: 4시간 고정
- 겹치는 이벤트: 포지션 보유 중 새 이벤트 무시
- 비용: 편도 fee 5 bps + slippage 2 bps
- discovery: 2022-01-01 ~ 2023-12-31
- validation: 2024-01-01 ~ 2025-12-31
- stress: 2026-01-01 ~ 2026-09-10, pre-stress 판정 뒤 진단
- pre-pass: discovery와 validation 모두 return > 0, Sharpe > 0, 거래 수 >= 10
- trial 수: 고정 규칙 1개. 결과를 보고 z threshold, underreaction 비율, hold 또는 방향을 재조정하지 않음

이 가설이 실패하면 같은 BTC 1h shock에 threshold/ratio/hold만 바꿔 반복하지 않습니다. 재검토는 더 짧은 실제 체결/호가 데이터처럼 정보전달 시점 계약 자체가 달라지거나 target universe가 달라질 때만 엽니다.

### 실제 결과

사전 등록한 고정 규칙 1개는 discovery에서는 양수였지만 validation에서 실패했습니다.

- discovery 2022~2023: **+9.73%, Sharpe +3.96, 57건**
- validation 2024~2025: **-4.96%, Sharpe -1.48, 55건**
- 2026 stress: **-4.33%, Sharpe -17.55, 11건**
- 비용 0 discovery: **+18.84%, Sharpe +6.92**
- 비용 0 validation: **+2.66%, Sharpe +1.52**
- 비용 0 2026 stress: **-2.84%, Sharpe -11.33**

비용을 제거하면 2024~2025까지 gross lead-lag 방향은 약하게 남지만 validation의 평균 gross 거래 수익은 약 **+0.071% = +7.1bp/trade**입니다. 사전 등록한 fee 5bp + slippage 2bp를 양방향에 적용한 왕복 비용 약 14bp보다 작아서 거래 가능한 여유가 없습니다. 2026은 비용을 완전히 제거해도 음수여서 최근 구간에서는 가격발견 방향성 자체도 유지되지 않았습니다.

**`BTC price shock → lagging ETH continuation`은 REJECTED입니다.** z threshold, ETH underreaction 비율, hold 또는 방향만 바꿔 같은 가족을 다시 탐색하지 않습니다.

재현 결과 파일:

- `artifacts/edge_search/price_lead_lag_pre_stress.csv`
- `artifacts/edge_search/price_lead_lag_stress_2026.csv`
- `artifacts/edge_search/price_lead_lag_zero_cost.csv`
- `artifacts/edge_search/price_lead_lag_shadow.csv`
- 실행 모듈: `src/quant_lab/research/price_lead_lag.py`

## 참고 자료

- Binance public data: <https://github.com/binance/binance-public-data>
- Binance USD-M long/short ratio: <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio>
- Binance top trader account ratio: <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Long-Short-Account-Ratio>
- Binance top trader position ratio: <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Long-Short-Position-Ratio>
- Binance open-interest statistics: <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics>
- USD-M liquidationSnapshot stop report: <https://github.com/binance/binance-public-data/issues/337>
- USD-M historical liquidation availability follow-up: <https://github.com/binance/binance-public-data/issues/420>
- Bitcoin market fragmentation and order flow: <https://www.tandfonline.com/doi/full/10.1080/1350486X.2022.2080083>
- 2026 BTC/ETH futures liquidity-state/order-flow study: <https://arxiv.org/pdf/2607.09230>
- 2026 liquidation-cascade study: <https://arxiv.org/html/2608.03616>

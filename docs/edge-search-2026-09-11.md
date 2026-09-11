# Derivatives microstructure Edge research — 2026-09-11

Funding/OI의 단순 방향성 가설 다음에 무엇을 연구할지 조사하고, 현재 로컬 artifact에 남아 있는 미시구조 실험도 함께 복구해 정리했습니다.

## 결론

다음 정식 연구 우선순위는 아래와 같습니다.

1. **Taker-flow shock × price divergence / absorption**
2. **Long/Short positioning의 절대값이 아닌 변화속도·가속도·series 간 불일치**
3. **Liquidation burst는 신뢰할 수 있는 역사 데이터 확보 전까지 보류**

단순 taker continuation/rebound, 절대적인 positioning crowd fade, premium fade/continuation은 이미 로컬 실험에서 엄격한 사전 기준을 통과하지 못했습니다. 같은 아이디어를 임계값만 바꿔 다시 돌리지 않습니다.

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

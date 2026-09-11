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

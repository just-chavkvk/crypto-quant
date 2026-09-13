# Edge family search — 2026-09-10

BTC/ETH에서 서로 다른 원리의 Edge 후보를 같은 기준으로 비교한 첫 가족 단위 검증 기록입니다.

## 검증 방식

- 데이터: Binance spot BTC/USDT, ETH/USDT의 1h/4h OHLCV
- 후보 탐색: 2020-01-01 ~ 2023-12-31
- 별도 검증: 2024-01-01 ~ 2025-12-31
- 최종 holdout: 2026-01-01 이후
- 거래 비용: fee 5 bps, base slippage 2 bps
- 리스크: 거래당 1%, stop loss 5%
- 변동성 slippage multiplier: 0.02
- 각 가족의 대표 설정은 holdout을 보기 전에 discovery/validation 성적으로만 선택
- 대표 설정만 2026 holdout을 열어보고 최종 판정

1h 원시 데이터에는 BTC/ETH 각각 32개의 누락 candle이 있고 마지막 누락은 2023-03-24입니다. 4h 원시 데이터에는 각각 1개의 누락 candle이 있습니다. 2024~2026 검증 구간에는 해당 1h 누락이 없습니다.

## 결과

| Edge 가족 | holdout 전에 고른 대표 설정 | 2024~2025 네 시장 중 최저 수익 | 2026 네 시장 중 최저 수익 | 판정 |
| --- | --- | ---: | ---: | --- |
| Momentum | lookback 336h + trend 400h | +12.07% | -0.20% | REJECTED |
| Donchian breakout | breakout 336h + exit 72h | +7.69% | -2.38% | REJECTED |
| Volume breakout | breakout 168h + volume 336h × 1.5 | +7.82% | -0.97% | REJECTED |
| Volatility breakout | breakout 72h + range 72h × 2.0 | +7.67% | -3.20% | REJECTED |

Momentum은 2026 holdout에서 ETH 1h, BTC 4h, ETH 4h는 플러스였지만 BTC 1h가 약 -0.20%라 현재의 엄격한 전 시장 통과 기준을 넘지 못했습니다.

2026 결과를 본 뒤 같은 가족의 다른 설정으로 다시 고르는 방식은 사용하지 않습니다. 그렇게 하면 holdout이 새로운 학습 데이터가 되어 검증 의미가 사라집니다.

## 다음 연구 방향

현재 가격/거래량 OHLCV만 사용하는 네 가족 중 완전 통과한 Edge는 없습니다. Momentum은 가장 가까운 관찰 후보로 유지하고, 다음 탐색은 가격과 다른 정보원을 쓰는 funding/OI/liquidation 계열로 확장합니다. Paper trading에는 최종 기준을 통과한 Edge가 생길 때 정식 참가시키고, 기준 미달 후보는 별도 shadow 관찰 대상으로만 다룹니다.

## Funding / OI 확장 검증

Binance USD-M futures 공개 데이터를 추가로 수집해 선물시장 정보 기반 후보를 검사했습니다.

- Funding rate: BTC/ETH 모두 2020-01-01 이후 사용 가능
- Open interest: BTC는 2020-09-01 이후, ETH는 2021-12-01 이후 사용 가능
- OI 공통 비교 구간: 2022-01-01 ~ 2023-12-31 탐색, 2024-01-01 ~ 2025-12-31 검증
- 2026 구간은 첫 가족 검색 이후 이미 결과를 확인했으므로 이후 실험에서는 pristine holdout이 아니라 stress check로만 취급

### 단독 선물시장 가설

| Edge 가족 | 후보 수 | 2022~2025 사전 통과 | 결과 |
| --- | ---: | ---: | --- |
| Negative funding rebound | 12 | 0 | 2024~2025는 일부 강했지만 ETH 2022~2023에서 약 -9%로 붕괴 |
| OI expansion momentum | 18 | 0 | 2024~2025부터 최소 수익/Sharpe가 음수 |
| OI flush rebound | 36 | 0 | 일부 2024~2025 성과는 양수였지만 2022~2023과 2026 stress에서 불안정 |

가장 강했던 negative funding rebound는 `funding <= -0.00005`, 72시간 보유였습니다. 2024~2025 네 데이터셋의 최저 수익은 +3.92%, 최저 Sharpe는 0.61이었지만, 2022~2023 ETH에서는 1h -9.56%, 4h -9.22%였습니다. 실제 funding 지급/수취를 거래 구간에 대입한 근사 계산에서도 ETH 개선 폭은 초기자금 기준 약 +0.18~0.23%뿐이어서 결론을 뒤집지 못했습니다.

### 기존 Momentum에 Funding / OI 필터 추가

| Edge 가족 | 후보 수 | 2022~2025 사전 통과 | 결과 |
| --- | ---: | ---: | --- |
| Funding-filtered momentum | 36 | 13 | 기존 336h/400h momentum보다 2026 약점을 해소하지 못함 |
| OI-filtered momentum | 72 | 0 | OI 필터가 오히려 성과를 악화 |
| Funding + OI crowd-filtered momentum | 12 | 0 | 네 시장 동시 안정성 부족 |

Funding-filtered momentum의 사전 1위는 `lookback=336h, trend=400h, funding cap=0.00020`이었고 2026 stress에서 BTC 1h가 다시 약 -0.20%였습니다. 높은 funding cap이 실제 진입을 거의 제한하지 않아 기존 momentum과 사실상 같은 결과였습니다.

### 과열을 반대로 숏하는 가설

| Edge 가족 | 후보 수 | 2022~2025 사전 통과 | 결과 |
| --- | ---: | ---: | --- |
| Positive funding fade short | 12 | 0 | 검증 구간부터 손실 |
| OI expansion fade short | 48 | 0 | 일부 2026 구간은 좋았지만 사전 검증 실패 |
| Funding + OI crowd fade short | 16 | 0 | 사전 검증 실패 |

현재까지 Funding/OI 기반 신규 Edge 중 정식 승격 가능한 후보는 없습니다. 단순 OI 증가를 추세 확인 신호로 쓰는 방식과 극단 funding을 바로 역추세 매매하는 방식은 현재 데이터에서 제외하는 편이 낫습니다. Momentum은 계속 관찰하되 다음 신규 가설은 taker buy/sell flow, long/short positioning, basis/premium처럼 다른 선물시장 정보를 우선 검사합니다.

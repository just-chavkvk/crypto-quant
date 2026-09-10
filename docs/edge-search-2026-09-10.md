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

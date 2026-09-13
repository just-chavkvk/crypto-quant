# Edge research — 2026-09-12

이번 회차는 새 가설 3개를 사전등록했습니다. 현물/선물 헤지 가설 2개는
**REJECTED (BLOCKED-DATA)**, 펀딩 정산 직전 매도 가설은 실제 백테스트 후
**REJECTED**입니다. 신규 PASS/SHADOW는 없고, 기존 3개 SHADOW는 모두 TRACKING입니다.

## 사전등록과 기존 연구와의 구분

- `f0e4b9c`: `hedged-edges-prereg-2026-09-12.md`, 같은 자산의 현물 매수/동일 수량
  선물 매도로 월간 펀딩 수입을 얻는 가설, 거래가격 basis 50bp 이상에서 24h 정상화를
  노리는 가설을 각각 고정. 실제 현물을 보유하는 두 시장 헤지는 기존 BTC/ETH 상대가치
  fade 및 펀딩으로 가격 방향을 예측한 연구와 데이터·실행 계약이 다릅니다.
- `7d92afa`: 어떤 수익률도 계산하기 전에 시장 거래 가능성, 현금 wallet/미실현손익,
  슬리피지 단일 차감, primary equity에 기반한 연도별 평가 계약을 명확히 기록.
- `6749d69`: `presettlement-prereg-2026-09-12.md`, 펀딩 정산 직전 1h의 매도 압력.
  펀딩값/모멘텀/가격반전 조건 없이 고정된 시간만 사용하며, 기존 정산 후 BTC/ETH
  funding-difference fade와 다른 메커니즘을 검증합니다.

총 파라미터 trial **3개 사전등록, 실제 금융 백테스트 1개 실행**입니다.
헤지 계산기의 synthetic QA는 전략 trial이나 수익성 증거에 포함하지 않습니다.
2026년은 재사용한 stress history이며 pristine holdout이 아닙니다.

## 두 현물/선물 후보: 데이터 게이트에서 중단

공식 spot 월별 1h 파일 114개를 새로 다운로드하고 SHA256을 확인했습니다.
기존 USD-M klines/fundingRate/markPriceKlines 349개 원본도 manifest로 재검증했습니다.
Spot의 2025년 이후 microsecond 전환을 명시적으로 처리하고 첫 데이터 행을 보존했습니다.

초기 exact-close-time 검사에서 각 자산의 두 행이 걸렸습니다:

- 2021-12-24 04:00 UTC: 거래가 있었지만 종료 시각이 짧은 봉. 평가 구간 밖의 사용하지
  않는 context이므로 해당 가격이 전략 진입/비용/보유기간에 영향을 줄 수 없습니다.
- 2023-03-24 12:00 UTC: 거래 수·거래량 0, OHLC 동일인 짧은 봉. 월별·일별·REST
  시각/거래 가능성 교차검증을 기록하고, 원본을 수정하지 않은 채 매매 불가로 표시하는
  데이터 계약 v2를 **첫 백테스트 전에** 고정했습니다.

그 뒤 완전한 시간 격자를 검사하자 **BTC/ETH 모두 2023-03-24 13:00 UTC 행이
완전히 없었습니다.** 각각 41,639행 / 기대 41,640행입니다. 중복이나 시각 단위 오류가
아니며, BTC 해당 시간의 공식 REST 요청도 `[]`였습니다. 보간, 누락 시간 압축,
다른 시장 가격을 현물 체결가로 대입하는 방법은 사용하지 않았습니다.

따라서 월간 펀딩 carry와 spot/perpetual dislocation의 역사 금융 백테스트는 **0회**입니다.
등록한 연속 가격/평가 계약을 충족하지 못한 결과이지, 두 경제 가설의 수익성이
음수라는 증거가 아닙니다. 완전한 공통 데이터 또는 거래 중단 시간의 평가·매매 불가를
공정하게 처리하는 별도 계약을 사전등록하기 전에는 동일 가설의 수익률 검색을 재개하지 않습니다.

헤지 실행기는 향후 적합한 데이터 검증에 사용할 수 있도록 독립 모듈로 남겼습니다.
현물 대금, 선물 현금 담보, 미실현손익, 펀딩, 두 leg 비용, 담보 위반을 분리합니다.
실제 시세가 아닌 고정가격 synthetic driver에서 q=40, funding=36.8,
execution cost=15.2, net=21.6, final equity=10,021.6을 독립 계산과 대조했습니다.
이 수치는 **QA fixture일 뿐 투자 성과가 아닙니다.**

## 펀딩 정산 직전 1h 매도: 실제 검증

고정 가설: 펀딩 지급을 피하려는 일부 long의 청산이 정산 직전에 매도 압력을 만들 수
있다는 가설입니다. 실제 투자자 동기를 관측했다는 주장이 아닙니다.

- 완성된 06/14/22 UTC 봉 이후 다음 07/15/23 UTC 시가에 short.
- 08/16/00 UTC 시가에 청산. 정산 이전 청산이라는 고정 가정에서 보유 중 펀딩 0.
- 원본 funding_interval=8 및 00/08/16 clock을 검사. 보유 시간의 예상 밖 펀딩은 오류.
- 진입 equity 20% 고정 수량, 5% stop, 추가 포지션/레버리지 증가 없음.
- 편도 fee 5bp + adverse slippage 2bp + 이전 완성 bar range/open ×0.02.
- 진입/청산 시간 모두 거래량 양수 필요. 매매 불가 경계 생략은 별도 집계하고 승격 금지.
- 신호/진입/청산 모두 평가 구간 안에 있어야 함. 각 구간 마지막 23:00 진입은
  다음 구간으로 나가므로 경계 신호 1개씩 제외. 가격/시간 보간 없음.

수익률은 10,000 USDT에서 시작하는 **계좌 수익률**이며 cash 시간을 포함하는
calendar-hour Sharpe입니다. 실제 비용을 낮춰 보이는 사후 재튜닝은 하지 않았습니다.

| 자산 | 기간 | 순수익률 | Sharpe | 최대 낙폭 | 완료 거래 |
| --- | --- | ---: | ---: | ---: | ---: |
| BTC | discovery 2022~2023 | -53.29% | -9.76 | -53.30% | 2,189 |
| BTC | validation 2024~2025 | -49.80% | -9.20 | -49.84% | 2,192 |
| BTC | stress 2026-01~08 | -24.40% | -11.67 | -24.53% | 728 |
| ETH | discovery 2022~2023 | -55.59% | -8.22 | -55.69% | 2,189 |
| ETH | validation 2024~2025 | -51.12% | -7.24 | -51.13% | 2,192 |
| ETH | stress 2026-01~08 | -23.49% | -8.96 | -23.80% | 728 |

6/6 primary 구간과 10/10 연도별 구간 모두 음수입니다. 거래 불가 경계 생략은 0건입니다.
하루 3번 가까이 반복하는 짧은 거래의 비용이 누적되었습니다. 예를 들어 BTC validation은
현재 capital path에서 gross +326.94 USDT지만 execution cost 5,306.49 USDT였습니다.

동일한 거래 시각/stop을 유지한 비용 0 진단:

| 자산 | 2022~2023 | 2024~2025 | 2026-01~08 |
| --- | ---: | ---: | ---: |
| BTC | -0.65% | +6.08% | -3.32% |
| ETH | -2.01% | +8.91% | -0.80% |

2024~2025만 약한 gross 효과가 있고 이전과 최근 stress에서는 음수입니다.
따라서 거래비용을 줄이는 것만으로 모든 기간에 통하는 방향성이 회복되지 않습니다.
**REJECTED, 고정 trial 1개 종료.** 시간대·방향·holding·수수료/슬리피지 조정으로
같은 family를 재시험하지 않습니다.

모형 한계: 1h OHLC의 시가는 정확한 밀리초 체결을 보장하지 않습니다. 청산과 정산
사이의 실제 지연/legging을 검증한 결과가 아니며, 경계 직전 체결 가정과 stop 시각은
사전등록한 연구 규약입니다. 이 낙관적인 시간 가정에서도 후보는 비용 포함 탈락했습니다.

## SHADOW 보존과 검증

기존 3개 전략 및 tracking 관련 7개 source의 SHA256은 작업 전과 동일합니다.
기존 refresh runner를 실제 실행해 BTC/ETH 각각 1h 22개, 4h 6개 완성 봉을 추가했습니다.
확인 당시 1h 최신 2026-09-12 04:00 UTC, 공통 1h/4h 최신 00:00 UTC입니다.
position-cap/breadth/dual-confirmed 모두 4/4 데이터셋 TRACKING, 최소 완료 거래 0입니다.
기존 shadow start/파라미터 변경, 새 SHADOW 등록, paper/live 연결은 없습니다.

전체 pytest **252개 통과**, 변경 파일 basedpyright 오류/경고 0, ruff 통과,
wheel/sdist 빌드 성공. 실데이터 pre-settlement CLI와 --help 및 헤지 synthetic
library driver를 직접 실행했습니다. 헤지 전략의 실데이터 수익성 검증은 데이터
게이트 때문에 수행하지 않았습니다.

## 재현 및 근거

```bash
uv run python -m quant_lab.research.presettlement_study
uv run pytest -q
uv run python -m quant_lab.research.shadow_status --root artifacts/edge_search --refresh
```

- `artifacts/edge_search/carry/source_manifest.csv`: 새 spot 114개 원본.
- `artifacts/edge_search/participation/source_manifest.csv`: 재검증한 USD-M 349개 원본.
- `artifacts/edge_search/carry/spot_incomplete_monthly_rows.csv`
- `artifacts/edge_search/carry/{BTCUSDT,ETHUSDT}_spot_missing_hours.csv`
- `artifacts/edge_search/carry/spot_checks/cross_source_check.csv`: 일별/REST 대조.
- `artifacts/edge_search/carry/frozen_shadow_before.sha256`
- `artifacts/edge_search/presettlement/presettlement_results.csv`
- `artifacts/edge_search/presettlement/annual_primary_results.csv`
- `artifacts/edge_search/presettlement/*_{net,zero_cost}_{trades.csv,equity.parquet}`
- `artifacts/edge_search/carry/presettlement_run.log`, `build.log`

주요 공식 출처는 Binance public-data README, checksum 동반 월별·일별 아카이브,
`https://api.binance.com/api/v3/klines`입니다. 원본 close-time을 임의로 정상화하거나,
기록에 없는 현물 봉을 만들어 거래한 결과는 없습니다.

구현 commit: `d826700c4cbe64485c8618e9c4fd9a5497a3adfd`, `8fe3cd84f729f50ca1db5904e5afb6fb229f1034`.
기계 판독 판정·원본/결과 SHA256: `docs/edge-evidence-2026-09-12.json`.

## 다른 원리의 Edge 조사와 Binance–Bybit 실측 검증

`docs/nonmomentum-edge-research-2026-09-12.md`에 네 경제 메커니즘의 공식 자료,
데이터 검증, 반론, 미확인 항목과 다음 순서를 정리했습니다.

Binance–Bybit 같은 자산 펀딩 차이는 `docs/cross-exchange-prereg-2026-09-12.md`,
commit `b6b65f0`로 월간 고정 규칙 1개를 사전등록한 뒤 실제 백테스트했습니다.
두 거래소 지갑을 별도로 유지하며 무료 자금 이동이나 증거금 상계를 가정하지 않았습니다.
원본 API 222페이지와 Binance ZIP 349개, 가격 격자·펀딩 정산·재요청 일치를 검증했습니다.

| 자산 | 2022~2023 순수익 | 2024~2025 순수익 | 2026-01~08 순수익 | 판정 |
| --- | ---: | ---: | ---: | --- |
| BTC | -1.109% | -1.171% | -0.367% | REJECTED |
| ETH | -1.098% | -1.021% | -0.449% | REJECTED |

비용 0이면 여섯 구간이 모두 양수이나, 현재 비용 계약에서는 펀딩 차이 수입이 너무
작습니다. 동일 holding/lookback/fee를 사후 조정하지 않습니다. 가격·funding·cost 합계는
최종 NAV와 일치했고 거래 불가 경계 생략·담보 게이트 위반은 0건입니다.

만기선물–perp는 원본/정산 데이터의 접근성을 확인해 NEXT로 올립니다. 정확한 정산 사건
시각과 전체 계약·공통 데이터가 먼저 필요하며 금융 trial은 0회입니다. 옵션 VRP와
예정된 토큰 언락은 데이터/시점 계약 부족으로 BLOCKED-DATA, 금융 trial 0회입니다.
이 세 후보를 PASS 또는 SHADOW로 표시하지 않습니다.

기존 SHADOW 3개의 7개 관련 source와 자동화 설정은 보존했습니다.
새 코드 포함 전체 테스트 307개와 변경 파일 타입 검사·ruff·빌드가 통과했습니다.

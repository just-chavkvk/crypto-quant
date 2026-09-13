# Edge research — 2026-09-13

이번 회차는 CoinYeon을 새 데이터 카탈로그로 조사한 뒤, 1순위 온체인 후보를 **고정 trial 1회** 검증했다.
상세 기능별 판정과 원출처 검증은 `docs/coinyeon-source-audit-2026-09-13.md`에 기록했다.

## 확인된 것

- CoinYeon 온체인은 MVRV, LTH/STH, 지갑 크기별 공급/변화, 실현손익, 채굴·네트워크 등
  장기 일간 지표와 CSV 다운로드 UI를 제공한다.
- 온체인 원출처 Bitcoin Research Kit(Bitview)는 인증 없는 공개 API와 JSON/CSV series를
  제공한다. 실제로 MVRV 일간 **6,465개**를 내려받아 날짜 index와 정렬했고,
  `2010-09-26`부터 `2026-09-13`까지 non-null history를 확인했다.
- CoinYeon 고래타점은 Hyperliquid 기반 실시간/과거 타점을 보여주지만, 현재 공개 화면에서
  구조화된 전체 역사 export는 확인되지 않았다. 현재 승자 지갑을 과거에 소급 선택하면
  look-ahead/survivorship bias가 생기므로 future snapshot 방식이 필요하다.
- 파이어차트는 6거래소 통합호가/VPVR/벽 규모를 실시간으로 보여주지만 역사 export는
  확인되지 않았다. 기존 order-book `BLOCKED-DATA`를 해제하지 않는다.
- 공포·탐욕은 Alternative.me 원 API의 전체 history/CSV로 재현 가능하다.
- 경제 캘린더는 개별 지표의 과거 actual/forecast/previous 발표 기록을 제공한다.

## 연구 우선순위

1. `REJECTED`: **BTC holder-cohort flow regime**. 아래 고정 trial에서 discovery/validation 모두 실패.
2. `NEXT-PROSPECTIVE`: **Hyperliquid whale crowding**. 매일 동일 시각 roster/방향/notional을
   저장하고 이후 수익만 평가. 현재 상위 고래를 과거에 소급 적용하지 않음.
3. `NEXT-DATA`: **ETF flow surprise**. 전체 역사 원출처 확정 후 flow/AUM 또는 rolling surprise를
   사전등록하고 평가.
4. `BLOCKED-DATA`: CoinYeon 파이어차트/청산맵은 역사 원본 확보 전 금융 trial 금지.

## 실제 수집 증거

- `artifacts/edge_search/coinyeon_source_audit/mvrv_day1.csv`
- rows: 6,465 + header
- first non-null: `2010-09-26`, value `6.0`
- last: `2026-09-13`, value `1.445784`
- SHA256: `0d528eb2ec86304ef03d4178f13d0504345c7d0c8ce64573533092363b76c90e`

소스 조사 단계에서는 후보 규칙·threshold·holding을 정하지 않았고, 이후 아래 별도 사전등록을 만든 뒤 수익률을 계산했다.

## BTC holder-cohort flow regime: 실제 검증

수익률을 보기 전에 `docs/holder-cohort-flow-prereg-2026-09-13.md`에 고정 trial 1개를 등록했다. Bitview 일간 원본의 `lth_supply_delta_1m_rate_ratio`, `sth_supply_delta_1m_rate_ratio`, `utxos_over_10k_btc_supply_delta_1w_rate_ratio` 세 시리즈만 사용했다. LTH 증가 + STH 감소 + 1만 BTC 초과 코호트 증가를 accumulation(+1), 세 방향의 완전한 반대를 distribution(-1)로 정의했다. 같은 regime이 이어지는 날짜는 중복 이벤트로 세지 않았다.

Bitview의 `date`, `price`, 세 feature는 모두 6,465행으로 길이가 일치했다. 원본 응답 SHA256은 `artifacts/edge_search/holder_cohort_flow/source_manifest.csv`에 기록했다. 일간 label의 역사적 계산 완료 시각이 별도 제공되지 않으므로 signal day D에서 2일을 지연해 D+2 가격에 진입하고 D+9 가격으로 정확히 7일 forward return을 계산했다. 왕복 14bp 비용을 고정 차감했다.

| 기간 | 이벤트 | Long / Short | 평균 net signed return | 중앙값 | 승률 | 누적 event return | 최악 event | gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2022-2023 discovery | 65 | 33 / 32 | -0.720% | -0.353% | 46.15% | -48.74% | -22.99% | FAIL |
| 2024-2025 validation | 43 | 12 / 31 | -1.184% | -0.209% | 44.19% | -44.49% | -14.70% | FAIL |
| 2026-01-01~08-31 stress | 19 | 15 / 4 | -1.750% | +0.633% | 52.63% | -31.81% | -22.21% | FAIL |

**REJECTED, 고정 trial 1개 종료.** Discovery와 validation 모두 평균 net signed return이 음수이고 승률도 50% 미만이다. 2026 stress는 중앙값과 승률이 양호해 보이지만 평균이 -1.75%로 큰 손실 event에 끌렸고, 기존 규칙상 2026 자체도 pristine holdout이 아니다. 따라서 이 결과를 보고 sign, 1m/1w horizon, 10k-BTC bucket, 2일 lag, 7일 hold, 비용 또는 반대 방향을 바꿔 같은 family를 되살리지 않는다.

이번 trial은 방향 예측 pre-screen이다. futures funding/borrow/liquidation을 포함한 실행 가능한 전략 백테스트가 아니며, pre-screen 단계에서 이미 실패했으므로 그런 정밀 실행 모델로 승격하지 않는다.

재현 자료:

- `src/quant_lab/research/holder_cohort_flow.py`
- `tests/test_holder_cohort_flow.py`
- `artifacts/edge_search/holder_cohort_flow/source.parquet`
- `artifacts/edge_search/holder_cohort_flow/source_manifest.csv`
- `artifacts/edge_search/holder_cohort_flow/events.csv`
- `artifacts/edge_search/holder_cohort_flow/summary.csv`

## Hyperliquid whale crowding: prospective shadow 시작

과거 승자 지갑을 현재 성과로 고른 뒤 과거에 소급하는 생존편향을 피하기 위해,
`docs/hyperliquid-whale-shadow-prereg-2026-09-13.md`에 미래 관찰 규칙을 먼저 고정했다.

- Hyperliquid 공개 leaderboard에서 account value >= 100,000 USDC,
  7일 PnL > 0, 30일 PnL > 0인 계정만 남긴다.
- 그중 all-time PnL 상위 20개 주소를 첫 실행에서 동결하고 이후 교체하지 않는다.
- 각 주소의 `clearinghouseState`에서 BTC/ETH perp open position만 읽는다.
- signed notional은 `sign(szi) * positionValue`, crowding은
  `sum(signed notional) / sum(abs notional)`이다.
- crowding의 부호만 신호로 고정한다. 양수 long, 음수 short, 0 neutral.
- `allMids`의 같은 시점 mid를 저장하고, 다음 1일/7일 수익률만 미래 데이터로 평가한다.

첫 실제 snapshot은 **2026-09-13 11:02:49 UTC**에 성공했다. frozen roster는 20개다.

| 자산 | mid | long / short 계정 | gross notional | signed notional | crowding | 현재 signal |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| BTC | 76,566.50 | 3 / 3 | $28.26M | -$22.24M | -0.7872 | short |
| ETH | 2,470.85 | 3 / 3 | $15.01M | -$13.79M | -0.9187 | short |

이 수치는 **현재 crowding 관측값**이지 수익성 증거가 아니다. 1일/7일 forward 결과가 아직
존재하지 않으므로 상태는 `SHADOW/TRACKING`이다. 최소 30개 daily snapshot과 각 horizon별
10개 이상의 완료 non-zero 관측이 쌓이기 전에는 승격 판정을 하지 않는다.

재현 자료:

- `src/quant_lab/research/hyperliquid_whale_shadow.py`
- `tests/test_hyperliquid_whale_shadow.py`
- `artifacts/edge_search/hyperliquid_whale_shadow/frozen_roster.csv`
- `artifacts/edge_search/hyperliquid_whale_shadow/positions_20260913T110249Z.parquet`
- `artifacts/edge_search/hyperliquid_whale_shadow/snapshots.csv`

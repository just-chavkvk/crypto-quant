# CoinYeon source audit — 2026-09-13

목적: CoinYeon을 새 Edge의 출발점으로 사용할 수 있는지, 화면 기능을 그대로 믿기 전에
과거 데이터 계약·원출처·수집 가능성을 분리해 확인한다. 이 문서는 데이터 소스 조사이며
수익성 trial은 0회다. 2026 역사자료는 기존 규칙대로 stress history로만 취급한다.

## 결론

CoinYeon 전체를 크롤링 대상으로 삼는 것보다 **데이터 카탈로그/아이디어 탐색 UI로 사용하고,
원출처가 확인되는 데이터는 원출처에서 직접 수집**하는 편이 재현성과 장기 유지에 유리하다.
특히 온체인 화면은 Bitcoin Research Kit(Bitview) 원출처를 명시하며, Bitview는 공개 REST API와
JSON/CSV 시계열을 제공한다. 반면 고래·파이어차트·청산맵 같은 실시간 기능은 화면 가치가
높아도 공개 역사 export가 확인되지 않아 같은 방법으로 과거 백테스트 자료라고 부를 수 없다.

## 기능별 판정

| 기능 | 화면에서 확인한 범위 | 백데이터 판정 | 연구 사용법 |
| --- | --- | --- | --- |
| Bitcoin 온체인 | MVRV, LTH/STH, 지갑 크기별 공급, SOPR/실현손익, 채굴/네트워크 등 수십 지표. 여러 화면에 `CSV 내려받기`, 전체/5년 등 범위 제공 | **BACKTESTABLE** | CoinYeon이 표시한 원출처 Bitview/BRK에서 직접 API 수집. 일간 feature로 사용 |
| 고래 타점/추적 | Hyperliquid 고래 현재 포지션, 7일/30일/전체 손익, 진입·청산 위치. 등업 설명은 일부 지갑의 수년 손익 추이와 과거 타점을 표시한다고 설명 | **PROSPECTIVE / 역사 export 미확인** | 현재 상위 고래를 과거에 적용하면 survivorship/look-ahead bias. 오늘부터 point-in-time snapshot을 쌓거나, 전체 주소가 합법적으로 확보되면 Hyperliquid 원 API에서 제한 범위 fills를 검증 |
| 파이어차트 | BTC 무기한 6거래소 통합, 5m~1d, 통합호가/VPVR/벽 규모 | **PROSPECTIVE** | 실시간 order-book/liquidity feature 후보. 공개 역사 export 확인 전 과거 백테스트 금지 |
| 청산맵 | 가이드에서 기능 존재 확인 | **BLOCKED-DATA** | 기존 liquidation 연구와 마찬가지로 완전한 과거 event tape 확보 전 수익성 trial 금지 |
| 현물 ETF 흐름 | BTC/ETH, 최근 20영업일 ETF별 유출입과 출시 이후 누적 차트 | **PARTIAL** | 2024 이후 이벤트 연구 후보. CoinYeon 화면만으로 전체 행 export가 확인되지 않아 원출처 확정 후 사용 |
| 공포·탐욕 | CoinYeon 최대 범위 차트, 3천일 이상 역사 위치 표시. 출처 Alternative.me 명시 | **BACKTESTABLE / 낮은 우선순위** | Alternative.me 공식 API가 전체 history와 CSV 제공. 가격·변동성 파생 성격이 강해 새 정보축 우선순위는 낮음 |
| 경제 캘린더 | CPI/FOMC 등 일정, 개별 지표 페이지에 역사 발표·예측·이전값 | **BACKTESTABLE 후보** | 발표 surprise(event actual-consensus)와 BTC 반응 연구 가능. 각국 공식 발표시각/수정치 시점 계약을 먼저 고정 |
| 슈퍼차트/AI 지표 | 차트 및 proprietary AI 지표 | **관찰용** | 역사 신호 export와 계산식이 확인되지 않으면 독립 백테스트 feature로 사용하지 않음 |
| 김프 | 가이드에서 기능 존재 확인 | **재구성 가능, CoinYeon history 미확인** | 필요하면 한국 거래소·글로벌 거래소·FX의 원데이터로 직접 PIT 재구성 |
| 롱숏클럽 | 커뮤니티 게시물/관점 | **비정형** | 신호 데이터로 바로 쓰지 않음. 별도 NLP 연구를 하더라도 publication time과 삭제/수정 이력을 보존해야 함 |

## 실제 원출처 검증

### Bitcoin Research Kit / Bitview

- CoinYeon 온체인 `시장 참여자 수익률(MVRV)` 화면은 데이터 출처를 Bitcoin Research Kit
  (`bitview.space`)로 표시한다.
- Bitview API는 Series를 JSON/CSV로 제공하며 인증 없이 조회할 수 있다.
- `GET /api/series/search?q=mvrv`에서 `mvrv`, `lth_mvrv`, `sth_mvrv` 등 다수의
  관련 시리즈가 실제 반환됐다.
- `GET /api/series/mvrv/day1/len`은 **6,465**를 반환했다.
- `GET /api/series/mvrv/day1/latest`는 조사 시점 **1.445784**를 반환했다.
- 날짜 index와 MVRV 배열을 직접 내려받아 정렬했으며, 날짜는
  `2009-01-01`~`2026-09-13`, MVRV 최초 non-null은 `2010-09-26`, 최신은
  `2026-09-13`이었다.
- 재현 artifact: `artifacts/edge_search/coinyeon_source_audit/mvrv_day1.csv`
  (6,465행 + header), SHA256
  `0d528eb2ec86304ef03d4178f13d0504345c7d0c8ce64573533092363b76c90e`.
- `lth_supply`, `lth_supply_delta_1w`, `utxos_over_10k_btc_supply_delta_1w` 등
  보유자/고래 cohort 시리즈도 검색 결과에서 실제 확인했다.

이 결과만으로도 **CoinYeon에서 발견한 온체인 아이디어를 원출처의 장기 일간 데이터로
재현해 백테스트할 수 있음**이 확인됐다.

### Alternative.me

CoinYeon 공포·탐욕 화면은 `alternative.me`를 출처로 표시한다. 공식 API 문서는
`/fng/?limit=0`으로 전체 history, `format=csv`로 CSV를 제공한다고 명시한다.

### Hyperliquid

CoinYeon 고래 화면은 Hyperliquid Whale Tracker다. Hyperliquid 공식 `info` endpoint는
주소별 `userFills`와 `userFillsByTime`을 제공하지만 최근 fills 수에 제한이 있다.
따라서 **오늘 수익률이 높은 고래를 먼저 고른 뒤 그 과거 거래를 검증하는 방식은 금지**한다.
그 방식은 survivorship/look-ahead bias가 크다. 고래 Edge는 앞으로의 point-in-time roster와
포지션 변화를 먼저 저장하는 future-shadow 설계가 적절하다.

## 다음 Edge 우선순위

1. **BTC holder-cohort flow regime — 후속 고정 trial에서 REJECTED**. 실제 결과는
   `docs/edge-search-2026-09-13.md`와 `docs/holder-cohort-flow-prereg-2026-09-13.md`를 따른다.
2. **Point-in-time Hyperliquid whale crowding** — 2026-09-13 첫 roster 20개와 snapshot을 실제로
   고정해 `SHADOW/TRACKING`을 시작했다. 과거에 소급 적용하지 않고 미래 1d/7d 수익만 평가한다.
3. **ETF flow surprise** — 전체 history 원출처를 확정한 뒤 `flow / AUM` 또는 rolling surprise로
   정규화해 다음 영업일/1주 BTC 반응을 검증한다. 원본 전체 행 확보 전 trial 0 유지.
4. **Firechart/order-book pressure** — 과거 원본이 없으므로 historical Edge 탐색 대신 future
   snapshot collector 후보로만 둔다.

## 출처

- https://coinyeon.kr/onchain
- https://coinyeon.kr/onchain/mvrv
- https://coinyeon.kr/onchain/lth-supply
- https://coinyeon.kr/onchain/supply-delta-wallet
- https://coinyeon.kr/whale-taten
- https://coinyeon.kr/firechart
- https://coinyeon.kr/fear-greed
- https://coinyeon.kr/calendar
- https://bitview.space/api
- https://alternative.me/crypto/fear-and-greed-index/
- https://hyperliquid.gitbook.io/Hyperliquid-docs/for-developers/api/info-endpoint

## 접근 경계

CoinYeon의 공개 화면/가이드는 조사에 사용했다. 사이트의 robots 정책에서 `/api/`와
`/orderbook` 등은 자동 수집 제외로 표시되어 있으므로 숨은 CoinYeon API를 역추적해 수집하는
방식은 사용하지 않았다. 원출처가 공개 API를 제공하는 경우에만 그 원출처 API를 사용한다.

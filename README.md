# Crypto Quant Lab

BTC/ETH 시장에서 **Alpha / Edge 후보를 찾고, 백테스트와 검증으로 가짜 전략을 최대한 걸러내는 Quant Research Lab**입니다.

이 저장소의 v0.1 목적은 자동매매가 아닙니다. Live Trading, 실제 자금 주문, 거래소 API key를 이용한 주문, AI Agent 실행은 현재 범위에 포함하지 않습니다.

## Architecture

```text
Public OHLCV (CCXT / Binance)
        ↓
Parquet cache + gap / duplicate checks
        ↓
Strategy signal (-1 / 0 / +1 target position)
        ↓
Lookahead guard
        ↓
Next-bar-open execution backtester
        ├─ adverse slippage
        ├─ volatility-aware slippage
        ├─ candle-volume participation cap
        ├─ risk-budget sizing + stop loss
        ├─ entry + exit fees
        └─ Trade Ledger
        ↓
Performance metrics + BTC Buy & Hold benchmark
        ↓
Train / Out-of-Sample / Walk-Forward validation
        ↓
Cross-asset / cross-timeframe Edge family search
        ↓
PASS / FAIL research verdict
```

기존 v0.1은 신호를 한 칸 shift한 뒤 close-to-close 수익률에 곱하는 구조였습니다. 실행 시점과 실제 진입/청산 가격을 거래 원장과 정확히 맞추기 어렵기 때문에, 현재 엔진은 **t 시점 종가로 만들어진 신호를 t+1 봉 시가에 체결**하는 방식으로 바꿨습니다.

### Execution contract

- 전략은 현재 봉까지의 데이터로 신호를 만듭니다.
- 신호는 한 봉 뒤의 시가에서 체결됩니다.
- slippage는 주문 방향에 불리하게 적용됩니다.
- fee는 진입과 청산 양쪽에 각각 적용됩니다.
- 백테스트 마지막에 열린 포지션은 마지막 종가에서 강제 청산해 원장을 닫습니다.
- 현재 v0.1 전략 신호는 `-1 / 0 / +1`의 discrete target입니다.
- `risk_per_trade`와 `stop_loss_pct`를 함께 지정하면 손절까지의 거리로 포지션 크기를 계산하고, 봉의 high/low가 손절선을 건드리면 손절을 실행합니다.
- `max_volume_participation`을 지정하면 한 봉의 거래량 중 허용한 비율만 체결하고, 목표 수량에 도달할 때까지 다음 봉에서 이어서 진입합니다.
- `volatility_slippage_multiplier`를 지정하면 high-low 범위가 큰 봉일수록 불리한 체결 가격을 추가로 반영합니다.

## Install

```bash
uv sync --extra dev
uv run quant --help
```

## Download BTC / ETH OHLCV

Public OHLCV만 사용하므로 API key가 필요 없습니다.

지원 심볼:

- `BTC/USDT`
- `ETH/USDT`

지원 timeframe:

- `1h`
- `4h`

```bash
uv run quant data download BTC/USDT --timeframe 1h
uv run quant data download ETH/USDT --timeframe 4h
```

시작일/종료일도 지정할 수 있습니다.

```bash
uv run quant data download BTC/USDT \
  --timeframe 1h \
  --start 2023-01-01T00:00:00Z \
  --end 2024-01-01T00:00:00Z
```

데이터는 `data/cache/binance/<SYMBOL>/<TIMEFRAME>.parquet`에 저장됩니다. pagination, timestamp 정렬, 중복 제거, 누락 candle 검사, 기존 cache 재사용, 앞/뒤/중간 누락 구간 재수집을 처리합니다.

## Backtest + Trade Ledger + Benchmark

```bash
uv run quant test data/cache/binance/BTC_USDT/1h.parquet \
  --symbol BTC/USDT \
  --fee-bps 5 \
  --slippage-bps 2 \
  --risk-per-trade-pct 1 \
  --stop-loss-pct 2 \
  --max-volume-participation-pct 10 \
  --volatility-slippage-multiplier 0.25 \
  --ledger-out artifacts/btc-ledger.csv
```

Trade Ledger에는 다음 값이 기록됩니다.

- symbol
- entry time / entry price / entry fill price
- exit time / exit price / exit fill price
- position size
- gross PnL
- fee
- slippage cost
- net PnL
- return %
- holding period

성과 지표는 다음을 계산합니다.

- Total Return
- CAGR
- Max Drawdown
- Sharpe Ratio
- Sortino Ratio
- Win Rate
- Loss Rate
- Profit Factor
- Average Win
- Average Loss
- Expectancy
- Number of Trades

BTC 전략은 같은 데이터로 BTC Buy & Hold benchmark를 자동 표시합니다. ETH 전략 등에서 별도 BTC benchmark를 쓰려면 `--benchmark-path`를 지정할 수 있습니다. benchmark에도 전략과 동일한 fee/slippage 설정이 적용됩니다.

## Walk-Forward validation

```bash
uv run quant walk-forward data/cache/binance/BTC_USDT/1h.parquet \
  --symbol BTC/USDT \
  --train-bars 1000 \
  --test-bars 250
```

출력은 반드시 세 구간을 따로 보여줍니다.

- `TRAIN`
- `OUT OF SAMPLE`
- `WALK FORWARD`

현재 보수적 v0.1 판정은 각 OOS window의 Total Return과 Sharpe가 양수이고, 연결된 Walk-Forward Total Return도 양수일 때만 PASS입니다. Train에서 좋아 보여도 OOS에서 무너지면 FAIL입니다.

## Parameter sweep

EMA와 breakout 설정을 여러 조합으로 자동 실행하고 Walk-Forward 결과가 좋은 순서대로 보여줍니다.

```bash
uv run quant sweep data/cache/binance/BTC_USDT/1h.parquet \
  --symbol BTC/USDT \
  --fast-values 10,20,50 \
  --slow-values 50,100,200 \
  --breakout-values 10,20,40 \
  --train-bars 1000 \
  --test-bars 250 \
  --top 10 \
  --results-out artifacts/sweep.csv
```

`fast >= slow`인 잘못된 조합은 자동으로 제외합니다. 순위는 Walk-Forward PASS 여부, Sharpe, Total Return 순서로 정렬합니다.

## Edge family search

하나의 숫자 조합만 잘 맞는 전략을 고르는 대신, 서로 다른 원리의 Edge를 각각 여러 설정으로 시험합니다.

연구 이력의 기준 문서는 [`docs/edge-research-ledger.md`](docs/edge-research-ledger.md)입니다. 새 Edge를 조사하거나 백테스트한 뒤에는 반드시 원장에 가설, 데이터, 시험 수, 판정, 재검토 조건을 남깁니다. 이미 `REJECTED`된 가설은 데이터·메커니즘·실행 가정 중 하나가 실질적으로 달라지지 않는 한 그대로 다시 시험하지 않습니다.

연구 결과와 코드 구현은 가능한 한 별도 커밋으로 남깁니다. 연구 한 묶음이 끝나면 `docs: record ... edge research` 형태의 문서 커밋을 만들고, 실제 전략/수집기/백테스터 변경은 별도 기능 커밋으로 연결합니다. 생성된 대용량 `artifacts/`와 임시 `.omo/` 저널은 Git에 넣지 않고, 재현에 필요한 파일명과 결과 요약만 연구 원장에 기록합니다.

- Momentum: 일정 기간 강했던 방향이 이어지는지
- Donchian breakout: 이전 고점을 돌파한 뒤 추세가 이어지는지
- Volume breakout: 거래량 증가를 동반한 돌파가 더 강한지
- Volatility breakout: 평소보다 큰 가격 움직임을 동반한 돌파가 더 강한지

각 후보는 BTC/ETH와 1h/4h에서 같은 시간 길이로 변환되어 비교됩니다. 2020~2023은 후보 탐색, 2024~2025는 별도 검증에 사용하고, 각 Edge 가족의 대표 설정을 고른 뒤에만 2026 데이터를 마지막 holdout 시험에 사용합니다.

```bash
uv run quant edge-search \
  artifacts/edge_search/BTC_USDT_1h_raw.parquet \
  artifacts/edge_search/ETH_USDT_1h_raw.parquet \
  artifacts/edge_search/BTC_USDT_4h_raw.parquet \
  artifacts/edge_search/ETH_USDT_4h_raw.parquet \
  --risk-per-trade-pct 1 \
  --stop-loss-pct 5 \
  --results-out artifacts/edge_search/edge_families.csv
```

2026 결과는 가족 대표를 선택한 뒤에만 열어봅니다. 따라서 2026 성적이 좋았던 설정으로 다시 고르는 방식의 과최적화를 막습니다.

## Lookahead protection

백테스트 자체는 신호를 다음 봉 시가에 실행합니다. 추가로 `assert_no_lookahead`가 미래 행을 잘라냈을 때 과거 신호가 바뀌는 전략을 탐지합니다. 이 검사는 미래 `shift(-1)` 같은 명백한 누수를 잡는 방어선이며, 모든 형태의 데이터 누수를 자동으로 증명하는 도구는 아닙니다.

## Validation commands

```bash
uv run ruff check .
uv run basedpyright
uv run pytest -q
uv run quant --help
uv run quant data --help
```

GitHub Actions도 같은 검증 순서를 실행합니다.

## Forward shadow tracking

역사 검증을 통과한 `global-position cap momentum`과 `breadth-confirmed momentum`은 2026-09-11 00:00 UTC 이후 데이터만 future shadow 증거로 사용합니다. 아래 명령은 Binance USD-M의 완전히 닫힌 BTC/ETH 1h·4h bar와 global long/short ratio를 증분 갱신한 뒤, 동결된 전략을 다시 평가합니다.

```bash
uv run python -m quant_lab.research.shadow_status --root artifacts/edge_search --refresh
```

신호 계산은 shadow 시작 이전의 336h/400h/2160h warm-up history를 유지하고, 성과만 shadow 시작 이후로 측정합니다. `WAITING_FOR_DATA`는 새 완성 bar가 없다는 뜻이고, `TRACKING`은 관찰 중, `READY_FOR_PAPER_REVIEW`는 BTC/ETH × 1h/4h 네 데이터셋이 모두 누적 수익률 > 0, Sharpe > 0, 거래 수 >= 10을 만족했다는 뜻입니다. 이 명령은 paper/live 주문을 실행하거나 자동 승격하지 않습니다.

## Explicitly out of scope for v0.1

- Live Trading
- 실제 돈 주문
- 거래소 주문 API key
- AI Agent 자동 실행
- paper/live execution adapter

다음 연구 단계는 살아남은 서로 다른 Edge 가족을 paper trading에서 동시에 추적하고, funding/OI/liquidation 데이터 기반 Edge와 order-book 기반 event-driven validation을 추가하는 것입니다.

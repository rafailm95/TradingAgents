# Verified market mode — CPU pilot

This branch adds two independent controls:

1. `strict_output_quality=True` on `TradingAgentsGraph` rejects incomplete,
   missing-stop-metadata, invalid-tool and empty responses before downstream
   consumption. Structured failures stop instead of retrying as free text.
   It is **opt-in**; existing default behavior is preserved. Completion checks
   do not establish factual accuracy. Provider stop metadata must be supported.
2. `python -m tradingagents.verified_market` is a **separate, narrower workflow**:
   code validates the input, computes indicators and renders every factual
   statement; a local model ranks existing evidence IDs in two perspectives.
   Unknown IDs, wrong polarity, duplicate IDs, extra fields, malformed JSON and
   truncated responses stop the run before its next stage. There is no free-text
   fallback and no investment rating, order, price forecast or allocation.

The market mode currently accepts only a caller-supplied **Coinbase BTC-USD UTC
daily** CSV, with columns `Date,Open,High,Low,Close,Volume`. The caller is
responsible for the declared provenance; the CSV itself does not authenticate
the exchange or asset. At least 200 consecutive daily candles are required.
Future rows are excluded before calculations; missing/stale/non-finite or
incoherent candles are rejected. All observations remain visible even when the
model omits one in its ranking. An empty perspective skips its model call.

## Run the reproduced experiment

Linux x64, Python 3.12 was tested. The standalone mode shares this repository's
dependencies. The runtime/model download is approximately 1.3 GB; allow several
GB of RAM. The measured host had approximately 10 GB RAM and used 6 CPU threads.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python scripts/setup_verified_runtime.py --runtime-dir ../tradingagents-runtime
.venv/bin/python scripts/run_verified_pilot.py \
  --runtime-dir ../tradingagents-runtime \
  --csv examples/verified_market/btc_coinbase.csv \
  --as-of 2026-10-15 \
  --output ../verified-run-001
```

The output directory must be new. The supervisor starts a temporary loopback
llama.cpp server, executes the two-perspective research run, then deliberately
limits a full-graph model response to one token to verify rejection. Finally it
stops the server, including on errors. No paid API credentials are forwarded.
The worker restricts Python sockets and curl calls; this is **not an OS network
sandbox**. There is no persistent service or scheduled execution.

Open `research/report.md` for the complete observations. Inspect `snapshot.json`,
`call_01.json`, `call_02.json`, `rankings.json` and `summary.json` for audit data.
`live_failure_test/summary.json` records the deliberate rejection test. Model
request and response bodies are saved, including rejected responses. A failed
research run writes `summary.json` but no final report.

To use an already running local server:

```bash
.venv/bin/python -m tradingagents.verified_market \
  --csv examples/verified_market/btc_coinbase.csv \
  --as-of 2026-10-15 --output ../verified-research-002 \
  --base-url http://127.0.0.1:18080/v1 --model qwen-pilot
```

Only literal loopback HTTP URLs are accepted; redirects and HTTP proxies are
disabled. The model must support the requested JSON schema response format.

## Enable the full-graph completion guard

```python
from copy import deepcopy
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = deepcopy(DEFAULT_CONFIG)
config["strict_output_quality"] = True
# Configure an appropriate provider/model before constructing the graph.
graph = TradingAgentsGraph(config=config)
```

This flag alone does **not** remove invented numbers or narratives from the full
debate graph. The constrained mode is the tested way of preventing arbitrary
model-authored financial claims from reaching the report.

## Measured result: 2026-10-16

Frozen input: 257 daily candles, 2026-02-01 through 2026-10-15, SHA-256
`b6b1ea73fc8f3872fecda65f9864447d800076d76ab628bb8d50ab8e78b137b6`.
Model: Qwen3.5-2B Q4_K_M, same model and candle data as the previous full-graph
experiment. Runtime: llama.cpp b11687, temperature 0, reasoning off.

| Measurement | Previous full graph | Constrained mode |
|---|---:|---:|
| Model calls, excluding separate baseline/failure test | 12 | 2 |
| Measured workflow time, excluding startup | 738.27 s | 6.43 s |
| Truncated responses | 6 | 0 |
| Technical acceptance | Rejected | Accepted |

These are **different scopes**, not a like-for-like model quality benchmark.
The constrained mode ranks existing facts instead of running investment/risk
debates and generating a portfolio rating. One run does not establish general
reliability or profitable trading. A separate live full-graph fault injection
stopped after exactly one truncated response, with zero downstream model calls.

In the accepted output, the close was below EMA10, VWMA and Bollinger middle,
above SMA50/200; MACD histogram was negative and RSI was neutral under the
declared thresholds. All these relationships are computed, not asserted by AI.
No news, macroeconomic evidence, institutional flows, cross-venue checks or
forward returns were supplied. Support/risk labels are descriptive heuristics.

## Focused regression checks

```bash
.venv/bin/python -m pytest \
  tests/test_verified_market.py tests/test_structured_agents.py \
  tests/test_structured_agent_prompts.py tests/test_graph_end_to_end.py \
  tests/test_checkpoint_lifecycle.py tests/test_checkpoint_resume.py \
  tests/test_dataflows_config.py tests/test_yahoo_snapshot.py \
  tests/test_analyst_execution.py -q
```

Result: **129 passed**, including rejection-before-consumption, no fallback on
strict failures, malformed data/JSON, wrong evidence polarity and future-data
isolation. Unit tests use synthetic fixtures; the reported model experiment uses
the frozen public market dataset. Tested packages include pandas 3.0.6,
stockstats 0.6.9 and langchain-core 1.6.11. Ruff was not installed and was not run.

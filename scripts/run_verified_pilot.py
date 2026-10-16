"""Start a temporary local llama.cpp server, run research and a live failure test.

The runtime directory must contain llama-b11687/llama-server and
Qwen3.5-2B-Q4_K_M.gguf from the separately pinned CPU pilot setup.
No downloads, credentials, paid endpoints, persistent service or broker orders.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def worker(args):
    from langchain_core.callbacks import BaseCallbackHandler

    from tradingagents.agents.output_quality import OutputQualityError
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph import trading_graph
    from tradingagents.verified_market import LocalRanker, run, write_json

    # Python-level containment, not an operating-system network sandbox.
    original_connect = socket.socket.connect

    def local_only(sock, address):
        if not isinstance(address, tuple) or address[:2] != ("127.0.0.1", 18080):
            raise RuntimeError("Worker permits only the local model server")
        return original_connect(sock, address)

    socket.socket.connect = local_only
    from curl_cffi import requests as curl_requests

    def no_external_curl(*_args, **_kwargs):
        raise RuntimeError("External data calls disabled in frozen-data worker")

    curl_requests.Session.request = no_external_curl
    output = Path(args.output)
    ranker = LocalRanker("http://127.0.0.1:18080/v1", "qwen-pilot")
    result = run(args.csv, args.as_of, output / "research", ranker)
    print(json.dumps(result), flush=True)

    # Actual full-graph integration test: deliberately exhaust the first model
    # response after one token. A second call or a returned rating is a failure.
    fault_dir = output / "live_failure_test"
    fault_dir.mkdir()

    class Recorder(BaseCallbackHandler):
        raise_error = True

        def __init__(self):
            self.count = 0
            self.reasons = []

        def on_chat_model_start(self, serialized, messages, **kwargs):
            self.count += 1
            if self.count > 1:
                raise AssertionError("Graph continued after rejected output")

        def on_llm_end(self, response, **kwargs):
            write_json(fault_dir / "model_response.json", {
                "outputs": [[g.message.model_dump(mode="json") for g in batch]
                            for batch in response.generations]})
            self.reasons = [g.message.response_metadata.get("finish_reason")
                            for batch in response.generations for g in batch]

    recorder = Recorder()
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg.update(llm_provider="openai_compatible", backend_url="http://127.0.0.1:18080/v1",
               quick_think_provider=None, deep_think_provider=None,
               quick_think_backend_url=None, deep_think_backend_url=None,
               deep_think_llm="qwen-pilot", quick_think_llm="qwen-pilot",
               llm_max_retries=0, max_tokens=1, temperature=0, strict_output_quality=True,
               max_tool_rounds=3, max_debate_rounds=1, max_risk_discuss_rounds=1,
               max_recur_limit=32, checkpoint_enabled=False, output_language="English",
               data_cache_dir=str(fault_dir / "cache"), results_dir=str(fault_dir / "results"),
               memory_log_path=str(fault_dir / "memory.md"))
    cfg["data_vendors"] = {key: "disabled" for key in cfg["data_vendors"]}
    cfg["tool_vendors"] = {}
    trading_graph.resolve_instrument_identity = lambda _ticker: {"name": "Bitcoin", "quote_type": "CRYPTOCURRENCY"}
    write_json(fault_dir / "config.json", cfg)
    graph = trading_graph.TradingAgentsGraph(selected_analysts=["market"], config=cfg, callbacks=[recorder])
    try:
        graph.propagate("BTC-USD", args.as_of, asset_type="crypto")
    except OutputQualityError as exc:
        if recorder.count != 1 or recorder.reasons != ["length"]:
            raise AssertionError("Test failed for a reason other than intended truncation") from exc
        write_json(fault_dir / "summary.json", {"status": "PASS", "blocked": str(exc),
                   "model_calls": recorder.count, "finish_reasons": recorder.reasons,
                   "downstream_model_calls": 0, "rating_produced": False})
        print("Live full-graph truncation test: PASS; no downstream call", flush=True)
    else:
        raise AssertionError("Strict graph accepted deliberately truncated output")
    write_json(output / "summary.json", {"research": result["status"], "live_failure_test": "PASS",
               "research_model_calls": ranker.calls, "fault_injection_model_calls": recorder.count,
               "paid_api_calls": 0, "orders": 0, "profitability_evaluated": False})


def supervise(args):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    runtime = Path(args.runtime_dir).resolve()
    env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "SYSTEMROOT", "TEMP", "TMP") if key in os.environ}
    env.update(PYTHON_DOTENV_DISABLED="1", LANGCHAIN_TRACING_V2="false", LANGSMITH_TRACING="false",
               DO_NOT_TRACK="1", NO_PROXY="127.0.0.1,localhost", PYTHONUNBUFFERED="1")
    cmd = [str(runtime / "llama-b11687/llama-server"), "-m", str(runtime / "Qwen3.5-2B-Q4_K_M.gguf"),
           "--host", "127.0.0.1", "--port", "18080", "--alias", "qwen-pilot", "-c", "16384",
           "-np", "1", "-t", "6", "-tb", "6", "-n", "256", "--reasoning", "off", "--jinja",
           "--no-context-shift", "--no-webui", "--no-agent", "--no-ui-mcp-proxy", "--timeout", "180",
           "--cors-origins", "http://localhost"]
    (output / "server_command.json").write_text(json.dumps(cmd, indent=2))
    with (output / "server.log").open("w") as log:
        server = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    raise RuntimeError("Model server exited; inspect server.log")
                try:
                    with urllib.request.urlopen("http://127.0.0.1:18080/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.5)
            else:
                raise RuntimeError("Local model server startup timeout")
            print("Local model ready; starting constrained research", flush=True)
            return subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker",
                                   "--runtime-dir", str(runtime), "--csv", str(Path(args.csv).resolve()),
                                   "--as-of", args.as_of, "--output", str(output.resolve())],
                                  cwd=REPO, env=env, timeout=360).returncode
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
            print("Temporary local model server stopped", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args)
    else:
        raise SystemExit(supervise(args))


if __name__ == "__main__":
    main()

"""Constrained BTC-USD research mode: code owns facts; a local model ranks IDs.

This is deliberately separate from the full TradingAgents debate graph. It
does not generate ratings, orders, price forecasts, or free-form model claims.
Run: python -m tradingagents.verified_market --help
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd
from stockstats import wrap

from tradingagents.agents.output_quality import OutputQualityError

INDICATORS = (
    "close_10_ema", "close_50_sma", "close_200_sma", "vwma",
    "boll", "boll_ub", "boll_lb", "rsi", "macd", "macds", "macdh", "atr",
)
MISSING = (
    "News, fundamentals, macroeconomic evidence and institutional flows were not supplied.",
    "Volume alone does not identify institutional buying or selling.",
    "One exchange only; no independent price-source reconciliation.",
    "No forward returns, trading costs or profitability were tested.",
)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def build_snapshot(csv_path, as_of):
    """Validate uninterrupted UTC daily candles and compute every reported fact.

    The caller attests that this file contains Coinbase BTC-USD candles. A hash
    identifies the supplied file; it does not independently authenticate it.
    Rows after the cutoff are excluded before any calculation.
    """
    path = Path(csv_path)
    raw = path.read_bytes()
    frame = pd.read_csv(path)
    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    if any(name not in frame for name in required):
        raise ValueError("Missing OHLCV column")
    cutoff = pd.Timestamp(as_of, tz="UTC")
    if cutoff.strftime("%Y-%m-%d") != as_of:
        raise ValueError("Expected canonical YYYY-MM-DD cutoff")
    frame = frame[required].copy()
    frame["Date"] = pd.to_datetime(frame.Date, utc=True, errors="raise")
    if frame.Date.isna().any() or (frame.Date != frame.Date.dt.normalize()).any():
        raise ValueError("Expected midnight UTC daily dates")
    excluded = int((frame.Date > cutoff).sum())
    frame = frame.loc[frame.Date <= cutoff].copy()
    if len(frame) < 200 or not frame.Date.is_unique or not frame.Date.is_monotonic_increasing:
        raise ValueError("Need at least 200 unique, sorted daily candles")
    if frame.Date.iloc[-1] != cutoff:
        raise ValueError("No candle on requested date; stale data rejected")
    if not frame.Date.diff().dropna().eq(pd.Timedelta(days=1)).all():
        raise ValueError("Missing daily candles")
    for column in required[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        if not frame[column].map(math.isfinite).all():
            raise ValueError("Non-finite OHLCV value")
    if not (frame[["Open", "High", "Low", "Close"]] > 0).all().all():
        raise ValueError("Nonpositive price")
    if (frame.Volume < 0).any():
        raise ValueError("Negative volume")
    if (frame.High < frame[["Open", "Close", "Low"]].max(axis=1)).any():
        raise ValueError("High is inconsistent with candle")
    if (frame.Low > frame[["Open", "Close", "High"]].min(axis=1)).any():
        raise ValueError("Low is inconsistent with candle")

    stock = wrap(frame.copy())
    values = {name: float(stock[name].iloc[-1]) for name in INDICATORS}
    if not all(math.isfinite(value) for value in values.values()):
        raise ValueError("Non-finite indicator")
    # Independent arithmetic checks for the levels misquoted in the first run.
    direct = {
        "close_50_sma": float(frame.Close.tail(50).mean()),
        "close_200_sma": float(frame.Close.tail(200).mean()),
        "boll": float(frame.Close.tail(20).mean()),
        "close_10_ema": float(frame.Close.ewm(span=10, adjust=True).mean().iloc[-1]),
    }
    if any(not math.isclose(values[key], value, rel_tol=1e-9, abs_tol=1e-8)
           for key, value in direct.items()):
        raise ValueError("Indicator calculation disagrees with independent formula")
    close = float(frame.Close.iloc[-1])
    facts = []

    def add(fact_id, polarity, text):
        facts.append({"id": fact_id, "polarity": polarity, "text": text})

    for fact_id, indicator, label in (
        ("ema10", "close_10_ema", "EMA10"),
        ("sma50", "close_50_sma", "SMA50"),
        ("sma200", "close_200_sma", "SMA200"),
        ("vwma", "vwma", "VWMA"),
        ("boll_middle", "boll", "Bollinger middle (20-day mean)"),
    ):
        reference = values[indicator]
        relation = "above" if close > reference else "below" if close < reference else "equal to"
        polarity = "support" if close > reference else "risk" if close < reference else "neutral"
        add(fact_id, polarity, f"Close {close:,.2f} USD is {relation} {label} {reference:,.2f} USD.")
    hist = values["macdh"]
    add("macd_hist", "support" if hist > 0 else "risk" if hist < 0 else "neutral",
        f"MACD histogram is {hist:,.2f} ({'positive' if hist > 0 else 'negative' if hist < 0 else 'zero'}).")
    rsi = values["rsi"]
    rsi_zone = "oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral"
    add("rsi", "neutral", f"RSI is {rsi:.2f}: {rsi_zone} using thresholds 30 and 70; this is not a reversal forecast.")
    add("atr", "neutral", f"ATR is {values['atr']:,.2f} USD ({100 * values['atr'] / close:.2f}% of close); it is not a price target.")
    latest = {key: float(frame.iloc[-1][key]) for key in required[1:]}
    return {
        "symbol": "BTC-USD", "source": "User-supplied Coinbase Exchange daily candle file",
        "volume_unit": "BTC", "as_of": as_of, "rows": len(frame),
        "first_date": frame.Date.iloc[0].strftime("%Y-%m-%d"),
        "excluded_future_rows": excluded, "csv_sha256": hashlib.sha256(raw).hexdigest(),
        "latest_ohlcv": latest, "indicators": values, "independent_checks": direct,
        "facts": facts, "missing_evidence": list(MISSING),
        "interpretation": "Support/risk labels are descriptive technical heuristics, not validated return predictions.",
        "indicator_convention": "Installed stockstats defaults; SMA and Bollinger middle plus EMA10 independently checked.",
    }


def selection_schema(snapshot, polarity):
    eligible = [fact["id"] for fact in snapshot["facts"] if fact["polarity"] == polarity]
    return {
        "type": "object", "additionalProperties": False,
        "properties": {"ranked_ids": {"type": "array", "items": {"type": "string", "enum": eligible},
                                      "minItems": min(1, len(eligible)), "maxItems": min(3, len(eligible)),
                                      "uniqueItems": True}},
        "required": ["ranked_ids"],
    }


def validate_selection(value, snapshot, polarity):
    """Treat grammar enforcement as assistance, never as the validation gate."""
    eligible = {fact["id"] for fact in snapshot["facts"] if fact["polarity"] == polarity}
    if not isinstance(value, dict) or set(value) != {"ranked_ids"}:
        raise OutputQualityError("Unexpected selection fields")
    ids = value["ranked_ids"]
    if (not isinstance(ids, list) or any(not isinstance(item, str) for item in ids)
            or not min(1, len(eligible)) <= len(ids) <= min(3, len(eligible))):
        raise OutputQualityError("Invalid selection length or type")
    if len(set(ids)) != len(ids) or not set(ids) <= eligible:
        raise OutputQualityError("Unknown, duplicate or wrong-polarity evidence ID")
    return ids


def parse_completion(response):
    choices = response.get("choices", [])
    if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
        raise OutputQualityError("Incomplete or ambiguous local model response")
    message = choices[0].get("message", {})
    if message.get("refusal") or message.get("tool_calls") or message.get("function_call"):
        raise OutputQualityError("Unexpected refusal or tool call")
    try:
        # Duplicate keys are invalid even if the last value would validate.
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate JSON key")
                result[key] = value
            return result
        return json.loads(message["content"], object_pairs_hook=unique_object)
    except (KeyError, TypeError, ValueError) as exc:
        raise OutputQualityError("Invalid JSON model output") from exc


class LocalRanker:
    """Two calls maximum, no SDK retry, no auth, proxies or redirects."""

    def __init__(self, base_url, model):
        parsed = urllib.parse.urlsplit(base_url)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path != "/v1"):
            raise ValueError("Only http://127.0.0.1:PORT/v1 is permitted")
        self.url = base_url + "/chat/completions"
        self.model = model
        self.calls = 0

    def __call__(self, snapshot, polarity, audit_dir):
        if self.calls >= 2:
            raise OutputQualityError("Two-call limit reached")
        self.calls += 1
        payload = {
            "model": self.model, "temperature": 0, "max_tokens": 256,
            "messages": [
                {"role": "system", "content": "Rank up to three supplied evidence IDs relevant to the requested perspective. "
                 "Use only IDs with that polarity. Return JSON with ranked_ids only, most important first. "
                 "Never add prose, numbers, new evidence, forecasts or trading instructions."},
                {"role": "user", "content": json.dumps({"symbol": snapshot["symbol"], "as_of": snapshot["as_of"],
                 "perspective": polarity, "facts": snapshot["facts"]})},
            ],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "EvidenceRanking", "strict": True, "schema": selection_schema(snapshot, polarity)}},
        }

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                raise OutputQualityError("Redirect rejected")

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        record = {"role": polarity, "request": payload}
        started = time.monotonic()
        try:
            request = urllib.request.Request(self.url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
            with opener.open(request, timeout=120) as response:
                record["response"] = json.load(response)
            value = parse_completion(record["response"])
            validate_selection(value, snapshot, polarity)
            record["accepted"] = True
            return value
        except Exception as exc:
            record.update(accepted=False, error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            record["seconds"] = time.monotonic() - started
            write_json(Path(audit_dir) / f"call_{self.calls:02}.json", record)


def render_report(snapshot, rankings):
    lines = ["# BTC-USD — verified technical observations", "",
             f"As of {snapshot['as_of']}; {snapshot['rows']} daily candles; volume in BTC.", "",
             "All statements and numbers below are rendered by code. The model only ranks evidence IDs.", "",
             "| Evidence | Observation |", "|---|---|"]
    lines.extend(f"| {fact['id']} | {fact['text']} |" for fact in snapshot["facts"])
    lines += ["", "## Model prioritization", ""]
    for polarity, ids in rankings.items():
        lines.append(f"- {polarity}: {', '.join(ids) if ids else 'No eligible observations.'}")
    polarities = {fact["polarity"] for fact in snapshot["facts"]}
    lines += ["", "## Scope", "",
              "Technical observations include both supportive and adverse signals."
              if {"support", "risk"} <= polarities else "Technical observations are listed without a return forecast.",
              snapshot["interpretation"], snapshot["indicator_convention"], ""]
    lines.extend(f"- {item}" for item in snapshot["missing_evidence"])
    lines += ["", "No investment rating, order or portfolio allocation is produced.", "",
              f"Input SHA-256: `{snapshot['csv_sha256']}`", ""]
    return "\n".join(lines)


def run(csv_path, as_of, output_dir, ranker):
    """Validate each stage before the next; no report exists after a rejection."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    accepted_roles = []
    try:
        snapshot = build_snapshot(csv_path, as_of)
        write_json(output / "snapshot.json", snapshot)
        rankings = {}
        for polarity in ("support", "risk"):
            # Empty perspectives need no model call (and no empty JSON enum).
            eligible = any(fact["polarity"] == polarity for fact in snapshot["facts"])
            value = ranker(snapshot, polarity, output) if eligible else {"ranked_ids": []}
            rankings[polarity] = validate_selection(value, snapshot, polarity)
            accepted_roles.append(polarity)
        report = render_report(snapshot, rankings)
        write_json(output / "rankings.json", rankings)
        (output / "report.md").write_text(report, encoding="utf-8")
        summary = {"status": "ACCEPTED_TECHNICAL_OUTPUT", "accepted_roles": accepted_roles,
                   "seconds": time.monotonic() - started, "profitability_evaluated": False,
                   "mode": "constrained evidence ranking; not the full debate graph"}
        write_json(output / "summary.json", summary)
        return summary
    except Exception as exc:
        write_json(output / "summary.json", {"status": "REJECTED", "accepted_roles": accepted_roles,
                   "seconds": time.monotonic() - started, "error_type": type(exc).__name__, "error": str(exc)})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, help="Frozen Coinbase BTC-USD daily OHLCV CSV")
    parser.add_argument("--as-of", required=True, help="YYYY-MM-DD; exact latest required daily candle")
    parser.add_argument("--output", required=True, help="New directory; existing directories rejected")
    parser.add_argument("--base-url", default="http://127.0.0.1:18080/v1")
    parser.add_argument("--model", default="qwen-pilot")
    args = parser.parse_args()
    print(json.dumps(run(args.csv, args.as_of, args.output, LocalRanker(args.base_url, args.model)), indent=2))


if __name__ == "__main__":
    main()

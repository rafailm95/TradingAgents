"""Replayable prospective virtual portfolios; no order or account interface."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
import math
from pathlib import Path
import re
from urllib.request import Request, urlopen

from tradingagents import expanded_journal as journal

PROTOCOL = journal.REPO / "docs/EXPANDED_PAPER_PROTOCOL.json"
PROTOCOL_SHA256 = "2c5a363c70491c89745235749242a2f467240caa59f62c391f6c4bc8d814fd43"


def _time(value):
    return journal._utc(datetime.fromisoformat(value))


def contract():
    raw = journal.source_bytes(PROTOCOL.read_bytes())
    if journal.digest(raw) != PROTOCOL_SHA256:
        raise ValueError("Frozen paper protocol mismatch")
    spec = journal.strict_json(raw)
    if spec["watchlist_sha256"] != journal.WATCHLIST_SHA256:
        raise ValueError("Paper watchlist mismatch")
    build = journal.digest(journal.source_bytes(Path(__file__).read_bytes()))
    return raw, spec, build


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("Invalid quote number")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError("Quote price must be finite and positive")
    return number


def validate_quote(quote, observation, recorded_at, spec):
    if not isinstance(quote, dict) or set(quote) != {
        "endpoint", "request_started_at_utc", "response_received_at_utc", "response_body_utf8"
    }:
        raise ValueError("Invalid quote evidence envelope")
    if quote["endpoint"] != spec["quote_endpoint"]:
        raise ValueError("Unexpected quote endpoint")
    body = quote["response_body_utf8"]
    if not isinstance(body, str) or len(body.encode("utf-8")) > spec["quote_max_bytes"]:
        raise ValueError("Quote response exceeds bounded size")
    ticker = journal.strict_json(body)
    if not isinstance(ticker, dict):
        raise ValueError("Invalid ticker response")
    bid, ask = _number(ticker["bid"]), _number(ticker["ask"])
    if bid > ask:
        raise ValueError("Crossed bid/ask quote")
    started = _time(quote["request_started_at_utc"])
    received = _time(quote["response_received_at_utc"])
    traded = _time(ticker["time"])
    observed = _time(observation["observed_at_utc"])
    if not observed <= started <= received <= recorded_at:
        raise ValueError("Quote must follow observation and precede recording")
    if not observed <= traded <= received:
        raise ValueError("Last-trade time precedes observation or is in the future")
    if (received - started).total_seconds() > spec["quote_max_request_seconds"]:
        raise ValueError("Quote request took too long")
    if (recorded_at - received).total_seconds() > spec["quote_max_record_delay_seconds"]:
        raise ValueError("Quote became stale before recording")
    if (received - traded).total_seconds() > spec["last_trade_max_age_seconds"]:
        raise ValueError("Last-trade time is stale")
    expected_day = (recorded_at.date() - timedelta(days=1)).isoformat()
    if observation["as_of_utc_day"] != expected_day or received.date() != recorded_at.date():
        raise ValueError("Signal is stale or UTC date rolled over")
    return bid, ask, received


def fetch_quote():
    """Exactly one bounded unauthenticated GET; no retry, credentials or orders."""
    _, spec, _ = contract()
    started = journal._utc(journal.utc_now())
    request = Request(spec["quote_endpoint"], headers={"User-Agent": "TradingAgents-paper-research/1"})
    with urlopen(request, timeout=spec["quote_timeout_seconds"]) as response:
        if response.status != 200 or response.geturl() != spec["quote_endpoint"]:
            raise ValueError("Unexpected quote HTTP status or redirect")
        raw = response.read(spec["quote_max_bytes"] + 1)
    received = journal._utc(journal.utc_now())
    if len(raw) > spec["quote_max_bytes"]:
        raise ValueError("Quote response exceeds bounded size")
    return {"endpoint": spec["quote_endpoint"], "request_started_at_utc": started.isoformat(),
            "response_received_at_utc": received.isoformat(), "response_body_utf8": raw.decode("utf-8")}


def _book(previous, definition, cost, bid, ask, elapsed, spec):
    initial = spec["initial_cash_per_independent_book_usd"]
    previous = previous or {}
    cash, quantity = previous.get("cash_usd", initial), previous.get("quantity_btc", 0.0)
    basis = previous.get("cost_basis_usd", 0.0)
    realized = previous.get("realized_pnl_usd", 0.0)
    paid_fees = previous.get("paid_fees_usd", 0.0)
    fills = previous.get("hypothetical_fill_count", 0)
    fee, slip = cost["fee_bps_per_side"] / 10000, cost["slippage_bps_per_side"] / 10000
    action, fill = ("HOLD" if quantity else "FLAT"), None
    if definition["id"] == "cash":
        entry, leave, fraction = False, False, 0.0
    elif definition["id"] == "buy_hold_50":
        entry, leave, fraction = not previous, False, 0.5
    else:
        entry, leave = definition["entry_condition"], definition["exit_condition"]
        fraction = definition["hypothetical_entry_fraction"]
    if not 0 <= fraction <= 0.5:
        raise ValueError("Entry allocation outside frozen bounds")
    if quantity > 0 and leave:
        price = bid * (1 - slip)
        gross = quantity * price
        charge = gross * fee
        proceeds = gross - charge
        fill = {"side": "SELL", "quantity_btc": quantity, "price_usd": price,
                "fee_usd": charge, "net_cash_change_usd": proceeds}
        cash += proceeds
        realized += proceeds - basis
        quantity, basis, action = 0.0, 0.0, "SELL"
    elif quantity == 0 and entry and not leave and fraction > 0:
        budget = cash * fraction
        price = ask * (1 + slip)
        quantity = budget / (price * (1 + fee))
        charge = quantity * price * fee
        fill = {"side": "BUY", "quantity_btc": quantity, "price_usd": price,
                "fee_usd": charge, "net_cash_change_usd": -budget}
        cash -= budget
        basis, action = budget, "BUY"
    if fill:
        paid_fees += fill["fee_usd"]
        fills += 1
    liquidation_position = quantity * bid * (1 - slip) * (1 - fee)
    liquidation_equity = cash + liquidation_position
    is_benchmark = definition["id"] in spec["benchmarks"]
    annual_opex = spec["benchmark_operating_cost_usd_per_year"] if is_benchmark else spec["candidate_operating_cost_usd_per_year"]
    operating_cost = annual_opex * elapsed / spec["year_seconds"]
    net_equity = liquidation_equity - operating_cost
    peak = max(previous.get("sampled_peak_net_equity_usd", initial), net_equity)
    drawdown = 1 - net_equity / peak
    result = {
        "id": definition["id"], "selection_class": definition.get("selection_class", "BENCHMARK"),
        "action": action, "fill": fill, "hypothetical_fill_count": fills,
        "cash_usd": cash, "quantity_btc": quantity, "cost_basis_usd": basis,
        "paid_fees_usd": paid_fees, "realized_pnl_usd": realized,
        "unrealized_liquidation_pnl_usd": liquidation_position - basis,
        "midpoint_equity_usd": cash + quantity * (bid + (ask - bid) / 2),
        "liquidation_equity_usd": liquidation_equity,
        "operating_cost_sensitivity_usd": operating_cost,
        "net_liquidation_equity_usd": net_equity,
        "net_pnl_usd": net_equity - initial,
        "net_return_fraction": net_equity / initial - 1,
        "sampled_peak_net_equity_usd": peak,
        "sampled_max_drawdown_fraction": max(previous.get("sampled_max_drawdown_fraction", 0.0), drawdown),
    }
    if cash < 0 or quantity < 0 or any(isinstance(v, float) and not math.isfinite(v) for v in result.values()):
        raise ValueError("Invalid portfolio arithmetic")
    journal.canonical(result)  # Also rejects non-finite nested fill values.
    return result


def _event(observation, quote, recorded_at, previous, spec, build):
    signal = observation["payload"]
    bid, ask, received = validate_quote(quote, signal, recorded_at, spec)
    prior = previous["payload"] if previous else None
    if prior and received <= _time(prior["valuation_at_utc"]):
        raise ValueError("Valuation clock must increase")
    started = prior["portfolio_started_at_utc"] if prior else received.isoformat()
    elapsed = (received - _time(started)).total_seconds()
    books = {}
    definitions = signal["candidates"] + [{"id": name} for name in spec["benchmarks"]]
    for scenario, cost in spec["cost_scenarios"].items():
        old_books = prior["books"][scenario] if prior else {}
        books[scenario] = {d["id"]: _book(old_books.get(d["id"]), d, cost, bid, ask, elapsed, spec)
                           for d in definitions}
    payload = {
        "schema_version": 1, "protocol_id": spec["protocol_id"], "protocol_sha256": PROTOCOL_SHA256,
        "ledger_build_sha256": build, "watchlist_sha256": signal["watchlist_sha256"],
        "observer_build_sha256": signal["observer_build_sha256"], "symbol": signal["symbol"],
        "as_of_utc_day": signal["as_of_utc_day"], "observation_record_sha256": observation["record_sha256"],
        "signal_observed_at_utc": signal["observed_at_utc"],
        "unrecorded_calendar_days_since_previous_signal": signal["unrecorded_days_since_previous"],
        "signal_to_quote_delay_seconds": (received - _time(signal["observed_at_utc"])).total_seconds(),
        "recorded_at_utc": recorded_at.isoformat(), "valuation_at_utc": received.isoformat(),
        "portfolio_started_at_utc": started, "quote": quote, "books": books,
        "previous_event_sha256": previous["event_sha256"] if previous else journal.ZERO_HASH,
        "orders": 0, "meaning": spec["meaning"], "data_authentication": spec["data_authentication"],
    }
    return {"payload": payload, "event_sha256": journal.digest(journal.canonical(payload))}


@contextmanager
def _observations(path, now):
    raw, spec, build = journal.contract()
    if path.is_symlink():
        raise ValueError("Invalid observation directory")
    if not path.exists():
        yield {}
        return
    if not path.is_dir():
        raise ValueError("Invalid observation directory")
    with journal._lock(path):
        yield journal._scan(path, raw, spec, build, now)


def _paths(journal_dir, ledger_dir):
    source, target = Path(journal_dir), Path(ledger_dir)
    a, b = source.resolve(), target.resolve()
    if a == b or a in b.parents or b in a.parents:
        raise ValueError("Journal and ledger need separate non-nested directories")
    if target.is_symlink() or target.exists() and not target.is_dir():
        raise ValueError("Invalid ledger directory")
    return source, target


def _replay(target, observations, now, raw, spec, build):
    if journal._bounded_read(target / "protocol.json") != raw:
        raise ValueError("Stored paper protocol mismatch")
    paths = []
    for path in target.iterdir():
        if path.name in {"protocol.json", ".record.lock"}:
            continue
        if path.is_symlink() or not path.is_file() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", path.name):
            raise ValueError("Unexpected ledger entry")
        paths.append(path)
    days = sorted(observations)
    if [p.stem for p in sorted(paths)] != days[:len(paths)] or len(paths) > len(days):
        raise ValueError("Ledger must consume every observation in order")
    events, previous = [], None
    for path in sorted(paths):
        event = journal.strict_json(journal._bounded_read(path))
        if not isinstance(event, dict) or set(event) != {"payload", "event_sha256"}:
            raise ValueError("Invalid ledger event envelope")
        payload = event["payload"]
        recorded = _time(payload["recorded_at_utc"])
        if recorded > now:
            raise ValueError("Ledger event is in the future")
        expected = _event(observations[path.stem], payload["quote"], recorded, previous, spec, build)
        if journal.canonical(expected) != journal.canonical(event):
            raise ValueError("Ledger replay mismatch: quote, accounting, source or chain changed")
        events.append(event)
        previous = event
    return events


def _result(observations, events):
    last = events[-1]["payload"] if events else None
    return {"status": "VERIFIED" if events else "NOT_STARTED", "events": len(events),
            "observations": len(observations), "pending_observations": len(observations) - len(events),
            "latest_observation_day": max(observations) if observations else None,
            "last_valuation_at_utc": last["valuation_at_utc"] if last else None,
            "books": last["books"] if last else None, "orders": 0}


def verify(journal_dir, ledger_dir):
    raw, spec, build = contract()
    now = journal._utc(journal.utc_now())
    source, target = _paths(journal_dir, ledger_dir)
    with _observations(source, now) as observations:
        if not target.exists():
            return _result(observations, [])
        with journal._lock(target):
            return _result(observations, _replay(target, observations, now, raw, spec, build))


def _ready(result, now):
    if result["observations"] == 0:
        return "WAITING_FOR_OBSERVATIONS"
    if result["pending_observations"] == 0:
        return "ALREADY_RECORDED"
    if result["pending_observations"] != 1:
        raise ValueError("Multiple unconsumed observations; cannot backfill old executions")
    if result["latest_observation_day"] != (now.date() - timedelta(days=1)).isoformat():
        raise ValueError("Unconsumed observation is stale; cannot backfill an execution")
    return "READY"


def prepare(journal_dir, ledger_dir):
    result = verify(journal_dir, ledger_dir)
    return {**result, "status": _ready(result, journal._utc(journal.utc_now()))}


def record(journal_dir, ledger_dir, quote):
    raw, spec, build = contract()
    now = journal._utc(journal.utc_now())
    source, target = _paths(journal_dir, ledger_dir)
    with _observations(source, now) as observations:
        # Only read/validate before initializing a new directory.
        if not target.exists():
            ready = _ready(_result(observations, []), now)
            if ready != "READY":
                return {"status": ready, "record_created": False, "orders": 0}
            _event(observations[max(observations)], quote, now, None, spec, build)
            target.mkdir(parents=True, exist_ok=True)
        with journal._lock(target):
            if not (target / "protocol.json").exists():
                if {p.name for p in target.iterdir()} != {".record.lock"}:
                    raise ValueError("Refuse to adopt nonempty uninitialized ledger")
                journal._write_new(target / "protocol.json", raw)
            events = _replay(target, observations, now, raw, spec, build)
            ready = _ready(_result(observations, events), now)
            if ready != "READY":
                return {"status": ready, "record_created": False, "orders": 0}
            # Re-read the actual clock after replay, so slow validation cannot
            # accidentally accept a stale quote or an intervening UTC rollover.
            recorded = journal._utc(journal.utc_now())
            event = _event(observations[max(observations)], quote, recorded,
                           events[-1] if events else None, spec, build)
            path = target / f"{event['payload']['as_of_utc_day']}.json"
            journal._write_new(path, journal.canonical(event) + b"\n")
            confirmed = _replay(target, observations, recorded, raw, spec, build)
            if confirmed[-1]["event_sha256"] != event["event_sha256"]:
                raise ValueError("Unexpected persisted event identity")
            return {**_result(observations, confirmed), "status": "RECORDED", "record_created": True,
                    "event_sha256": event["event_sha256"], "path": str(path)}

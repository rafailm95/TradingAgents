# Execution realism review — 2026-10-16

The current system is a useful research filter, but not a full exchange execution simulator. This is an assessment of the actual code, not a statement that more hardware or paid AI is needed.

## Established

Causal completed-candle signals; next-open historical fills; base/stress per-side fees and slippage; independent cash-conservation audits; chronological selection and walk-forward comparisons; delay sensitivity; versioned source/data; separate paper books using observed bid/ask timestamps and modeled expense. Historical losses and selection failures are preserved. The seven frozen paper hypotheses remain unchanged.

## Implemented in this slice

`execution_depth.py` walks one public aggregate Level2 snapshot for hypothetical USD250/1000/5000 entry budgets at assumed60/120bps fees. It floors quantity to base_increment, respects market minimum, keeps residual cash, and refuses inadequate liquidity, crossed/auction/halted markets. Aggregated size is used once, not multiplied by order count. Immediate same-snapshot bid liquidation is a cost diagnostic; it is not a forecast or actual fill. This standalone module is not integrated into the seven frozen paper contracts. It refuses insufficient depth rather than simulating an exchange's partial-fill policy. It does not model queue priority, cancel latency, adverse selection, future book changes, historical product rules or account-specific fee rounding.

The first real public-data probe was BLOCKED: the runtime tunnel returned403Forbidden for all3product-metadata requests. Zero order books were obtained and zero actual depth metrics exist. Synthetic tests passed, but they do not establish public connectivity or representative live costs. No automatic retry. Network permission review was cancelled; no approval was granted. Existing schedules remain enabled, but later success collecting quotes cannot be promised. Future task execution must report a real data failure instead of fabricating fills.

## Inputs that improve realism

1. Intended venue and interface (for example Coinbase Advanced rather than a generic brand), actual quote currency, and fee tier. Official Coinbase documentation says fees depend on product/tier and maker/taker behavior; the user's actual fee is not established by public generic tables. A fee-page screenshot without secrets is sufficient; no account credentials are needed for research.
2. Intended starting capital and tolerated loss. The USD10000 baseline is an assumption. Fixed USD120/year research expense would be24% ofUSD500,12% ofUSD1000,2.4% ofUSD5000,1.2% ofUSD10000, before trading returns. USD120 is a sensitivity assumption, not a verified bill. Entry-only50% allocations can drift above50% while held.
3. Reliable permitted public API connectivity, exact collection time and observed latency. The scheduled paper observation time differs from the historical next-midnight-open assumption. Extra1/2day signal lag is only sensitivity, not a faithful outage or queue model.
4. Venue-specific hourly/finer prices, bid/ask, depth, rounding, minimums, rejections and partial-fill rules. Daily closing drawdown misses intraday troughs; daily OHLCV does not recover an order book or within-bar event order. Snapshot liquidity is not a historical guarantee.
5. Untouched future data. A large search on correlated reused history raises selection risk. A180day/20exit monitoring gate is not statistical proof of an edge.

## Preferred next step

Continue the bounded historical search, and resolve venue/capital/fee assumptions plus public connectivity before introducing a versioned enhanced paper contract. Preserve the current two/five cohorts. Do not silently change their rules or rewrite accepted history. No broker credentials, paid AI or real orders are required for the current research.

Sources, checked2026-10-16:
- https://help.coinbase.com/en/coinbase/trading-and-funding/advanced-trade/advanced-trade-fees
- https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-book
- https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-single-product

RESOLVED: Weekly signal and standalone depth diagnostic tested.
OPEN: Genuine depth capture, venue/account costs, capital calibration, intraday execution.
IMPLEMENTATION_READY: Offline research YES; actual depth measurement BLOCKED.
MATERIAL_BLOCKER: Current runtime public API tunnel403; account assumptions unknown.
NEXT_IMPLEMENTATION_SLICE: Venue/capital calibration and permitted public-data capture.
DONE_CONDITION: Verified public snapshot provenance plus versioned execution contract tested on untouched observations.
EXECUTION_ENVIRONMENT: Python3.12 with research dependencies; public-data access required for capture.
REQUIRED_MODE: Research and virtual accounting only.

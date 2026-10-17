"""One preregistered causal family; no historical outcome optimization."""
from decimal import Decimal as D, localcontext
import math
import pandas as pd
from tradingagents.bybit_history import DAY, HOUR

NEW_CANDIDATES = ('funding_carry7_momentum28__fixed50',
                  'funding_carry7_momentum28__vol15_cap50')


def funding_signals(market, end):
    """Use only 21 settled rates in seven fully closed UTC days, not next funding."""
    if end % DAY or not market.start < end <= market.end:
        raise ValueError('Invalid complete-day signal boundary')
    frame = market.frame.iloc[:(end - market.start) // DAY].copy()
    index = list(range(market.start, end, DAY))
    if list(frame.Date.astype('int64') // 1_000_000) != index:
        raise ValueError('Daily frame mismatch')
    sums = []
    with localcontext() as ctx:
        ctx.prec = 128
        for day in index:
            # No missing events filled as zero. Final event is 16:00 of closed day.
            rates = [market.funding[t] for t in range(day, day + DAY, 8 * HOUR)]
            if any(not x.is_finite() for x in rates):
                raise ValueError('Invalid settled funding')
            sums.append(sum(rates, D(0)))
        affordable = [False] * len(index)
        for i in range(6, len(index)):
            # 1bp/settlement is a mechanism-derived reference, not an optimized threshold.
            affordable[i] = sum(sums[i-6:i+1], D(0)) <= D('.0001') * 21
    close = frame.Close.reset_index(drop=True)
    ready = close.shift(28).notna() & (pd.Series(range(len(index))) >= 6)
    entry = ready & (close > close.shift(28)) & pd.Series(affordable)
    leave = ready & ~entry
    vol = close.pct_change(fill_method=None).rolling(60, min_periods=60).std(ddof=1) * math.sqrt(365.25)
    return pd.DataFrame({'entry': entry.to_numpy(dtype=bool),
                         'exit': leave.to_numpy(dtype=bool),
                         'vol60': vol.to_numpy(), 'max_hold': 20}, index=index)


"""Preregistered experiment011: daily breakout with completed-week confirmation."""
from dataclasses import dataclass
import math
import pandas as pd
FAMILY = 'weekly_confirmed_breakout20'
SIZINGS = ('fixed50', 'vol15_cap50')

@dataclass(frozen=True)
class Candidate:
    family: str
    sizing: str
    def __post_init__(self):
        if self.family != FAMILY or self.sizing not in SIZINGS:
            raise ValueError('Unsupported preregistered weekly candidate')
    @property
    def id(self): return f'{self.family}__{self.sizing}'
CANDIDATES = tuple(Candidate(FAMILY, size) for size in SIZINGS)

def signals(frame):
    """Row t is evaluated after its daily UTC candle completes, never intraday.
    Sunday close becomes available on that completed Sunday row; Monday through
    Saturday retain the previous Sunday's values. Never use an incomplete week.
    """
    dates = pd.DatetimeIndex(frame.Date)
    if dates.tz is None or str(dates.tz) != 'UTC' or not dates.is_unique:
        raise ValueError('Unique UTC daily dates required')
    if not dates.equals(dates.normalize()) or not dates.is_monotonic_increasing:
        raise ValueError('Ordered UTC midnight dates required')
    if len(dates)>1 and not ((dates[1:]-dates[:-1])==pd.Timedelta(days=1)).all():
        raise ValueError('Contiguous daily dates required')
    close=frame.Close
    weekly=pd.Series(close.to_numpy(),index=dates).loc[dates.dayofweek==6]
    average=weekly.rolling(40,min_periods=40).mean()
    last_week=pd.Series(weekly.reindex(dates,method='ffill').to_numpy(),index=frame.index)
    mean40=pd.Series(average.reindex(dates,method='ffill').to_numpy(),index=frame.index)
    vol=close.pct_change(fill_method=None).rolling(60,min_periods=60).std(ddof=1)*math.sqrt(365.25)
    prior_high=frame.High.rolling(20,min_periods=20).max().shift(1)
    prior_low=frame.Low.rolling(10,min_periods=10).min().shift(1)
    ready=mean40.notna() & vol.notna() & prior_high.notna() & prior_low.notna()
    leave=ready & ((close<prior_low) | (last_week<mean40))
    enter=ready & (close>prior_high) & (last_week>mean40) & ~leave
    return pd.DataFrame({'entry':enter.fillna(False),'exit':leave.fillna(False),'vol60':vol,'max_hold':0,
        'completed_week_close':last_week,'completed_week_sma40':mean40})

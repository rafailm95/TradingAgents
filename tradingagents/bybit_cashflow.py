"""Decimal USDT-linear cash-flow kernel, not an exchange or liquidation simulator.
No signal generation, data fetching, margin-mode inference, orders or credentials.
Historical replay still requires the separate frozen protocol and complete inputs.
"""
from decimal import Decimal
try:
    from .bybit_history import number
except ImportError:
    from bybit_history import number

ZERO = Decimal(0)


def funding_cashflow(signed_quantity, mark_price, settled_rate):
    """Positive funding: long pays, short receives. Rate is a decimal fraction."""
    return -number(signed_quantity) * number(mark_price, positive=True) * number(settled_rate)


class LinearCashflow:
    def __init__(self, initial='10000', fee_bps='5.5'):
        self.initial = number(initial, positive=True)
        self.balance = self.initial
        self.fee_rate = number(fee_bps) / 10000
        if not 0 <= self.fee_rate < 1:
            raise ValueError('Invalid fee')
        self.quantity = ZERO
        self.entry_price = None
        self.price_pnl = ZERO
        self.fees = ZERO
        self.funding = ZERO
        self.expense = ZERO
        self.funding_times = set()

    def equity(self, mark_price, *, reserve_exit_fee=False):
        mark = number(mark_price, positive=True)
        unrealized = self.quantity * (mark - self.entry_price) if self.quantity else ZERO
        reserve = abs(self.quantity) * mark * self.fee_rate if reserve_exit_fee else ZERO
        return self.balance + unrealized - reserve

    def open(self, signed_quantity, fill_price, *, quantity_step, minimum_quantity,
             maximum_quantity, minimum_notional, entry_cap='0.5'):
        if self.quantity:
            raise ValueError('Position already open; no pyramiding in this kernel')
        q, price = number(signed_quantity), number(fill_price, positive=True)
        step = number(quantity_step, positive=True)
        minimum = number(minimum_quantity, positive=True)
        maximum = number(maximum_quantity, positive=True)
        min_value = number(minimum_notional, positive=True)
        cap = number(entry_cap, positive=True)
        if maximum < minimum or not 0 < cap <= Decimal('0.5'):
            raise ValueError('Invalid quantity limits or research entry cap')
        notional = abs(q) * price
        fee = notional * self.fee_rate
        if not q or abs(q) % step or not minimum <= abs(q) <= maximum or notional < min_value:
            raise ValueError('Quantity/precision/minimum constraint failed')
        if notional > self.balance * cap or notional + 2 * fee > self.balance:
            raise ValueError('Entry exceeds research cash/notional budget')
        self.balance -= fee
        self.fees += fee
        self.quantity, self.entry_price = q, price
        # Contract notional is not deducted as if purchasing a spot asset.
        self.reconcile(price)

    def settle_funding(self, timestamp_ms, mark_price, settled_rate):
        if type(timestamp_ms) is not int or timestamp_ms < 0 or timestamp_ms in self.funding_times:
            raise ValueError('Invalid/duplicate funding settlement')
        if self.funding_times and timestamp_ms <= max(self.funding_times):
            raise ValueError('Funding must be chronological')
        cash = funding_cashflow(self.quantity, mark_price, settled_rate)
        self.funding_times.add(timestamp_ms)
        self.balance += cash
        self.funding += cash
        self.reconcile(mark_price)
        return cash

    def operating_cost(self, amount):
        value = number(amount)
        if value < 0:
            raise ValueError('Negative operating expense')
        self.expense += value
        self.balance -= value

    def close(self, fill_price):
        if not self.quantity:
            raise ValueError('No position to close')
        price = number(fill_price, positive=True)
        gain = self.quantity * (price - self.entry_price)
        fee = abs(self.quantity) * price * self.fee_rate
        self.price_pnl += gain
        self.fees += fee
        self.balance += gain - fee
        self.quantity, self.entry_price = ZERO, None
        self.reconcile(price)
        return gain - fee

    def reconcile(self, mark_price):
        expected_cash = self.initial + self.price_pnl + self.funding - self.fees - self.expense
        if self.balance != expected_cash:
            raise ValueError('Cash conservation failure')
        mark = number(mark_price, positive=True)
        expected_equity = expected_cash + (self.quantity * (mark - self.entry_price) if self.quantity else ZERO)
        if self.equity(mark) != expected_equity:
            raise ValueError('Equity conservation failure')
        return True


def drawdown(samples, initial='10000'):
    """Cash amount at the same peak/trough as max percentage DD; also max cash DD."""
    start = number(initial, positive=True)
    peak = start; worst_pct = ZERO; amount_at_worst_pct = ZERO; max_cash = ZERO
    peak_at_worst = start; trough_at_worst = start
    for value in samples:
        equity = number(value)
        peak = max(peak, equity)
        amount = peak - equity
        pct = amount / peak * 100
        max_cash = max(max_cash, amount)
        if pct > worst_pct:
            worst_pct, amount_at_worst_pct = pct, amount
            peak_at_worst, trough_at_worst = peak, equity
    return {'max_drawdown_pct': str(worst_pct), 'cash_at_max_pct_drawdown_usdt': str(amount_at_worst_pct),
            'max_cash_drawdown_usdt': str(max_cash), 'peak_at_max_pct_usdt': str(peak_at_worst),
            'trough_at_max_pct_usdt': str(trough_at_worst)}

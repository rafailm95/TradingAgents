"""Independent hand-calculated USDT cash, funding-sign and drawdown oracles."""
from decimal import Decimal as D
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tradingagents'))
from bybit_cashflow import LinearCashflow, funding_cashflow, drawdown


def enter(ledger, quantity='10', price='100'):
    ledger.open(quantity, price, quantity_step='.1', minimum_quantity='.1',
                maximum_quantity='100', minimum_notional='5')


def test_long_cash_and_funding_independent_oracle():
    book = LinearCashflow('10000', '5.5'); enter(book)
    assert book.balance == D('9999.45')  # 1000 notional remains collateral, not a spot debit
    assert book.equity('110') == D('10099.45')
    assert book.settle_funding(0, '110', '.0001') == D('-.11')
    assert book.settle_funding(1, '105', '-.0002') == D('.21')
    book.operating_cost('1')
    book.close('120')
    # 10000 + 200 - .55 - .66 - .11 + .21 - 1
    assert book.balance == D('10197.89')
    assert book.quantity == 0 and book.reconcile('120')


def test_short_cash_and_funding_independent_oracle():
    book = LinearCashflow('10000', '10'); enter(book, '-10')
    assert book.equity('90') == D('10099')
    assert book.settle_funding(0, '90', '.0001') == D('.09')
    book.close('80')
    assert book.balance == D('10198.29')  # 10000 + 200 - 1 - .8 + .09


def test_flat_funding_is_zero_and_duplicate_fails():
    book = LinearCashflow()
    assert book.settle_funding(0, '100', '.01') == 0
    with pytest.raises(ValueError, match='duplicate'): book.settle_funding(0, '100', '.01')
    assert book.balance == 10000


@pytest.mark.parametrize('quantity', ['.05', '100.1', '51', '0', 'NaN'])
def test_invalid_or_overbudget_order_never_changes_cash(quantity):
    book = LinearCashflow()
    with pytest.raises(ValueError): enter(book, quantity)
    assert book.balance == 10000 and book.quantity == 0


def test_cash_drawdown_uses_actual_peak_not_initial_capital():
    result = drawdown(['12000', '9500', '11000'])
    assert D(result['cash_at_max_pct_drawdown_usdt']) == 2500
    assert D(result['max_drawdown_pct']) == D(2500) / D(12000) * 100
    assert D(result['peak_at_max_pct_usdt']) == 12000


def test_max_cash_drawdown_can_differ_from_max_percentage():
    result = drawdown(['10000', '8000', '20000', '17000'])
    assert D(result['max_drawdown_pct']) == 20
    assert D(result['cash_at_max_pct_drawdown_usdt']) == 2000
    assert D(result['max_cash_drawdown_usdt']) == 3000


def test_known_bybit_funding_example_and_signed_rate():
    assert funding_cashflow('10', '8000', '.0001') == -8
    assert funding_cashflow('-10', '8000', '.0001') == 8
    assert funding_cashflow('10', '8000', '-.0001') == 8

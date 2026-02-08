#!/usr/bin/env python3
from ib_insync import IB, Contract, Order
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

ib = IB()
ib.connect('127.0.0.1', 4004, clientId=103)

# SPY Put - Feb 21, 2026 (3rd Friday of February)
contract = Contract(
    symbol='SPY',
    secType='OPT',
    exchange='SMART',
    currency='USD',
    lastTradeDateOrContractMonth='20260221',
    strike=580.0,
    right='P',
    multiplier='100'
)

print('=' * 60)
qualified = ib.qualifyContracts(contract)
if qualified:
    print(f'✅ Contract qualified: {qualified[0].localSymbol}')
    
    ticker = ib.reqMktData(contract)
    ib.sleep(2)
    bid = ticker.bid if ticker.bid > 0 else 5.00
    print(f'Current bid: ${bid}')
    
    order = Order(action='SELL', orderType='LMT', totalQuantity=1, lmtPrice=bid)
    trade = ib.placeOrder(contract, order)
    ib.sleep(5)
    
    print(f'📊 Order ID: {trade.order.orderId}')
    print(f'📊 Status: {trade.orderStatus.status}')
    print(f'📊 Filled: {trade.orderStatus.filled}')
    if trade.orderStatus.filled > 0:
        print(f'✅ FILLED at ${trade.orderStatus.avgFillPrice}')
        print(f'💰 Premium collected: ${trade.orderStatus.avgFillPrice * 100:.2f}')
    else:
        print(f'⏳ Order working - check IB Gateway')
else:
    print('❌ Contract not found - trying alternate expiration')
    # Try Mar 21, 2026 (3rd Friday of March)
    contract.lastTradeDateOrContractMonth = '20260321'
    qualified = ib.qualifyContracts(contract)
    if qualified:
        print(f'✅ March contract found: {qualified[0].localSymbol}')

print('=' * 60)
ib.disconnect()

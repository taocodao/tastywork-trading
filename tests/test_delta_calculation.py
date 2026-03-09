import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.tqqq_turbocore.executor import calculate_delta_orders

class TestDeltaCalculation(unittest.TestCase):
    def test_basic_allocation(self):
        target = {"TQQQ": 0.8, "SGOV": 0.2}
        net_liq = 10000.0
        current_positions = {}
        live_prices = {"TQQQ": 40.0, "SGOV": 100.0}
        
        # 8000 / 40 = 200 TQQQ
        # 2000 / 100 = 20 SGOV
        orders = calculate_delta_orders(target, net_liq, current_positions, live_prices)
        
        self.assertEqual(len(orders), 2)
        # SGOV could be first or TQQQ. Both are BUY.
        
        tqqq_order = next(o for o in orders if o["symbol"] == "TQQQ")
        sgov_order = next(o for o in orders if o["symbol"] == "SGOV")
        
        self.assertEqual(tqqq_order["action"], "BUY")
        self.assertEqual(tqqq_order["quantity"], 200)
        self.assertEqual(sgov_order["action"], "BUY")
        self.assertEqual(sgov_order["quantity"], 20)

    def test_rebalance_sell_before_buy(self):
        target = {"TQQQ": 0.8, "SGOV": 0.2}
        net_liq = 10000.0
        # Currently 100% SGOV
        current_positions = {"TQQQ": 0, "SGOV": 100} 
        live_prices = {"TQQQ": 40.0, "SGOV": 100.0}
        
        # Need 20 SGOV -> Sell 80 SGOV
        # Need 200 TQQQ -> Buy 200 TQQQ
        orders = calculate_delta_orders(target, net_liq, current_positions, live_prices)
        
        self.assertEqual(len(orders), 2)
        
        # Sell comes first
        self.assertEqual(orders[0]["action"], "SELL")
        self.assertEqual(orders[0]["symbol"], "SGOV")
        self.assertEqual(orders[0]["quantity"], 80)
        
        self.assertEqual(orders[1]["action"], "BUY")
        self.assertEqual(orders[1]["symbol"], "TQQQ")
        self.assertEqual(orders[1]["quantity"], 200)

    def test_fractional_sweep(self):
        target = {"TQQQ": 0.8, "SGOV": 0.2}
        net_liq = 10000.0
        current_positions = {}
        # Make prices such that it doesn't divide evenly
        live_prices = {"TQQQ": 43.15, "SGOV": 100.12}
        
        # TQQQ Target: 8000 / 43.15 = 185.39 -> 185
        # SGOV Target: 2000 / 100.12 = 19.97 -> 19
        orders = calculate_delta_orders(target, net_liq, current_positions, live_prices)
        
        tqqq_order = next(o for o in orders if o["symbol"] == "TQQQ")
        sgov_order = next(o for o in orders if o["symbol"] == "SGOV")
        
        self.assertEqual(tqqq_order["quantity"], 185)
        self.assertEqual(sgov_order["quantity"], 19)

    def test_liquidation(self):
        target = {"TQQQ": 0.0, "SGOV": 1.0}
        net_liq = 10000.0
        current_positions = {"TQQQ": 100, "QQQ": 50, "SGOV": 10}
        live_prices = {"TQQQ": 40.0, "SGOV": 100.0, "QQQ": 400.0}
        
        # Should sell TQQQ (100) and QQQ (50)
        # Should buy 90 SGOV
        orders = calculate_delta_orders(target, net_liq, current_positions, live_prices)
        
        sells = [o for o in orders if o["action"] == "SELL"]
        buys = [o for o in orders if o["action"] == "BUY"]
        
        self.assertEqual(len(sells), 2)
        self.assertEqual(len(buys), 1)
        
        # Both sells should be at the start of the list
        self.assertEqual(orders[0]["action"], "SELL")
        self.assertEqual(orders[1]["action"], "SELL")

if __name__ == '__main__':
    unittest.main()

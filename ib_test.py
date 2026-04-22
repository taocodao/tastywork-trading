"""
IB Gateway Health Check
Verifies:
  1. ib_insync can connect to port 4004
  2. Live/delayed QQQ spot price is returned
  3. A simple option contract can be qualified
"""
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("ib_test")

sys.path.insert(0, "/home/ubuntu/tastywork-trading/iv-switching-composite")

# ── Test 1: Live spot price ──────────────────────────────────────────────────
print("\n=== TEST 1: IB Gateway Spot Price (QQQ) ===")
try:
    from ib_options_pricing import get_live_spot_prices  # type: ignore
    prices = get_live_spot_prices(["QQQ", "TQQQ", "SQQQ"])
    if prices and prices.get("QQQ", 0) > 0:
        print("PASS - IB spot prices returned:")
        for sym, px in prices.items():
            print("  " + sym + ": $" + str(round(px, 2)))
    else:
        print("FAIL - IB returned empty prices:", prices)
except Exception as e:
    print("ERROR - " + str(e))

# ── Test 2: Option contract qualification ────────────────────────────────────
print("\n=== TEST 2: Option Contract Qualification (QQQ Call) ===")
try:
    from ib_options_pricing import get_option_spread_quote  # type: ignore
    # Use a nearby strike — adjust if QQQ has moved significantly
    # This just tests connectivity and contract lookup, not exact pricing
    quote = get_option_spread_quote("QQQ", 480, 500, "260522", "C")
    if quote is not None:
        print("PASS - Option contract qualified")
        print("  short_mid: " + str(quote.short_mid))
        print("  long_mid:  " + str(quote.long_mid))
        print("  net_credit: " + str(quote.net_credit))
    else:
        print("WARN - Quote returned None (IB may be unavailable or strikes OTM)")
except Exception as e:
    print("ERROR - " + str(e))

print("\n=== DONE ===")

import os
import sys
from dotenv import load_dotenv
load_dotenv()
from tastytrade_client import TastytradeClient

client = TastytradeClient()
client.connect()
positions = client.get_positions()
for p in positions:
    print(f"Symbol: {p.symbol}, Type: {p.instrument_type}, Qty: {p.quantity}, Dir: {getattr(p, 'quantity_direction', None)}")

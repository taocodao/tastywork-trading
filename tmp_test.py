import sys, os
from datetime import date
sys.path.insert(0, r"D:\Projects\tastywork-trading-1")
sys.path.insert(0, r"D:\Projects\tastywork-trading-1\iv-switching-composite")

def parse_occ(occ: str):
    # e.g. 'QQQ   260515C00612000'
    underlying = occ[:6].strip()
    yymmdd = occ[6:12]
    opt_type = occ[12]
    strike = int(occ[13:]) / 1000.0
    return underlying, yymmdd, opt_type, strike

def test_parse():
    print(parse_occ('QQQ   260515C00612000'))
    print(parse_occ('QQQM  260515C00622121'))

if __name__ == "__main__":
    test_parse()

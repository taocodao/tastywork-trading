import pytest
from src.tqqq.position_sizer import TQQQPositionSizer

def test_medium_risk():
    """Test $25K principal + MEDIUM (7.5%) + $5 width + $0.85 credit"""
    result = TQQQPositionSizer.calculate(
        principal=25000,
        risk_level="MEDIUM",
        credit=0.85,
        spread_width=5.0
    )
    # Max risk = $1875
    # Max loss/contract = $415
    # Max contracts = floor(1875 / 415) = 4
    assert result["quantity"] == 4
    assert result["maxLossPerContract"] == 415.0

def test_low_risk_floor():
    """Test $5K principal + LOW (5%) + $5 width + $0.85 credit"""
    result = TQQQPositionSizer.calculate(
        principal=5000,
        risk_level="LOW",  # 5% = $250 max risk
        credit=0.85,
        spread_width=5.0
    )
    # $250 / $415 is less than 1, but we floor to 1 contract minimum
    assert result["quantity"] == 1

def test_high_risk_ceiling():
    """Test $50K principal + HIGH (10%) + $3 width + $0.65 credit"""
    result = TQQQPositionSizer.calculate(
        principal=50000,
        risk_level="HIGH",  # 10% = $5000 max risk
        credit=0.65,
        spread_width=3.0    # max loss = $235
    )
    # $5000 / $235 = 21 contracts, but we cap at 10
    assert result["quantity"] == 10

def test_position_limit_reached():
    """Test block when max positions reached"""
    result = TQQQPositionSizer.calculate(
        principal=25000,
        risk_level="MEDIUM", # max 5 positions
        credit=0.85,
        spread_width=5.0,
        active_positions=5
    )
    assert result["quantity"] == 0
    assert result["reason"] == "max_positions_reached"

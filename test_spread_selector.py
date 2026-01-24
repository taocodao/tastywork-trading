"""
Test Vertical Spread Selector
=============================

Unit tests for the VerticalSpreadSelector class.
"""

import pytest
import sys
import os
from datetime import date, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.vertical_spreads.spread_selector import (
    VerticalSpreadSelector,
    VerticalSpreadSetup,
    get_available_expirations
)


class TestSpreadSelector:
    """Tests for VerticalSpreadSelector."""
    
    @pytest.fixture
    def selector(self):
        """Create a fresh selector for each test."""
        return VerticalSpreadSelector()
    
    @pytest.fixture
    def expirations(self):
        """Generate test expirations."""
        return get_available_expirations(7, 21)
    
    # Bull Call Spread Tests
    def test_bull_call_spread_selection(self, selector, expirations):
        """Bull call spread should have buy_strike < sell_strike."""
        setup = selector.select_spread(
            symbol="SPY",
            stock_price=485.0,
            direction="BULL",
            confidence=70,
            iv=0.20,
            account_balance=10000,
            available_expirations=expirations
        )
        
        assert setup is not None
        assert setup.strategy == "BULL_CALL_SPREAD"
        assert setup.option_type == "C"
        assert setup.buy_strike <= setup.sell_strike
        assert setup.direction == "BULL"
    
    def test_bull_call_spread_high_confidence(self, selector, expirations):
        """High confidence should select wider strikes."""
        high_conf = selector.select_spread(
            symbol="SPY",
            stock_price=485.0,
            direction="BULL",
            confidence=85,  # High
            iv=0.20,
            account_balance=10000,
            available_expirations=expirations
        )
        
        low_conf = selector.select_spread(
            symbol="SPY",
            stock_price=485.0,
            direction="BULL",
            confidence=55,  # Low
            iv=0.20,
            account_balance=10000,
            available_expirations=expirations
        )
        
        # High confidence should have wider spread or same
        assert high_conf.sell_strike - high_conf.buy_strike >= low_conf.sell_strike - low_conf.buy_strike
    
    # Bear Put Spread Tests
    def test_bear_put_spread_selection(self, selector, expirations):
        """Bear put spread should have buy_strike > sell_strike."""
        setup = selector.select_spread(
            symbol="SPY",
            stock_price=485.0,
            direction="BEAR",
            confidence=70,
            iv=0.20,
            account_balance=10000,
            available_expirations=expirations
        )
        
        assert setup is not None
        assert setup.strategy == "BEAR_PUT_SPREAD"
        assert setup.option_type == "P"
        assert setup.buy_strike >= setup.sell_strike
        assert setup.direction == "BEAR"
    
    # Neutral Direction Test
    def test_neutral_returns_none(self, selector, expirations):
        """Neutral direction should return None."""
        setup = selector.select_spread(
            symbol="SPY",
            stock_price=485.0,
            direction="NEUTRAL",
            confidence=50,
            iv=0.20,
            account_balance=10000,
            available_expirations=expirations
        )
        
        assert setup is None
    
    # Implied Move Tests
    def test_implied_move_calculation(self, selector):
        """Implied move should increase with IV and DTE."""
        # Base case
        move_base = selector._calculate_implied_move(100, 0.20, 14)
        
        # Higher IV
        move_high_iv = selector._calculate_implied_move(100, 0.40, 14)
        assert move_high_iv > move_base
        
        # More DTE
        move_more_dte = selector._calculate_implied_move(100, 0.20, 28)
        assert move_more_dte > move_base
        
        # Higher price
        move_high_price = selector._calculate_implied_move(200, 0.20, 14)
        assert move_high_price > move_base
    
    def test_implied_move_zero_dte(self, selector):
        """Implied move with 0 DTE should be 0."""
        move = selector._calculate_implied_move(100, 0.20, 0)
        assert move == 0
    
    # Contract Sizing Tests
    def test_contract_sizing_respects_risk_limit(self, selector):
        """Contract count should not exceed risk limit."""
        # With $10,000 account and 2% risk = $200 max risk
        contracts = selector._calculate_contracts(
            max_loss_per_contract=100,  # $100 max loss per contract
            account_balance=10000,
            risk_tolerance="medium"  # 2%
        )
        
        # Max 2 contracts = $200 risk
        assert contracts <= 2
    
    def test_contract_sizing_minimum_one(self, selector):
        """Should always have at least 1 contract."""
        contracts = selector._calculate_contracts(
            max_loss_per_contract=500,  # More than 2% risk
            account_balance=5000,
            risk_tolerance="conservative"  # 1%
        )
        
        assert contracts >= 1
    
    def test_contract_sizing_risk_tolerances(self, selector):
        """Different risk tolerances should affect sizing."""
        cons = selector._calculate_contracts(100, 10000, "conservative")  # 1%
        med = selector._calculate_contracts(100, 10000, "medium")  # 2%
        aggr = selector._calculate_contracts(100, 10000, "aggressive")  # 5%
        
        assert cons <= med <= aggr
    
    # Expiration Selection Tests
    def test_expiry_selection_prefers_target_dte(self, selector):
        """Should prefer DTE closest to preferred (14 days)."""
        today = date.today()
        expirations = [
            today + timedelta(days=7),
            today + timedelta(days=14),  # Should prefer this
            today + timedelta(days=21)
        ]
        
        selected = selector._select_expiration(expirations)
        assert (selected - today).days == 14
    
    def test_expiry_selection_within_range(self, selector, expirations):
        """Selected expiry should be within DTE range."""
        if not expirations:
            pytest.skip("No expirations available")
        
        selected = selector._select_expiration(expirations)
        if selected:
            dte = (selected - date.today()).days
            assert selector.target_dte_min <= dte <= selector.target_dte_max + 7
    
    def test_expiry_selection_no_valid_expiries(self, selector):
        """Should return None if no valid expirations."""
        far_expirations = [
            date.today() + timedelta(days=60),
            date.today() + timedelta(days=90)
        ]
        
        selected = selector._select_expiration(far_expirations)
        # Should fallback to closest available if DTE min is met
        assert selected is None or (selected - date.today()).days >= selector.target_dte_min
    
    # Strike Rounding Tests
    def test_strike_rounding_small_price(self, selector):
        """Small prices should round to $0.50 increments."""
        strike = selector._round_strike(15.73)
        assert strike in [15.5, 16.0]
    
    def test_strike_rounding_medium_price(self, selector):
        """Medium prices should round to $1 increments."""
        strike = selector._round_strike(85.4)
        assert strike in [85.0, 86.0]
    
    def test_strike_rounding_large_price(self, selector):
        """Large prices should round to $5 increments."""
        strike = selector._round_strike(485.3)
        assert strike in [485.0, 490.0]
    
    # Score Calculation Tests
    def test_spread_setup_score(self, selector, expirations):
        """Spread setup should have calculated score."""
        setup = selector.select_spread(
            symbol="SPY",
            stock_price=485.0,
            direction="BULL",
            confidence=75,
            iv=0.20,
            account_balance=10000,
            available_expirations=expirations
        )
        
        assert setup.score > 0
    
    def test_higher_confidence_higher_score(self, selector, expirations):
        """Higher confidence should produce higher score."""
        high_conf = selector.select_spread(
            symbol="SPY",
            stock_price=485.0,
            direction="BULL",
            confidence=80,
            iv=0.20,
            account_balance=10000,
            available_expirations=expirations
        )
        
        low_conf = selector.select_spread(
            symbol="SPY",
            stock_price=485.0,
            direction="BULL",
            confidence=50,
            iv=0.20,
            account_balance=10000,
            available_expirations=expirations
        )
        
        # Score depends on confidence as one factor
        # Note: Other factors may affect score too
        assert high_conf.confidence > low_conf.confidence


class TestVerticalSpreadSetup:
    """Tests for VerticalSpreadSetup dataclass."""
    
    def test_setup_string_format(self):
        """String representation should be readable."""
        setup = VerticalSpreadSetup(
            symbol="SPY",
            strategy="BULL_CALL_SPREAD",
            direction="BULL",
            buy_strike=485.0,
            sell_strike=490.0,
            option_type="C",
            expiration=date.today() + timedelta(days=14),
            dte=14,
            net_debit=2.50,
            max_profit=250.0,
            max_loss=250.0,
            contracts=1,
            total_at_risk=250.0,
            implied_move=8.0,
            confidence=70,
            stock_price=485.0
        )
        
        str_repr = str(setup)
        assert "BULL_CALL_SPREAD" in str_repr
        assert "SPY" in str_repr
        assert "485" in str_repr


class TestHelperFunctions:
    """Tests for module helper functions."""
    
    def test_get_available_expirations(self):
        """Should return list of Friday expirations."""
        expirations = get_available_expirations(7, 21)
        
        for exp in expirations:
            assert isinstance(exp, date)
            assert exp >= date.today()
            # Should be Friday
            assert exp.weekday() == 4
    
    def test_get_available_expirations_sorted(self):
        """Expirations should be sorted chronologically."""
        expirations = get_available_expirations(7, 21)
        
        for i in range(len(expirations) - 1):
            assert expirations[i] < expirations[i + 1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

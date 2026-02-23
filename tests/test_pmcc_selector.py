import pytest
from datetime import datetime, date, timedelta
import pandas as pd
from unittest.mock import Mock, patch

from src.pmcc.pmcc_selector import PMCCSelector
from src.pmcc.pmcc_short_call_selector import PMCCShortCallSelector
from src.pmcc.pmcc_sr_finder import SupportResistanceFinder
from ib_data_provider import IBDataProvider

@pytest.fixture
def mock_ib_provider():
    mock_ib = Mock(spec=IBDataProvider)
    
    # Mock expirations
    def mock_get_next_expiry(symbol, days_out):
        return date.today() + timedelta(days=days_out)
    
    mock_ib.get_next_expiry.side_effect = mock_get_next_expiry
    
    # Lists of dicts (what get_call_chain_for_pmcc actually returns)
    leaps_chain = [
        {'strike': 140.0, 'delta': 0.85, 'ask': 30.0, 'bid': 29.5, 'expiration': date.today() + timedelta(days=365)},
        {'strike': 150.0, 'delta': 0.78, 'ask': 22.0, 'bid': 21.5, 'expiration': date.today() + timedelta(days=365)}, # Target LEAPS
        {'strike': 160.0, 'delta': 0.65, 'ask': 15.0, 'bid': 14.8, 'expiration': date.today() + timedelta(days=365)}
    ]
    
    short_chain = [
        {'strike': 180.0, 'delta': 0.35, 'ask': 3.5, 'bid': 3.4, 'expiration': date.today() + timedelta(days=30)},
        {'strike': 185.0, 'delta': 0.28, 'ask': 2.2, 'bid': 2.1, 'expiration': date.today() + timedelta(days=30)}, # Target Short
        {'strike': 190.0, 'delta': 0.18, 'ask': 1.1, 'bid': 1.0, 'expiration': date.today() + timedelta(days=30)}
    ]
    
    # Mock PMCC call chain based on is_leaps flag
    def mock_get_chain(symbol, expiry, delta_min, delta_max, is_leaps):
        if is_leaps:
            return leaps_chain
        else:
            return short_chain
            
    mock_ib.get_call_chain_for_pmcc.side_effect = mock_get_chain
    return mock_ib

@pytest.fixture
def sr_finder():
    return SupportResistanceFinder()

def test_pmcc_selector_valid_setup(mock_ib_provider):
    """Test standard LEAPS and short call selection where BCI math is met."""
    selector = PMCCSelector(mock_ib_provider)
    
    # Stock price 170
    setup = selector.select_pmcc_entry(
        symbol="TEST",
        stock_price=170.0,
        confidence=85,
        account_balance=10000.0,
        risk_tolerance="medium"
    )
    
    assert setup is not None
    assert setup.long_strike == 150.0  # Selected delta 0.75
    assert setup.short_strike == 185.0 # Selected delta 0.28 (<0.30 target)
    assert setup.bci_formula_met is True
    
    # Economics check
    # Debit = 22.0 (Long Ask) - 2.1 (Short Bid) = 19.9
    assert round(setup.net_debit, 2) == 19.9
    assert setup.break_even == 150.0 + 19.9 # 169.9
    
    # BCI checks: Break even (169.9) < Short Strike (185.0) -> True!

def test_pmcc_selector_bci_failure(mock_ib_provider):
    """Test fallback when BCI formula fails but score is high enough to override."""
    
    def mock_get_chain(symbol, expiry, delta_min, delta_max, is_leaps):
        if is_leaps:
            return [{'strike': 150.0, 'delta': 0.75, 'ask': 45.0, 'bid': 44.0, 'expiration': date.today() + timedelta(days=365)}]
        else:
            return [{'strike': 180.0, 'delta': 0.30, 'ask': 2.0, 'bid': 1.9, 'expiration': date.today() + timedelta(days=30)}]
            
    mock_ib_provider.get_call_chain_for_pmcc.side_effect = mock_get_chain
    
    selector = PMCCSelector(mock_ib_provider)
    
    # Stock price 170. Break even = 150 + (45-1.9) = 193.1. Short Strike = 180. BCI Fails!
    
    # With a moderate score, it should reject (fallback to default BCI override logic?)
    # actually right now BCI failure is universally a warning, but setup is returned anyway.
    # We should verify it returns but bci_formula_met is False
    setup = selector.select_pmcc_entry("TEST", 170.0, 75, 10000.0)
    assert setup is not None
    assert setup.bci_formula_met is False

def test_support_resistance_alignment(mock_ib_provider):
    """Test that Short Call Selector adjusts strike to align with resistance."""
    short_selector = PMCCShortCallSelector(mock_ib_provider)
    
    # This chain will be returned by get_call_chain_for_pmcc when called by ShortCallSelector
    short_chain = [
        {'strike': 180.0, 'delta': 0.40, 'ask': 4.0, 'bid': 3.9, 'expiration': date.today() + timedelta(days=30)},
        {'strike': 185.0, 'delta': 0.28, 'ask': 2.2, 'bid': 2.1, 'expiration': date.today() + timedelta(days=30)}, # Nearest delta
        {'strike': 190.0, 'delta': 0.20, 'ask': 1.2, 'bid': 1.1, 'expiration': date.today() + timedelta(days=30)}  # Resistance level
    ]
    mock_ib_provider.get_call_chain_for_pmcc.side_effect = lambda **kw: short_chain
    
    # Mock a dataframe where the highest volume node is at 190
    hist_df = pd.DataFrame({'close': [160, 165, 170], 'volume': [100, 200, 300]})
    
    with patch.object(SupportResistanceFinder, 'get_resistance_levels') as mock_resist:
        mock_resist.return_value = [175.0, 190.0]  # Strong resistance exactly at 190
        
        # We target delta 0.30 (nearest is 185). But there's resistance at 190.
        # So it should push the short strike up to 190
        selected = short_selector.select_short_call(
            symbol="TEST",
            stock_price=170.0,
            hist_df=hist_df,
            target_delta=0.30,
            leaps_break_even=165.0
        )
        
        assert selected is not None
        assert selected['strike'] == 190.0

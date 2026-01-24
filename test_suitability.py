"""
Test Vertical Spread Suitability Validator
==========================================

Unit tests for the VerticalSpreadSuitabilityValidator class.
"""

import pytest
import sys
import os
from datetime import date, datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.vertical_spreads.suitability import (
    VerticalSpreadSuitabilityValidator,
    SuitabilityResult,
    SuitabilityCheck
)


class TestSuitabilityValidator:
    """Tests for VerticalSpreadSuitabilityValidator."""
    
    @pytest.fixture
    def validator(self):
        """Create a fresh validator with default settings."""
        return VerticalSpreadSuitabilityValidator()
    
    @pytest.fixture
    def valid_profile(self):
        """Create a valid customer profile."""
        return {
            "account_balance": 10000,
            "options_level": 3,
            "risk_tolerance": "medium"
        }
    
    # Account Balance Tests
    def test_account_balance_minimum_passed(self, validator):
        """Account >= $2000 should pass."""
        profile = {"account_balance": 5000, "options_level": 2}
        result = validator.validate(profile)
        
        balance_check = [c for c in result.checks if c.name == "Account Balance"][0]
        assert balance_check.passed
    
    def test_account_balance_minimum_failed(self, validator):
        """Account < $2000 should fail."""
        profile = {"account_balance": 1500, "options_level": 2}
        result = validator.validate(profile)
        
        balance_check = [c for c in result.checks if c.name == "Account Balance"][0]
        assert not balance_check.passed
        assert not result.suitable
    
    def test_account_balance_exactly_minimum(self, validator):
        """Account exactly $2000 should pass."""
        profile = {"account_balance": 2000, "options_level": 2}
        result = validator.validate(profile)
        
        balance_check = [c for c in result.checks if c.name == "Account Balance"][0]
        assert balance_check.passed
    
    # Options Level Tests
    def test_options_level_passed(self, validator):
        """Options level >= 2 should pass."""
        profile = {"account_balance": 5000, "options_level": 2}
        result = validator.validate(profile)
        
        level_check = [c for c in result.checks if c.name == "Options Approval Level"][0]
        assert level_check.passed
    
    def test_options_level_failed(self, validator):
        """Options level < 2 should fail."""
        profile = {"account_balance": 5000, "options_level": 1}
        result = validator.validate(profile)
        
        level_check = [c for c in result.checks if c.name == "Options Approval Level"][0]
        assert not level_check.passed
        assert not result.suitable
    
    def test_options_level_higher_passed(self, validator):
        """Higher options levels should also pass."""
        profile = {"account_balance": 5000, "options_level": 4}
        result = validator.validate(profile)
        
        level_check = [c for c in result.checks if c.name == "Options Approval Level"][0]
        assert level_check.passed
    
    # Trade Size Tests
    def test_trade_size_within_limit(self, validator, valid_profile):
        """Trade size within 2% should pass."""
        trade = {
            "max_loss_per_contract": 100,
            "contracts": 1
        }
        result = validator.validate(valid_profile, trade)
        
        size_check = [c for c in result.checks if c.name == "Trade Size"][0]
        assert size_check.passed
    
    def test_trade_size_exceeds_limit(self, validator, valid_profile):
        """Trade size > 2% should fail."""
        trade = {
            "max_loss_per_contract": 500,
            "contracts": 2  # $1000 risk on $10000 account = 10%
        }
        result = validator.validate(valid_profile, trade)
        
        size_check = [c for c in result.checks if c.name == "Trade Size"][0]
        assert not size_check.passed
    
    def test_trade_size_exactly_at_limit(self, validator, valid_profile):
        """Trade size exactly at 2% should pass."""
        trade = {
            "max_loss_per_contract": 200,  # 2% of $10000
            "contracts": 1
        }
        result = validator.validate(valid_profile, trade)
        
        size_check = [c for c in result.checks if c.name == "Trade Size"][0]
        assert size_check.passed
    
    # Overall Suitability Tests
    def test_fully_suitable(self, validator, valid_profile):
        """Valid profile should be suitable."""
        result = validator.validate(valid_profile)
        
        assert result.suitable
        assert len(result.blocking_issues) == 0
    
    def test_multiple_failures(self, validator):
        """Multiple failures should all be reported."""
        profile = {
            "account_balance": 1000,  # Fail
            "options_level": 1  # Fail
        }
        result = validator.validate(profile)
        
        assert not result.suitable
        assert len(result.blocking_issues) >= 2
    
    # Custom Threshold Tests
    def test_custom_min_balance(self):
        """Should respect custom minimum balance."""
        validator = VerticalSpreadSuitabilityValidator(min_account_balance=5000)
        
        profile = {"account_balance": 3000, "options_level": 2}
        result = validator.validate(profile)
        
        assert not result.suitable
    
    def test_custom_min_options_level(self):
        """Should respect custom options level."""
        validator = VerticalSpreadSuitabilityValidator(min_options_level=3)
        
        profile = {"account_balance": 5000, "options_level": 2}
        result = validator.validate(profile)
        
        assert not result.suitable
    
    def test_custom_risk_percent(self):
        """Should respect custom risk percentage."""
        validator = VerticalSpreadSuitabilityValidator(max_risk_per_trade_pct=0.01)  # 1%
        
        profile = {"account_balance": 10000, "options_level": 2}
        trade = {"max_loss_per_contract": 150, "contracts": 1}  # 1.5%
        
        result = validator.validate(profile, trade)
        
        size_check = [c for c in result.checks if c.name == "Trade Size"][0]
        assert not size_check.passed
    
    # Summary Output Tests
    def test_summary_output_suitable(self, validator, valid_profile):
        """Summary for suitable account should show approval."""
        result = validator.validate(valid_profile)
        summary = validator.get_suitability_summary(result)
        
        assert "approved" in summary.lower() or "✅" in summary
    
    def test_summary_output_not_suitable(self, validator):
        """Summary for unsuitable account should show rejection."""
        profile = {"account_balance": 500, "options_level": 1}
        result = validator.validate(profile)
        summary = validator.get_suitability_summary(result)
        
        assert "not approved" in summary.lower() or "❌" in summary
    
    # PDT Rule Tests
    def test_pdt_under_25k_with_trades(self, validator):
        """Account < $25K with 4+ day trades should be PDT."""
        profile = {
            "account_balance": 15000,
            "day_trades_last_5_days": 4
        }
        
        assert validator.is_pattern_day_trader(profile)
    
    def test_pdt_over_25k(self, validator):
        """Account >= $25K should not be PDT restricted."""
        profile = {
            "account_balance": 30000,
            "day_trades_last_5_days": 10
        }
        
        assert not validator.is_pattern_day_trader(profile)
    
    def test_pdt_under_25k_few_trades(self, validator):
        """Account < $25K with < 4 day trades should not be PDT."""
        profile = {
            "account_balance": 15000,
            "day_trades_last_5_days": 2
        }
        
        assert not validator.is_pattern_day_trader(profile)
    
    # Result to Dict Tests
    def test_result_to_dict(self, validator, valid_profile):
        """Result should convert to dictionary for JSON."""
        result = validator.validate(valid_profile)
        result_dict = result.to_dict()
        
        assert "suitable" in result_dict
        assert "checks" in result_dict
        assert "blockingIssues" in result_dict
        assert isinstance(result_dict["checks"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

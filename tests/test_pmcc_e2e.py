"""
PMCC End-to-End Signal Pipeline Tests
======================================
Comprehensive tests covering the full PMCC signal lifecycle:

  Signal Creation → expires_at → DB Persistence → Auto-Approve Decision
  → Auto-Approve Execution → WebSocket Broadcast → Full Pipeline

Run:  python -m pytest tests/test_pmcc_e2e.py -v --tb=short
"""

import sys
import os
import uuid
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ═══════════════════════════════════════════════════════════════════════
# 1. SIGNAL CREATION — Verify dataclass serialization
# ═══════════════════════════════════════════════════════════════════════

class TestPMCCSignalCreation:
    """Verify all PMCC signal dataclasses serialize correctly."""

    def test_pmcc_entry_to_dict(self, pmcc_entry_signal):
        signal = pmcc_entry_signal()
        data = signal.to_dict()
        assert data['symbol'] == 'AAPL'
        assert data['long_strike'] == 140.0
        assert data['short_strike'] == 185.0
        assert data['bci_formula_met'] is True
        assert data['action'] == 'ENTRY'
        assert data['strategy'] == 'PMCC'
        assert 'created_at' in data
        assert isinstance(data['created_at'], str)

    def test_pmcc_cycle_to_dict(self, pmcc_cycle_signal):
        signal = pmcc_cycle_signal()
        data = signal.to_dict()
        assert data['symbol'] == 'AAPL'
        assert data['action'] == 'CYCLE'
        assert data['cycle_number'] == 2
        assert data['short_strike'] == 190.0
        assert 'position_id' in data


# ═══════════════════════════════════════════════════════════════════════
# 2. PMCC PUBLISHER — Verify expires_at calculation and broadcasting
# ═══════════════════════════════════════════════════════════════════════

class TestPMCCPublisher:
    """Verifies PMCC publishers append expires_at and broadcast properly."""

    @patch('signal_publisher.pmcc.broadcast_to_channel', return_value=True)
    def test_pmcc_entry_adds_expires_at(self, mock_broadcast, pmcc_entry_signal):
        from signal_publisher.pmcc import publish_pmcc_entry_signal
        signal = pmcc_entry_signal()
        
        with patch('src.earnings_intelligence.database.SignalRepository') as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            with patch('auto_approve.auto_approve_signal', return_value=None):
                publish_pmcc_entry_signal(signal)
        
        call_args = mock_broadcast.call_args_list
        assert len(call_args) >= 1
        data = call_args[0][0][1]
        assert 'expires_at' in data
        assert isinstance(data['expires_at'], datetime)
        # Assuming typical 4 PM ET expiration logic
        # PMCC uses standard EOD expiration on signal day (same as Zebra/Theta)
        assert data['expires_at'].hour in range(19, 22)

    @patch('signal_publisher.pmcc.broadcast_to_channel', return_value=True)
    def test_pmcc_cycle_adds_expires_at(self, mock_broadcast, pmcc_cycle_signal):
        from signal_publisher.pmcc import publish_pmcc_cycle_signal
        signal = pmcc_cycle_signal()
        
        with patch('src.earnings_intelligence.database.SignalRepository') as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            with patch('auto_approve.auto_approve_signal', return_value=None):
                publish_pmcc_cycle_signal(signal)
        
        call_args = mock_broadcast.call_args_list
        assert len(call_args) >= 1
        data = call_args[0][0][1]
        assert 'expires_at' in data


# ═══════════════════════════════════════════════════════════════════════
# 3. DATABASE PERSISTENCE — SQLite logic mapping
# ═══════════════════════════════════════════════════════════════════════

class TestPMCCDatabasePersistence:
    """Test saving PMCC signals directly to the repository."""

    def test_save_new_pmcc_signal(self, signal_repo, pmcc_entry_signal):
        signal = pmcc_entry_signal()
        data = signal.to_dict()
        
        result = signal_repo.save_signal(data)
        assert result.id == data['id']
        assert result.symbol == 'AAPL'
        assert result.strategy == 'PMCC'
        assert result.status == 'NEW'


# ═══════════════════════════════════════════════════════════════════════
# 4. AUTO-APPROVE DECISION — Test PMCC Auto-approve logic
# ═══════════════════════════════════════════════════════════════════════

class TestPMCCAutoApproveDecision:
    """Test that PMCC auto-approve rules correctly flag valid setups."""

    def test_pmcc_auto_approve_granted(self):
        from auto_approve import should_auto_approve
        # Requires mocking the default PMCC settings to be enabled
        with patch('auto_approve.get_auto_approve_settings') as mock_settings:
            mock_settings.return_value = {
                "enabled": True,
                "diagonal": {
                    "enabled": True,
                    "risk_level": "LOW",
                    "risk_profiles": {
                        "LOW": {
                            "min_confidence": 80,
                            "max_capital_per_trade": 5000,
                            "max_contracts": 2,
                            "max_positions": 4,
                        }
                    },
                    "custom_overrides": {}
                }
            }
            
            signal = {
                'symbol': 'AAPL',
                'strategy': 'pmcc',
                'confidence': 85.0,
                'capitalRequired': 2790.0,
                'cost': 2790.0,
                'contracts': 1
            }
            
            # Since auto-approve expects oauth token to execute but not necessarily to check should_auto_approve
            approved = should_auto_approve(signal, user_refresh_token="mock_token")
            assert approved is True

    def test_pmcc_auto_approve_denied_capital_limit(self):
        from auto_approve import should_auto_approve
        with patch('auto_approve.get_auto_approve_settings') as mock_settings:
            mock_settings.return_value = {
                "enabled": True,
                "diagonal": {
                    "enabled": True,
                    "risk_level": "LOW",
                    "risk_profiles": {
                        "LOW": {
                            "min_confidence": 80,
                            "max_capital_per_trade": 2000,
                            "max_contracts": 2,
                            "max_positions": 4,
                        }
                    },
                    "custom_overrides": {}
                }
            }
            
            signal = {
                'symbol': 'AAPL',
                'strategy': 'pmcc',
                'confidence': 85.0,
                'capitalRequired': 2790.0,
                'cost': 2790.0,
                'contracts': 1
            }
            
            approved = should_auto_approve(signal, user_refresh_token="mock_token")
            assert approved is False


# ═══════════════════════════════════════════════════════════════════════
# 5. FULL PIPELINE SIMULATION
# ═══════════════════════════════════════════════════════════════════════

class TestPMCCFullPipeline:
    """Test the full flow: signal -> publisher -> DB -> WebSockets -> Execution"""

    @patch('tastytrade_utils.get_user_account')
    @patch('tastytrade_utils.create_user_session')
    @patch('auto_approve._execute_pmcc_auto_approve')
    @patch('signal_publisher.pmcc.broadcast_to_channel')
    def test_full_entry_pipeline(
        self,
        mock_broadcast,
        mock_execute,
        mock_session,
        mock_account,
        pmcc_entry_signal,
        signal_repo
    ):
        """Simulate a PMCC scanner hit making its way fully through the system."""
        from signal_publisher.pmcc import publish_pmcc_entry_signal
        
        # 1. Signal is generated (emulating scanner)
        signal = pmcc_entry_signal()
        
        # Ensure it meets auto-approve requirements
        signal.confidence = 90
        signal.total_risk = 1500.0
        
        mock_execute.return_value = {"orderId": "123", "status": "filled"}
        mock_broadcast.return_value = True
        mock_session.return_value = MagicMock()
        mock_acc = MagicMock()
        mock_acc.account_number = "5WX1234"
        mock_account.return_value = mock_acc
        
        # Override auto-approve settings to force it through
        with patch('auto_approve.get_auto_approve_settings') as mock_settings:
            mock_settings.return_value = {
                "enabled": True,
                "diagonal": {
                    "enabled": True,
                    "risk_level": "LOW",
                    "risk_profiles": {
                        "LOW": {
                            "min_confidence": 75,
                            "max_capital_per_trade": 5000,
                            "max_contracts": 5,
                        }
                    },
                    "custom_overrides": {}
                }
            }
            
            with patch('src.earnings_intelligence.database.SignalRepository') as mock_repo_cls:
                mock_repo_cls.return_value = signal_repo
                
                # 2. Publish it
                publish_success = publish_pmcc_entry_signal(signal, user_refresh_token="abc")
                
                # Verify pipeline outcomes:
                # A. Publisher returned true
                assert publish_success is True
                
                # B. Auto-approve executed it
                mock_execute.assert_called_once()
                
                # C. Broadcasted via WebSocket (twice if auto approved)
                assert mock_broadcast.call_count == 2

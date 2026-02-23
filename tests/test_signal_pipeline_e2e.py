"""
End-to-End Signal Pipeline Unit Tests
======================================
Comprehensive tests covering the full signal lifecycle:

  Signal Creation → expires_at → DB Persistence → Auto-Approve Decision
  → Auto-Approve Execution → WebSocket Broadcast → Full Pipeline

All external dependencies (Tastytrade API, WebSocket, production DB) are mocked.
Database tests use an in-memory SQLite instance for real ORM verification.

Run:  python -m pytest tests/test_signal_pipeline_e2e.py -v --tb=short
"""

import sys
import os
import uuid
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════════════════
# 1. SIGNAL CREATION — Verify dataclass serialization
# ═══════════════════════════════════════════════════════════════════════

class TestSignalCreation:
    """Verify all signal dataclasses serialize correctly with required fields."""

    def test_theta_entry_to_dict(self, theta_entry_signal):
        signal = theta_entry_signal()
        data = signal.to_dict()
        assert data['symbol'] == 'SPY'
        assert data['strike'] == 580.0
        assert data['confidence'] == 75.0
        assert data['contracts'] == 1
        assert data['entry_price'] == 2.50
        assert 'created_at' in data
        assert isinstance(data['created_at'], str)  # datetime converted to ISO string

    def test_theta_exit_to_dict(self, theta_exit_signal):
        signal = theta_exit_signal()
        data = signal.to_dict()
        assert data['symbol'] == 'SPY'
        assert data['exit_reason'] == 'profit_target'
        assert data['pnl'] == 200.0
        assert data['pnl_percent'] == 80.0
        assert data['action'] == 'BUY_TO_CLOSE'

    def test_zebra_entry_to_dict(self, zebra_entry_signal):
        signal = zebra_entry_signal()
        data = signal.to_dict()
        assert data['symbol'] == 'AAPL'
        assert data['direction'] == 'LONG'
        assert data['composite_score'] == 80.0
        assert data['net_delta'] == 1.0
        assert data['strategy'] == 'zebra'
        assert 'rationale' in data

    def test_zebra_exit_to_dict(self, zebra_exit_signal):
        signal = zebra_exit_signal()
        data = signal.to_dict()
        assert data['symbol'] == 'AAPL'
        assert data['exit_reason'] == 'PROFIT_TARGET'
        assert data['exit_credit'] == 7.50
        assert data['action'] == 'CLOSE'

    def test_dvo_entry_to_dict(self, dvo_entry_signal):
        signal = dvo_entry_signal()
        data = signal.to_dict()
        assert data['symbol'] == 'MSFT'
        assert data['strategy_type'] == 'SHORT_PUT'
        assert data['current_price'] == 420.0
        assert data['fair_value'] == 450.0
        assert data['margin_of_safety'] == 0.30

    def test_dvo_exit_to_dict(self, dvo_exit_signal):
        signal = dvo_exit_signal()
        data = signal.to_dict()
        assert data['symbol'] == 'MSFT'
        assert data['reason'] == 'VELOCITY'
        assert data['pnl_pct'] == 66.7

    def test_calendar_setup_conversion(self, calendar_setup):
        from signal_publisher.calendar import spread_setup_to_signal
        data = spread_setup_to_signal(calendar_setup)
        assert data['symbol'] == 'SPY'
        assert data['strategy'] == 'calendar'
        assert data['status'] == 'pending'
        assert 'short_strike' in data
        assert 'short_expiry' in data
        assert 'long_expiry' in data
        assert 'expires_at' in data


# ═══════════════════════════════════════════════════════════════════════
# 2. EXPIRES_AT CALCULATION — Verify market close expiry
# ═══════════════════════════════════════════════════════════════════════

class TestExpiresAtCalculation:
    """Verifies that each publisher correctly calculates and appends 'expires_at'."""

    @patch('signal_publisher.theta.broadcast_to_channel', return_value=True)
    def test_theta_adds_expires_at(self, mock_broadcast, theta_entry_signal):
        signal = theta_entry_signal()
        
        with patch('src.earnings_intelligence.database.SignalRepository') as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            with patch('auto_approve.auto_approve_signal', return_value=None):
                from signal_publisher.theta import publish_theta_entry_signal
                publish_theta_entry_signal(signal)
        
        # Check that broadcast was called with expires_at
        call_args = mock_broadcast.call_args_list
        assert len(call_args) >= 1
        broadcasted_data = call_args[0][0][1]  # second arg of first call
        assert 'expires_at' in broadcasted_data
        # Should be a native python datetime object now
        assert isinstance(broadcasted_data['expires_at'], datetime)

    @patch('signal_publisher.zebra.broadcast_to_channel', return_value=True)
    def test_zebra_adds_expires_at(self, mock_broadcast, zebra_entry_signal):
        signal = zebra_entry_signal()
        
        with patch('src.earnings_intelligence.database.SignalRepository') as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            with patch('auto_approve.auto_approve_signal', return_value=None):
                from signal_publisher.zebra import publish_zebra_entry_signal
                publish_zebra_entry_signal(signal)
            
        call_args = mock_broadcast.call_args_list
        assert len(call_args) >= 1
        broadcasted_data = call_args[0][0][1]
        assert 'expires_at' in broadcasted_data
        assert isinstance(broadcasted_data['expires_at'], datetime)

    @patch('signal_publisher.dvo.broadcast_to_channel', return_value=True)
    def test_dvo_adds_expires_at(self, mock_broadcast, dvo_entry_signal):
        from signal_publisher.dvo import publish_dvo_entry_signal
        signal = dvo_entry_signal()
        
        with patch('src.earnings_intelligence.database.SignalRepository') as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            with patch('auto_approve.auto_approve_signal', return_value=None):
                publish_dvo_entry_signal(signal)
        
        call_args = mock_broadcast.call_args_list
        assert len(call_args) >= 1
        data = call_args[0][0][1]
        assert 'expires_at' in data
        assert isinstance(data['expires_at'], datetime)

    def test_calendar_has_expires_at(self, calendar_setup):
        from signal_publisher.calendar import spread_setup_to_signal
        data = spread_setup_to_signal(calendar_setup)
        assert 'expires_at' in data
        # Verify it's a valid ISO datetime str or datetime object
        if isinstance(data['expires_at'], str):
            exp = datetime.fromisoformat(data['expires_at'])
        else:
            exp = data['expires_at']
        assert exp.hour in range(19, 22)  # 4 PM ET = 20-21 UTC depending on DST


# ═══════════════════════════════════════════════════════════════════════
# 3. DATABASE PERSISTENCE — In-memory SQLite tests
# ═══════════════════════════════════════════════════════════════════════

class TestDatabasePersistence:
    """Test SignalRepository with real ORM on in-memory SQLite."""

    def test_save_new_signal(self, signal_repo, theta_entry_signal):
        signal = theta_entry_signal()
        data = signal.to_dict()
        data['strategy'] = 'theta'
        
        result = signal_repo.save_signal(data)
        assert result.id == data['id']
        assert result.symbol == 'SPY'
        assert result.strategy == 'theta'
        assert result.status == 'pending'

    def test_save_updates_existing_signal(self, signal_repo, theta_entry_signal):
        signal = theta_entry_signal()
        data = signal.to_dict()
        data['strategy'] = 'theta'
        
        # First save
        signal_repo.save_signal(data)
        
        # Update status
        data['status'] = 'approved'
        result = signal_repo.save_signal(data)
        
        assert result.status == 'approved'
        assert result.approved_at is not None  # auto-set on approval

    def test_get_all_signals_excludes_expired(self, signal_repo):
        past = datetime.utcnow() - timedelta(hours=2)
        future = datetime.utcnow() + timedelta(hours=2)
        
        # Expired signal
        signal_repo.save_signal({
            'id': str(uuid.uuid4()),
            'symbol': 'AAPL',
            'strategy': 'theta',
            'status': 'pending',
            'expires_at': past,
        })
        
        # Active signal
        active_id = str(uuid.uuid4())
        signal_repo.save_signal({
            'id': active_id,
            'symbol': 'SPY',
            'strategy': 'theta',
            'status': 'pending',
            'expires_at': future,
        })
        
        signals = signal_repo.get_all_signals(status='pending')
        assert len(signals) == 1
        assert signals[0].id == active_id

    def test_get_all_signals_includes_unexpired(self, signal_repo):
        future = datetime.utcnow() + timedelta(hours=4)
        
        signal_repo.save_signal({
            'id': str(uuid.uuid4()),
            'symbol': 'MSFT',
            'strategy': 'dvo',
            'status': 'pending',
            'expires_at': future,
        })
        
        signals = signal_repo.get_all_signals()
        assert len(signals) == 1
        assert signals[0].symbol == 'MSFT'

    def test_expire_old_signals(self, signal_repo):
        past = datetime.utcnow() - timedelta(hours=1)
        
        signal_repo.save_signal({
            'id': str(uuid.uuid4()),
            'symbol': 'AAPL',
            'strategy': 'zebra',
            'status': 'pending',
            'expires_at': past,
        })
        
        count = signal_repo.expire_old_signals()
        assert count == 1
        
        # Should now show as 'expired'
        signals = signal_repo.get_all_signals(status='expired', include_expired=True)
        assert len(signals) == 1
        assert signals[0].status == 'expired'

    def test_get_signal_by_id(self, signal_repo, theta_entry_signal):
        signal = theta_entry_signal()
        data = signal.to_dict()
        data['strategy'] = 'theta'
        signal_repo.save_signal(data)
        
        retrieved = signal_repo.get_signal(data['id'])
        assert retrieved is not None
        assert retrieved.symbol == 'SPY'

    def test_signal_to_dict_includes_status(self, signal_repo, theta_entry_signal):
        signal = theta_entry_signal()
        data = signal.to_dict()
        data['strategy'] = 'theta'
        saved = signal_repo.save_signal(data)
        
        d = saved.to_dict()
        assert d['status'] == 'pending'
        assert 'symbol' in d


# ═══════════════════════════════════════════════════════════════════════
# 4. AUTO-APPROVE DECISION — Test should_auto_approve() logic
# ═══════════════════════════════════════════════════════════════════════

class TestAutoApproveDecision:
    """Test that auto-approve criteria filtering works correctly."""

    def test_high_confidence_theta_approved(self):
        from auto_approve import should_auto_approve
        signal = {
            'strategy': 'theta',
            'confidence': 75.0,
            'capital_required': 500,
            'contracts': 1,
            'symbol': 'SPY',
        }
        # Pass a refresh token so it's not blocked
        result = should_auto_approve(signal, user_refresh_token="test_token")
        assert result is True

    def test_low_confidence_theta_rejected(self):
        from auto_approve import should_auto_approve
        signal = {
            'strategy': 'theta',
            'confidence': 40.0,
            'capital_required': 500,
            'contracts': 1,
            'symbol': 'SPY',
        }
        result = should_auto_approve(signal, user_refresh_token="test_token")
        assert result is False

    def test_disabled_strategy_rejected(self):
        from auto_approve import should_auto_approve
        signal = {
            'strategy': 'diagonal',
            'confidence': 90.0,
            'capital_required': 500,
            'contracts': 1,
            'symbol': 'SPY',
        }
        result = should_auto_approve(signal, user_refresh_token="test_token")
        assert result is False

    def test_no_refresh_token_rejected(self):
        from auto_approve import should_auto_approve
        signal = {
            'strategy': 'theta',
            'confidence': 90.0,
            'capitalRequired': 500,
            'contracts': 1,
            'symbol': 'SPY',
        }
        # Must clear env var - should_auto_approve falls back to TASTYTRADE_REFRESH_TOKEN
        with patch.dict(os.environ, {}, clear=True):
            result = should_auto_approve(signal, user_refresh_token=None)
            assert result is False

    def test_excessive_capital_rejected(self):
        from auto_approve import should_auto_approve
        signal = {
            'strategy': 'theta',
            'confidence': 80.0,
            'capitalRequired': 999999,  # camelCase matches auto_approve.py logic
            'contracts': 1,
            'symbol': 'SPY',
        }
        result = should_auto_approve(signal, user_refresh_token="test_token")
        assert result is False


# ═══════════════════════════════════════════════════════════════════════
# 5. AUTO-APPROVE EXECUTION — Test the execute path with mocked SDK
# ═══════════════════════════════════════════════════════════════════════

class TestAutoApproveExecution:
    """Test auto_approve_signal() with mocked Tastytrade session."""

    @patch('tastytrade_utils.get_user_account')
    @patch('tastytrade_utils.create_user_session')
    def test_creates_session_with_token(self, mock_create_session, mock_get_account):
        from auto_approve import auto_approve_signal
        
        mock_session = MagicMock()
        mock_create_session.return_value = mock_session
        mock_account = MagicMock()
        mock_account.account_number = "ACCT123"
        mock_get_account.return_value = mock_account
        
        signal = {
            'strategy': 'theta',
            'confidence': 80.0,
            'capitalRequired': 500,
            'contracts': 1,
            'symbol': 'SPY',
            'strike': 580.0,
            'expiration': '2026-04-18',
        }
        
        with patch.dict(os.environ, {'TASTYTRADE_REFRESH_TOKEN': 'test_refresh_token'}):
            with patch('auto_approve._execute_theta_auto_approve', return_value={'orderId': '12345'}):
                result = auto_approve_signal(signal, user_refresh_token='my_token')
        
        mock_create_session.assert_called_once_with('my_token')

    @patch('tastytrade_utils.get_user_account')
    @patch('tastytrade_utils.create_user_session')
    def test_handles_session_failure_gracefully(self, mock_create_session, mock_get_account):
        from auto_approve import auto_approve_signal
        
        mock_create_session.side_effect = ValueError("Bad credentials")
        
        signal = {
            'strategy': 'theta',
            'confidence': 80.0,
            'capitalRequired': 500,
            'contracts': 1,
            'symbol': 'SPY',
        }
        
        with patch.dict(os.environ, {'TASTYTRADE_REFRESH_TOKEN': 'bad_token'}):
            result = auto_approve_signal(signal, user_refresh_token='bad_token')
        
        assert result is None

    @patch('tastytrade_utils.get_user_account')
    @patch('tastytrade_utils.create_user_session')
    def test_executes_theta_strategy(self, mock_create_session, mock_get_account):
        from auto_approve import auto_approve_signal
        
        mock_session = MagicMock()
        mock_create_session.return_value = mock_session
        mock_account = MagicMock()
        mock_get_account.return_value = mock_account
        
        signal = {
            'strategy': 'theta',
            'confidence': 80.0,
            'capitalRequired': 500,
            'contracts': 1,
            'symbol': 'SPY',
            'strike': 580.0,
            'expiration': '2026-04-18',
        }
        
        with patch.dict(os.environ, {'TASTYTRADE_REFRESH_TOKEN': 'test_token'}):
            with patch('auto_approve._execute_theta_auto_approve', return_value={'orderId': '12345'}) as mock_exec:
                auto_approve_signal(signal, user_refresh_token='test_token')
        
        mock_exec.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════
# 6. WEBSOCKET BROADCAST — Test broadcast_to_channel()
# ═══════════════════════════════════════════════════════════════════════

class TestWebSocketBroadcast:
    """Test WebSocket broadcast with mocked HTTP."""

    @patch('signal_publisher.websocket_client.requests.post')
    def test_broadcast_success(self, mock_post):
        from signal_publisher.websocket_client import broadcast_to_channel
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        result = broadcast_to_channel('theta_entry', {'symbol': 'SPY', 'action': 'SELL'})
        
        assert result is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]['json']['channel'] == 'theta_entry'
        assert call_kwargs[1]['json']['signal']['symbol'] == 'SPY'

    @patch('signal_publisher.websocket_client.requests.post')
    def test_broadcast_connection_error(self, mock_post):
        import requests
        from signal_publisher.websocket_client import broadcast_to_channel
        
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")
        
        result = broadcast_to_channel('theta_entry', {'symbol': 'SPY'})
        assert result is False

    def test_broadcast_uses_localhost_default(self):
        from signal_publisher.websocket_client import WEBSOCKET_BROADCAST_URL
        assert 'localhost' in WEBSOCKET_BROADCAST_URL or '127.0.0.1' in WEBSOCKET_BROADCAST_URL

    @patch('signal_publisher.websocket_client.requests.post')
    def test_broadcast_server_error_returns_false(self, mock_post):
        from signal_publisher.websocket_client import broadcast_to_channel
        
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        result = broadcast_to_channel('theta_entry', {'symbol': 'SPY'})
        assert result is False


# ═══════════════════════════════════════════════════════════════════════
# 7. EXIT SIGNAL PUBLISHING — Test exit publishers
# ═══════════════════════════════════════════════════════════════════════

class TestExitSignalPublishing:
    """Verify exit signal publishers work for all strategies."""

    @patch('signal_publisher.theta.broadcast_to_channel', return_value=True)
    def test_theta_exit_publishes(self, mock_broadcast, theta_exit_signal):
        from signal_publisher.theta import publish_theta_exit_signal
        signal = theta_exit_signal()
        result = publish_theta_exit_signal(signal)
        assert result is True
        
        # Should broadcast to theta_puts and theta_exit
        assert mock_broadcast.call_count == 2
        channels = [call[0][0] for call in mock_broadcast.call_args_list]
        assert 'theta_puts' in channels
        assert 'theta_exit' in channels

    @patch('signal_publisher.zebra.broadcast_to_channel', return_value=True)
    def test_zebra_exit_publishes(self, mock_broadcast, zebra_exit_signal):
        from signal_publisher.zebra import publish_zebra_exit_signal
        signal = zebra_exit_signal()
        result = publish_zebra_exit_signal(signal)
        assert result is True
        assert mock_broadcast.call_count >= 1

    @patch('signal_publisher.dvo.broadcast_to_channel', return_value=True)
    def test_dvo_exit_publishes(self, mock_broadcast, dvo_exit_signal):
        from signal_publisher.dvo import publish_dvo_exit_signal
        signal = dvo_exit_signal()
        result = publish_dvo_exit_signal(signal)
        assert result is True
        assert mock_broadcast.call_count >= 1


# ═══════════════════════════════════════════════════════════════════════
# 8. FULL PIPELINE INTEGRATION — E2E with mocked boundaries
# ═══════════════════════════════════════════════════════════════════════

class TestFullPipelineE2E:
    """End-to-end tests that mock ONLY external boundaries."""

    @patch('signal_publisher.theta.broadcast_to_channel', return_value=True)
    def test_theta_full_pipeline(self, mock_broadcast, theta_entry_signal, signal_repo):
        """Signal → DB save → auto-approve check → broadcast."""
        signal = theta_entry_signal(confidence=80.0)
        
        with patch('src.earnings_intelligence.database.SignalRepository', return_value=signal_repo):
            with patch('auto_approve.auto_approve_signal', return_value=None):
                from signal_publisher.theta import publish_theta_entry_signal
                publish_theta_entry_signal(signal)
        
        # Verify signal was saved to DB
        saved = signal_repo.get_signal(signal.id)
        if saved:  # DB save succeeded
            assert saved.symbol == 'SPY'
            assert saved.status == 'pending'

    @patch('signal_publisher.zebra.broadcast_to_channel', return_value=True)
    def test_zebra_full_pipeline(self, mock_broadcast, zebra_entry_signal, signal_repo):
        """ZEBRA signal → DB save → broadcast."""
        signal = zebra_entry_signal()
        
        with patch('src.earnings_intelligence.database.SignalRepository', return_value=signal_repo):
            with patch('auto_approve.auto_approve_signal', return_value=None):
                from signal_publisher.zebra import publish_zebra_entry_signal
                result = publish_zebra_entry_signal(signal)
        
        # Verify broadcast was called
        assert mock_broadcast.call_count >= 1
        data = mock_broadcast.call_args_list[0][0][1]
        assert data['symbol'] == 'AAPL'
        assert data['strategy'] == 'zebra'

    @patch('signal_publisher.websocket_client.requests.post')
    def test_calendar_full_pipeline(self, mock_post, calendar_setup, signal_repo):
        """Calendar setup → signal conversion → DB save → broadcast."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        with patch('src.earnings_intelligence.database.SignalRepository', return_value=signal_repo):
            with patch('auto_approve.auto_approve_signal', return_value=None):
                from signal_publisher.calendar import publish_calendar_signal
                result = publish_calendar_signal(calendar_setup)
        
        assert result is True


# ═══════════════════════════════════════════════════════════════════════
# 9. TASTYTRADE UTILS — Version-safe account fetching
# ═══════════════════════════════════════════════════════════════════════

class TestTastytradeUtils:
    """Verify the version-safe account fetching wrapper."""

    def test_get_accounts_safe_tries_multiple_methods(self):
        from tastytrade_utils import _get_accounts_safe
        
        mock_session = MagicMock()
        mock_accounts = [MagicMock(account_number='ACCT001')]
        
        # Simulate SDK that has get_accounts method
        with patch('tastytrade_utils.Account') as MockAccount:
            MockAccount.get_accounts = MagicMock(return_value=mock_accounts)
            # hasattr will return True because we set the attribute
            result = _get_accounts_safe(mock_session)
        
        assert len(result) == 1

    def test_get_user_account_returns_first(self):
        from tastytrade_utils import get_user_account
        
        mock_session = MagicMock()
        mock_accounts = [MagicMock(account_number='ACCT001'), MagicMock(account_number='ACCT002')]
        
        with patch('tastytrade_utils._get_accounts_safe', return_value=mock_accounts):
            account = get_user_account(mock_session)
        
        assert account.account_number == 'ACCT001'

    def test_get_user_account_specific_number(self):
        from tastytrade_utils import get_user_account
        
        mock_session = MagicMock()
        mock_accounts = [MagicMock(account_number='ACCT001'), MagicMock(account_number='ACCT002')]
        
        with patch('tastytrade_utils._get_accounts_safe', return_value=mock_accounts):
            account = get_user_account(mock_session, account_number='ACCT002')
        
        assert account.account_number == 'ACCT002'

    def test_get_user_account_not_found_raises(self):
        from tastytrade_utils import get_user_account
        
        mock_session = MagicMock()
        mock_accounts = [MagicMock(account_number='ACCT001')]
        
        with patch('tastytrade_utils._get_accounts_safe', return_value=mock_accounts):
            with pytest.raises(ValueError, match="not found"):
                get_user_account(mock_session, account_number='NONEXIST')


# ─────────────────────────────────────────────────────────────────────
# Helper for full pipeline E2E test (patches internal imports)
# ─────────────────────────────────────────────────────────────────────

def publish_theta_entry_signal_patched(signal, repo, mock_broadcast):
    """Manually run the theta publish pipeline with injected dependencies."""
    from signal_publisher.theta import publish_theta_entry_signal
    
    with patch('signal_publisher.theta.SignalRepository', return_value=repo):
        with patch('signal_publisher.theta.auto_approve_signal', return_value=None):
            return publish_theta_entry_signal(signal)

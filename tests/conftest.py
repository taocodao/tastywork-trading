"""
Shared test fixtures for the signal pipeline test suite.
Provides in-memory SQLite database, signal factories, and mock objects.
"""
import sys
import os
import uuid
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# ─────────────────────────────────────────────────────────────────────
# In-memory SQLite database fixture
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def db_engine():
    """Create an in-memory SQLite engine with all tables."""
    from src.earnings_intelligence.database import Base
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Create a fresh DB session for each test."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def signal_repo(db_session):
    """SignalRepository wired to in-memory DB."""
    from src.earnings_intelligence.database import SignalRepository
    repo = SignalRepository(session=db_session)
    return repo


# ─────────────────────────────────────────────────────────────────────
# Signal dataclass factories
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def theta_entry_signal():
    """Factory for realistic ThetaEntrySignal."""
    from signal_publisher.theta import ThetaEntrySignal
    def _create(**overrides):
        defaults = dict(
            id=str(uuid.uuid4()),
            symbol="SPY",
            strike=580.0,
            expiration=(datetime.now() + timedelta(days=30)).date().isoformat(),
            dte=30,
            entry_price=2.50,
            ask=2.55,
            mid=2.52,
            delta=-0.30,
            theta=0.05,
            vega=0.15,
            iv=0.22,
            confidence=75.0,
            probability_otm=0.70,
            expected_premium=250.0,
            capital_required=58000.0,
            contracts=1,
            total_premium=250.0,
            total_capital_required=58000.0,
            created_at=datetime.now(),
        )
        defaults.update(overrides)
        return ThetaEntrySignal(**defaults)
    return _create


@pytest.fixture
def theta_exit_signal():
    """Factory for ThetaExitSignal."""
    from signal_publisher.theta import ThetaExitSignal
    def _create(**overrides):
        defaults = dict(
            id=str(uuid.uuid4()),
            position_id=str(uuid.uuid4()),
            symbol="SPY",
            strike=580.0,
            expiration="2026-03-20",
            exit_price=0.50,
            exit_reason="profit_target",
            entry_price=2.50,
            pnl=200.0,
            pnl_percent=80.0,
            contracts=1,
            days_held=15,
            created_at=datetime.now(),
        )
        defaults.update(overrides)
        return ThetaExitSignal(**defaults)
    return _create


@pytest.fixture
def zebra_entry_signal():
    """Factory for ZebraEntrySignal."""
    from signal_publisher.zebra import ZebraEntrySignal
    def _create(**overrides):
        defaults = dict(
            id=str(uuid.uuid4()),
            symbol="AAPL",
            direction="LONG",
            long_strike=170.0,
            long_delta=0.75,
            short_strike=180.0,
            short_delta=0.50,
            expiry="2026-04-18",
            dte=45,
            net_debit=5.50,
            max_loss=550.0,
            breakeven=175.50,
            net_delta=1.0,
            net_theta=-0.01,
            net_vega=0.05,
            net_extrinsic=0.20,
            construction_score=85.0,
            directional_confidence=78.0,
            capital_efficiency=1.8,
            anti_crowding_score=70.0,
            composite_score=80.0,
            capital_required=550.0,
            created_at=datetime.utcnow(),
        )
        defaults.update(overrides)
        return ZebraEntrySignal(**defaults)
    return _create


@pytest.fixture
def zebra_exit_signal():
    """Factory for ZebraExitSignal."""
    from signal_publisher.zebra import ZebraExitSignal
    def _create(**overrides):
        defaults = dict(
            id=str(uuid.uuid4()),
            position_id=str(uuid.uuid4()),
            symbol="AAPL",
            direction="LONG",
            exit_credit=7.50,
            exit_reason="PROFIT_TARGET",
            entry_debit=5.50,
            pnl=200.0,
            pnl_percent=36.4,
            contracts=1,
            days_held=20,
            created_at=datetime.utcnow(),
        )
        defaults.update(overrides)
        return ZebraExitSignal(**defaults)
    return _create


@pytest.fixture
def dvo_entry_signal():
    """Factory for DVOEntrySignal."""
    from signal_publisher.dvo import DVOEntrySignal
    def _create(**overrides):
        defaults = dict(
            id=str(uuid.uuid4()),
            symbol="MSFT",
            strategy_type="SHORT_PUT",
            action="SELL_TO_OPEN",
            quantity=1,
            limit_price=3.00,
            expiration="2026-04-18",
            strike=400.0,
            option_type="PUT",
            dte=45,
            current_price=420.0,
            fair_value=450.0,
            margin_of_safety=0.30,
            regime="ACCUMULATION",
            reasoning="Deep value play",
            status="pending",
            created_at=datetime.utcnow().isoformat(),
        )
        defaults.update(overrides)
        return DVOEntrySignal(**defaults)
    return _create


@pytest.fixture
def dvo_exit_signal():
    """Factory for DVOExitSignal."""
    from signal_publisher.dvo import DVOExitSignal
    def _create(**overrides):
        defaults = dict(
            id=str(uuid.uuid4()),
            position_id=str(uuid.uuid4()),
            symbol="MSFT",
            strategy_type="SHORT_PUT",
            action="CLOSE",
            quantity=1,
            limit_price=1.00,
            reason="VELOCITY",
            pnl_pct=66.7,
            status="pending",
            created_at=datetime.utcnow().isoformat(),
        )
        defaults.update(overrides)
        return DVOExitSignal(**defaults)
    return _create


@pytest.fixture
def calendar_setup():
    """Mock SpreadSetup object for calendar signal tests."""
    setup = MagicMock()
    setup.symbol = "SPY"
    setup.strike = 500.0
    setup.short_expiry = (datetime.now() + timedelta(days=7)).date()
    setup.long_expiry = (datetime.now() + timedelta(days=30)).date()
    setup.net_debit = 3.50
    setup.stock_price = 500.5
    setup.score = 80.0
    setup.iv = 0.22
    setup.theta_edge = 0.18
    return setup


@pytest.fixture
def pmcc_entry_signal():
    """Factory for PMCCEntrySignal."""
    from src.pmcc.pmcc_signal_generator import PMCCEntrySignal
    def _create(**overrides):
        defaults = dict(
            id=f"PMCC_ENTRY_AAPL_{datetime.now().strftime('%Y%m%d%H%M%S')}_{str(uuid.uuid4())[:6]}",
            symbol="AAPL",
            action="ENTRY",
            contracts=1,
            total_risk=2790.0,
            long_strike=140.0,
            long_expiration=(datetime.now() + timedelta(days=365)).isoformat(),
            long_dte=365,
            long_delta=0.85,
            long_price=30.0,
            short_strike=185.0,
            short_expiration=(datetime.now() + timedelta(days=30)).isoformat(),
            short_dte=30,
            short_delta=0.28,
            short_price=2.1,
            net_debit=27.9,
            max_loss=2790.0,
            max_profit=1710.0,
            break_even=167.9,
            bci_formula_met=True,
            composite_score=85.0,
            trend_score=75.0,
            iv_rank=25.0,
            confidence=85,
            rationale="BCI criteria met (Break even below short strike). Favorable IV Rank (25.0%)."
        )
        defaults.update(overrides)
        return PMCCEntrySignal(**defaults)
    return _create


@pytest.fixture
def pmcc_cycle_signal():
    """Factory for PMCCShortCallSignal."""
    from src.pmcc.pmcc_signal_generator import PMCCShortCallSignal
    def _create(**overrides):
        defaults = dict(
            id=f"PMCC_CYCLE_AAPL_{datetime.now().strftime('%Y%m%d%H%M%S')}_{str(uuid.uuid4())[:6]}",
            symbol="AAPL",
            action="CYCLE",
            position_id=str(uuid.uuid4()),
            cycle_number=2,
            short_strike=190.0,
            short_expiration=(datetime.now() + timedelta(days=45)).isoformat(),
            short_dte=45,
            short_delta=0.25,
            short_price=2.5,
            leaps_strike=140.0,
            leaps_break_even=167.9,
            rationale="Rolled short call out and slightly up above resistance node."
        )
        defaults.update(overrides)
        return PMCCShortCallSignal(**defaults)
    return _create


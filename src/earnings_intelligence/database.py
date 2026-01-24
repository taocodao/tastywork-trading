"""
Database Models for Earnings Intelligence.
Uses SQLAlchemy with PostgreSQL for persisting earnings data, predictions, and outcomes.
"""

import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.postgresql import JSONB

logger = logging.getLogger(__name__)

# Get database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    os.getenv("DB_URL", "sqlite:///./earnings_intelligence.db")
)

# Create engine and session
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class EarningsCalendar(Base):
    """Store earnings calendar data from Perplexity API."""
    __tablename__ = "earnings_calendar"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(10), nullable=False, index=True)
    announcement_date = Column(DateTime, nullable=True)
    expected_move_pct = Column(Float, nullable=True)
    historical_move_pct = Column(Float, nullable=True)
    iv_rank = Column(Float, nullable=True)
    crush_probability = Column(Float, nullable=True)
    analysis_summary = Column(Text, nullable=True)
    data_source = Column(String(20), default="perplexity")
    raw_response = Column(JSON, nullable=True)  # Store full API response
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to predictions
    predictions = relationship("IVPrediction", back_populates="earnings_event")

    def __repr__(self):
        return f"<EarningsCalendar(symbol={self.symbol}, date={self.announcement_date})>"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "announcement_date": self.announcement_date.isoformat() if self.announcement_date else None,
            "expected_move_pct": self.expected_move_pct,
            "historical_move_pct": self.historical_move_pct,
            "iv_rank": self.iv_rank,
            "crush_probability": self.crush_probability,
            "analysis_summary": self.analysis_summary,
            "data_source": self.data_source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class IVPrediction(Base):
    """Store ML model predictions for IV crush."""
    __tablename__ = "iv_predictions"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(10), nullable=False, index=True)
    earnings_id = Column(Integer, ForeignKey("earnings_calendar.id"), nullable=True)
    prediction_date = Column(DateTime, default=datetime.utcnow)
    days_to_earnings = Column(Integer, nullable=True)
    
    # ML Prediction outputs
    predicted_class = Column(String(20), nullable=False)  # NORMAL, SEVERE, EXPANSION, NO_CRUSH
    predicted_crush_pct = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    class_probabilities = Column(JSON, nullable=True)  # {class: probability}
    
    # Features used for prediction
    features = Column(JSON, nullable=True)
    model_version = Column(String(20), default="v1.0")
    
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    earnings_event = relationship("EarningsCalendar", back_populates="predictions")
    outcome = relationship("PredictionOutcome", back_populates="prediction", uselist=False)

    def __repr__(self):
        return f"<IVPrediction(symbol={self.symbol}, class={self.predicted_class}, conf={self.confidence})>"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "prediction_date": self.prediction_date.isoformat() if self.prediction_date else None,
            "days_to_earnings": self.days_to_earnings,
            "predicted_class": self.predicted_class,
            "predicted_crush_pct": self.predicted_crush_pct,
            "confidence": self.confidence,
            "model_version": self.model_version,
        }


class PredictionOutcome(Base):
    """Track actual outcomes for model evaluation and retraining."""
    __tablename__ = "prediction_outcomes"

    id = Column(Integer, primary_key=True, index=True)
    prediction_id = Column(Integer, ForeignKey("iv_predictions.id"), nullable=False)
    
    # Actual outcomes
    actual_crush_pct = Column(Float, nullable=True)
    actual_class = Column(String(20), nullable=True)
    iv_before = Column(Float, nullable=True)
    iv_after = Column(Float, nullable=True)
    price_move_pct = Column(Float, nullable=True)
    
    # Evaluation
    prediction_correct = Column(Boolean, nullable=True)
    error_magnitude = Column(Float, nullable=True)  # Difference between predicted and actual
    
    recorded_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    prediction = relationship("IVPrediction", back_populates="outcome")

    def __repr__(self):
        return f"<PredictionOutcome(pred_id={self.prediction_id}, correct={self.prediction_correct})>"


class TrainingDataPoint(Base):
    """Historical training data for ML model."""
    __tablename__ = "training_data"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(10), nullable=False, index=True)
    earnings_date = Column(DateTime, nullable=False)
    
    # Features
    days_to_earnings = Column(Integer)
    expected_move_pct = Column(Float)
    historical_move_pct = Column(Float)
    iv_rank = Column(Float)
    rsi_14 = Column(Float)
    bb_position = Column(Float)
    vix_level = Column(Float)
    sector_momentum = Column(Float)
    move_ratio = Column(Float)
    is_mega_cap = Column(Boolean)
    all_features = Column(JSON)  # Full feature vector
    
    # Labels (actual outcomes)
    actual_crush_pct = Column(Float)
    actual_class = Column(String(20))  # NORMAL, SEVERE, EXPANSION, NO_CRUSH
    actual_price_move_pct = Column(Float)
    
    data_source = Column(String(20), default="perplexity")
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<TrainingDataPoint(symbol={self.symbol}, class={self.actual_class})>"


# Database utility functions
def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session():
    """Get a new database session (non-generator version)."""
    return SessionLocal()


# CRUD operations
class EarningsRepository:
    """Repository for earnings calendar operations."""

    def __init__(self, session=None):
        self.session = session or get_session()

    def save_earnings(self, earnings_data: Dict[str, Any]) -> EarningsCalendar:
        """Save or update earnings data."""
        existing = self.session.query(EarningsCalendar).filter(
            EarningsCalendar.symbol == earnings_data.get("symbol"),
            EarningsCalendar.announcement_date == earnings_data.get("announcement_date")
        ).first()

        if existing:
            for key, value in earnings_data.items():
                if hasattr(existing, key) and value is not None:
                    setattr(existing, key, value)
            existing.updated_at = datetime.utcnow()
            self.session.commit()
            return existing
        else:
            earnings = EarningsCalendar(**earnings_data)
            self.session.add(earnings)
            self.session.commit()
            self.session.refresh(earnings)
            return earnings

    def get_by_symbol(self, symbol: str) -> Optional[EarningsCalendar]:
        """Get latest earnings for a symbol."""
        return self.session.query(EarningsCalendar).filter(
            EarningsCalendar.symbol == symbol
        ).order_by(EarningsCalendar.announcement_date.desc()).first()

    def get_upcoming(self, days: int = 14) -> List[EarningsCalendar]:
        """Get all upcoming earnings within N days."""
        from datetime import timedelta
        cutoff = datetime.utcnow() + timedelta(days=days)
        return self.session.query(EarningsCalendar).filter(
            EarningsCalendar.announcement_date <= cutoff,
            EarningsCalendar.announcement_date >= datetime.utcnow()
        ).all()


class PredictionRepository:
    """Repository for IV predictions."""

    def __init__(self, session=None):
        self.session = session or get_session()

    def save_prediction(self, prediction_data: Dict[str, Any]) -> IVPrediction:
        """Save a new prediction."""
        prediction = IVPrediction(**prediction_data)
        self.session.add(prediction)
        self.session.commit()
        self.session.refresh(prediction)
        return prediction

    def save_outcome(self, prediction_id: int, outcome_data: Dict[str, Any]) -> PredictionOutcome:
        """Save prediction outcome for evaluation."""
        outcome = PredictionOutcome(prediction_id=prediction_id, **outcome_data)
        self.session.add(outcome)
        self.session.commit()
        self.session.refresh(outcome)
        return outcome

    def get_recent_predictions(self, symbol: str, limit: int = 10) -> List[IVPrediction]:
        """Get recent predictions for a symbol."""
        return self.session.query(IVPrediction).filter(
            IVPrediction.symbol == symbol
        ).order_by(IVPrediction.created_at.desc()).limit(limit).all()

    def get_model_accuracy(self, model_version: str = None) -> Dict[str, Any]:
        """Calculate model accuracy from outcomes."""
        query = self.session.query(PredictionOutcome).join(IVPrediction)
        
        if model_version:
            query = query.filter(IVPrediction.model_version == model_version)
        
        outcomes = query.all()
        
        if not outcomes:
            return {"accuracy": 0, "total": 0}
        
        correct = sum(1 for o in outcomes if o.prediction_correct)
        return {
            "accuracy": correct / len(outcomes),
            "total": len(outcomes),
            "correct": correct
        }


class TrainingDataRepository:
    """Repository for training data."""

    def __init__(self, session=None):
        self.session = session or get_session()

    def save_training_point(self, data: Dict[str, Any]) -> TrainingDataPoint:
        """Save a training data point."""
        point = TrainingDataPoint(**data)
        self.session.add(point)
        self.session.commit()
        self.session.refresh(point)
        return point

    def get_all_training_data(self) -> List[TrainingDataPoint]:
        """Get all training data."""
        return self.session.query(TrainingDataPoint).all()

    def get_training_data_count(self) -> int:
        """Get count of training data points."""
        return self.session.query(TrainingDataPoint).count()


class Signal(Base):
    """Store generated trading signals."""
    __tablename__ = "signals"

    id = Column(String(36), primary_key=True, index=True)
    symbol = Column(String(10), nullable=False, index=True)
    strategy = Column(String(50), nullable=True)
    status = Column(String(20), default="pending", index=True)  # pending, approved, executed, failed, expired
    
    # Store full signal object as JSON
    data = Column(JSON, nullable=False)
    
    # Expiration fields
    expires_at = Column(DateTime, nullable=True, index=True)  # When signal becomes invalid
    front_expiry = Column(DateTime, nullable=True)  # Short leg expiration (for calendar spreads)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    
    # Relationship to user executions
    user_executions = relationship("UserSignalExecution", back_populates="signal")

    def __repr__(self):
        return f"<Signal(id={self.id}, symbol={self.symbol}, status={self.status})>"

    def to_dict(self) -> Dict[str, Any]:
        """Return the JSON data with dynamic status updates."""
        signal_data = dict(self.data)
        signal_data['status'] = self.status
        if self.approved_at:
            signal_data['approvedAt'] = self.approved_at.isoformat()
        if self.executed_at:
            signal_data['executedAt'] = self.executed_at.isoformat()
        if self.expires_at:
            signal_data['expiresAt'] = self.expires_at.isoformat()
        return signal_data
    
    def is_expired(self) -> bool:
        """Check if signal has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at


class UserSignalExecution(Base):
    """Track each user's execution status for a signal."""
    __tablename__ = "user_signal_executions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(64), nullable=False, index=True)  # Privy user ID
    signal_id = Column(String(36), ForeignKey("signals.id"), nullable=False, index=True)
    
    status = Column(String(20), default="pending")  # pending, approved, executed, rejected, failed
    order_id = Column(String(64), nullable=True)  # Tastytrade order ID
    error_message = Column(Text, nullable=True)  # Error details if failed
    
    created_at = Column(DateTime, default=datetime.utcnow)  # When user first interacted
    approved_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    
    # Relationship
    signal = relationship("Signal", back_populates="user_executions")

    def __repr__(self):
        return f"<UserSignalExecution(user={self.user_id}, signal={self.signal_id}, status={self.status})>"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "userId": self.user_id,
            "signalId": self.signal_id,
            "status": self.status,
            "orderId": self.order_id,
            "errorMessage": self.error_message,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "approvedAt": self.approved_at.isoformat() if self.approved_at else None,
            "executedAt": self.executed_at.isoformat() if self.executed_at else None,
        }


class Position(Base):
    """Track open calendar spread positions for risk management."""
    __tablename__ = "positions"

    id = Column(String(64), primary_key=True, index=True)  # Order ID from Tastytrade
    user_id = Column(String(64), nullable=False, index=True)
    signal_id = Column(String(36), ForeignKey("signals.id"), nullable=True)
    
    # Position details
    symbol = Column(String(10), nullable=False, index=True)
    strategy = Column(String(30), default="Calendar Spread")
    direction = Column(String(10), default="NEUTRAL")  # BULL/BEAR/NEUTRAL
    
    # Contract details
    front_expiry = Column(DateTime, nullable=True)
    back_expiry = Column(DateTime, nullable=True)
    strike = Column(Float, nullable=True)
    quantity = Column(Integer, default=1)
    front_symbol = Column(String(50), nullable=True)  # OCC symbol for front leg
    back_symbol = Column(String(50), nullable=True)   # OCC symbol for back leg
    
    # Entry pricing
    entry_debit = Column(Float, nullable=True)  # Net debit paid (per contract)
    entry_stock_price = Column(Float, nullable=True)  # Underlying price at entry
    entry_front_iv = Column(Float, nullable=True)  # Front month IV at entry
    
    # Risk parameters (calculated at entry)
    max_profit = Column(Float, nullable=True)  # Target credit when closing
    max_loss = Column(Float, nullable=True)  # Entry debit (what we paid)
    stop_loss_price = Column(Float, nullable=True)  # Exit if spread value drops to this
    profit_target_price = Column(Float, nullable=True)  # Exit if spread value rises to this
    
    # Current state (updated by monitor)
    current_value = Column(Float, nullable=True)  # Current spread mid price
    unrealized_pnl = Column(Float, nullable=True)  # Current P&L
    last_checked = Column(DateTime, nullable=True)  # Last time position was evaluated
    
    # Status
    status = Column(String(20), default="open", index=True)  # open, closing, closed, expired
    closed_at = Column(DateTime, nullable=True)
    exit_reason = Column(String(100), nullable=True)
    exit_pnl = Column(Float, nullable=True)
    exit_order_id = Column(String(64), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Position(id={self.id}, symbol={self.symbol}, status={self.status})>"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "userId": self.user_id,
            "signalId": self.signal_id,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "direction": self.direction,
            "frontExpiry": self.front_expiry.isoformat() if self.front_expiry else None,
            "backExpiry": self.back_expiry.isoformat() if self.back_expiry else None,
            "strike": self.strike,
            "quantity": self.quantity,
            "frontSymbol": self.front_symbol,
            "backSymbol": self.back_symbol,
            "entryDebit": self.entry_debit,
            "entryStockPrice": self.entry_stock_price,
            "maxProfit": self.max_profit,
            "maxLoss": self.max_loss,
            "stopLossPrice": self.stop_loss_price,
            "profitTargetPrice": self.profit_target_price,
            "currentValue": self.current_value,
            "unrealizedPnl": self.unrealized_pnl,
            "status": self.status,
            "exitReason": self.exit_reason,
            "exitPnl": self.exit_pnl,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "closedAt": self.closed_at.isoformat() if self.closed_at else None,
        }
    
    def calculate_pnl(self, current_spread_value: float) -> float:
        """Calculate unrealized P&L based on current spread value."""
        if self.entry_debit is None:
            return 0.0
        # P&L = (current value - entry debit) * quantity * 100
        return (current_spread_value - self.entry_debit) * self.quantity * 100
    
    def get_front_dte(self) -> int:
        """Get days to expiration for front leg."""
        if self.front_expiry is None:
            return 999
        from datetime import date
        if isinstance(self.front_expiry, datetime):
            return (self.front_expiry.date() - date.today()).days
        return (self.front_expiry - date.today()).days


class SignalRepository:
    """Repository for signal operations."""

    def __init__(self, session=None):
        self.session = session or get_session()

    def save_signal(self, signal_data: Dict[str, Any]) -> Signal:
        """Save or update a signal."""
        signal_id = signal_data.get('id')
        existing = self.session.query(Signal).filter(Signal.id == signal_id).first()

        if existing:
            # Update fields
            existing.status = signal_data.get('status', existing.status)
            existing.data = signal_data
            if existing.status == 'approved' and not existing.approved_at:
                existing.approved_at = datetime.utcnow()
            if existing.status == 'executed' and not existing.executed_at:
                existing.executed_at = datetime.utcnow()
            existing.updated_at = datetime.utcnow()
            self.session.commit()
            return existing
        else:
            # Create new
            signal = Signal(
                id=signal_id,
                symbol=signal_data.get('symbol'),
                strategy=signal_data.get('strategy'),
                status=signal_data.get('status', 'pending'),
                data=signal_data,
                created_at=datetime.utcnow()
            )
            self.session.add(signal)
            self.session.commit()
            return signal

    def get_all_signals(self, status: str = None, include_expired: bool = False) -> List[Signal]:
        """Get all signals, optionally filtered by status and expiration."""
        query = self.session.query(Signal)
        if status:
            query = query.filter(Signal.status == status)
        if not include_expired:
            # Exclude expired signals
            query = query.filter(
                (Signal.expires_at == None) | (Signal.expires_at > datetime.utcnow())
            )
        return query.order_by(Signal.created_at.desc()).all()

    def get_signal(self, signal_id: str) -> Optional[Signal]:
        """Get a specific signal."""
        return self.session.query(Signal).filter(Signal.id == signal_id).first()
    
    def expire_old_signals(self) -> int:
        """Mark expired signals as 'expired'. Returns count of updated signals."""
        expired = self.session.query(Signal).filter(
            Signal.status == 'pending',
            Signal.expires_at != None,
            Signal.expires_at < datetime.utcnow()
        ).all()
        
        for signal in expired:
            signal.status = 'expired'
            signal.updated_at = datetime.utcnow()
        
        self.session.commit()
        return len(expired)


class UserSignalRepository:
    """Repository for per-user signal execution tracking."""

    def __init__(self, session=None):
        self.session = session or get_session()

    def get_user_execution(self, user_id: str, signal_id: str) -> Optional[UserSignalExecution]:
        """Get a user's execution status for a specific signal."""
        return self.session.query(UserSignalExecution).filter(
            UserSignalExecution.user_id == user_id,
            UserSignalExecution.signal_id == signal_id
        ).first()

    def get_user_executions(self, user_id: str, status: str = None) -> List[UserSignalExecution]:
        """Get all executions for a user."""
        query = self.session.query(UserSignalExecution).filter(
            UserSignalExecution.user_id == user_id
        )
        if status:
            query = query.filter(UserSignalExecution.status == status)
        return query.order_by(UserSignalExecution.created_at.desc()).all()

    def create_or_update_execution(
        self,
        user_id: str,
        signal_id: str,
        status: str,
        order_id: str = None,
        error_message: str = None
    ) -> UserSignalExecution:
        """Create or update a user's execution for a signal."""
        existing = self.get_user_execution(user_id, signal_id)
        
        if existing:
            existing.status = status
            if order_id:
                existing.order_id = order_id
            if error_message:
                existing.error_message = error_message
            if status == 'approved' and not existing.approved_at:
                existing.approved_at = datetime.utcnow()
            if status == 'executed' and not existing.executed_at:
                existing.executed_at = datetime.utcnow()
            self.session.commit()
            return existing
        else:
            execution = UserSignalExecution(
                user_id=user_id,
                signal_id=signal_id,
                status=status,
                order_id=order_id,
                error_message=error_message,
                created_at=datetime.utcnow()
            )
            if status == 'approved':
                execution.approved_at = datetime.utcnow()
            if status == 'executed':
                execution.executed_at = datetime.utcnow()
            self.session.add(execution)
            self.session.commit()
            return execution

    def get_signal_execution_count(self, signal_id: str) -> int:
        """Get count of users who have executed a signal."""
        return self.session.query(UserSignalExecution).filter(
            UserSignalExecution.signal_id == signal_id,
            UserSignalExecution.status == 'executed'
        ).count()


class PositionRepository:
    """Repository for position tracking and risk management."""

    def __init__(self, session=None):
        self.session = session or get_session()

    def save_position(self, position_data: Dict[str, Any]) -> Position:
        """Save a new position after trade execution."""
        position = Position(
            id=position_data.get('order_id') or position_data.get('id'),
            user_id=position_data.get('user_id'),
            signal_id=position_data.get('signal_id'),
            symbol=position_data.get('symbol'),
            strategy=position_data.get('strategy', 'Calendar Spread'),
            direction=position_data.get('direction', 'NEUTRAL'),
            front_expiry=position_data.get('front_expiry'),
            back_expiry=position_data.get('back_expiry'),
            strike=position_data.get('strike'),
            quantity=position_data.get('quantity', 1),
            front_symbol=position_data.get('front_symbol'),
            back_symbol=position_data.get('back_symbol'),
            entry_debit=position_data.get('entry_debit'),
            entry_stock_price=position_data.get('entry_stock_price'),
            entry_front_iv=position_data.get('entry_front_iv'),
            max_loss=position_data.get('entry_debit'),  # Max loss = entry debit
            profit_target_price=position_data.get('entry_debit', 0) * 1.25,  # 25% profit target
            stop_loss_price=position_data.get('entry_debit', 0) * 0.50,  # 50% stop loss
            status='open'
        )
        self.session.add(position)
        self.session.commit()
        self.session.refresh(position)
        logger.info(f"Position saved: {position.symbol} (ID: {position.id})")
        return position

    def get_position(self, position_id: str) -> Optional[Position]:
        """Get a specific position by ID."""
        return self.session.query(Position).filter(Position.id == position_id).first()

    def get_open_positions(self, user_id: str = None) -> List[Position]:
        """Get all open positions, optionally filtered by user."""
        query = self.session.query(Position).filter(Position.status == 'open')
        if user_id:
            query = query.filter(Position.user_id == user_id)
        return query.order_by(Position.created_at.desc()).all()

    def get_positions_needing_check(self, stale_minutes: int = 5) -> List[Position]:
        """Get open positions that haven't been checked recently."""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(minutes=stale_minutes)
        return self.session.query(Position).filter(
            Position.status == 'open',
            (Position.last_checked == None) | (Position.last_checked < cutoff)
        ).all()

    def update_position_value(self, position_id: str, current_value: float, pnl: float) -> Optional[Position]:
        """Update position with current market value."""
        position = self.get_position(position_id)
        if position:
            position.current_value = current_value
            position.unrealized_pnl = pnl
            position.last_checked = datetime.utcnow()
            self.session.commit()
        return position

    def close_position(
        self, 
        position_id: str, 
        exit_reason: str, 
        exit_pnl: float,
        exit_order_id: str = None
    ) -> Optional[Position]:
        """Mark a position as closed."""
        position = self.get_position(position_id)
        if position:
            position.status = 'closed'
            position.closed_at = datetime.utcnow()
            position.exit_reason = exit_reason
            position.exit_pnl = exit_pnl
            position.exit_order_id = exit_order_id
            self.session.commit()
            logger.info(f"Position closed: {position.symbol} - {exit_reason} (P&L: ${exit_pnl:.2f})")
        return position

    def get_user_positions_summary(self, user_id: str) -> Dict[str, Any]:
        """Get summary of user's positions."""
        open_positions = self.get_open_positions(user_id)
        total_pnl = sum(p.unrealized_pnl or 0 for p in open_positions)
        return {
            "openCount": len(open_positions),
            "totalUnrealizedPnl": round(total_pnl, 2),
            "positions": [p.to_dict() for p in open_positions]
        }


# Initialize tables on import (can be disabled)
if os.getenv("AUTO_INIT_DB", "false").lower() == "true":
    init_db()


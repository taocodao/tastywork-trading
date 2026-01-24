"""
Calendar Spreads Bot - Position Manager
========================================

Tracks open positions, monitors P&L, and handles exits.
"""

import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, date
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
import uuid

from config import (
    PROFIT_TARGET_PCT, STOP_LOSS_PCT, MAX_HOLD_HOURS,
    POSITIONS_FILE, LOG_DIR
)
from scanner import SpreadSetup

logger = logging.getLogger(__name__)


class PositionStatus(Enum):
    """Position lifecycle status."""
    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSED_PROFIT = "CLOSED_PROFIT"
    CLOSED_LOSS = "CLOSED_LOSS"
    CLOSED_TIME = "CLOSED_TIME"
    CLOSED_MANUAL = "CLOSED_MANUAL"


class ExitReason(Enum):
    """Reason for closing a position."""
    PROFIT_TARGET = "PROFIT_TARGET"
    STOP_LOSS = "STOP_LOSS"
    MAX_HOLD_TIME = "MAX_HOLD_TIME"
    MANUAL = "MANUAL"
    SHORT_EXPIRY = "SHORT_EXPIRY"


@dataclass
class Position:
    """An open or closed calendar spread position."""
    id: str
    symbol: str
    strike: float
    short_expiry: str  # YYYY-MM-DD
    long_expiry: str   # YYYY-MM-DD
    
    # Entry
    entry_time: str
    entry_debit: float
    contracts: int
    
    # Targets
    profit_target: float  # Spread value at target
    stop_loss: float      # Spread value at stop
    
    # Current state
    status: str = PositionStatus.OPEN.value
    current_value: float = 0.0
    unrealized_pnl: float = 0.0
    
    # Exit
    exit_time: Optional[str] = None
    exit_value: Optional[float] = None
    exit_reason: Optional[str] = None
    realized_pnl: Optional[float] = None
    
    @property
    def is_open(self) -> bool:
        return self.status == PositionStatus.OPEN.value
    
    @property
    def pnl_pct(self) -> float:
        """Current P&L as percentage of entry."""
        if self.entry_debit > 0:
            return (self.current_value - self.entry_debit) / self.entry_debit * 100
        return 0.0
    
    @property
    def total_cost(self) -> float:
        """Total cost of position (per contract)."""
        return self.entry_debit * self.contracts
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Position':
        return cls(**data)
    
    @classmethod
    def from_setup(
        cls,
        setup: SpreadSetup,
        contracts: int = 1,
        profit_target_pct: float = PROFIT_TARGET_PCT,
        stop_loss_pct: float = STOP_LOSS_PCT
    ) -> 'Position':
        """Create a new position from a SpreadSetup."""
        return cls(
            id=str(uuid.uuid4())[:8],
            symbol=setup.symbol,
            strike=setup.strike,
            short_expiry=setup.short_expiry.isoformat(),
            long_expiry=setup.long_expiry.isoformat(),
            entry_time=datetime.now().isoformat(),
            entry_debit=setup.net_debit,
            contracts=contracts,
            profit_target=setup.net_debit * (1 + profit_target_pct / 100),
            stop_loss=setup.net_debit * (1 + stop_loss_pct / 100),
            current_value=setup.net_debit
        )


@dataclass
class ExitSignal:
    """Signal indicating position should be closed."""
    should_exit: bool
    reason: Optional[ExitReason] = None
    message: str = ""


class PositionManager:
    """
    Manages the lifecycle of calendar spread positions.
    
    - Opens new positions
    - Updates current values
    - Checks exit conditions
    - Closes positions
    - Persists state to disk
    """
    
    def __init__(self, positions_file: str = None):
        """Initialize position manager."""
        self.positions_file = Path(positions_file or POSITIONS_FILE)
        self.positions: Dict[str, Position] = {}
        
        # Ensure log directory exists
        Path(LOG_DIR).mkdir(exist_ok=True)
        
        # Load existing positions
        self._load_positions()
    
    def _load_positions(self):
        """Load positions from disk."""
        if self.positions_file.exists():
            try:
                with open(self.positions_file, 'r') as f:
                    data = json.load(f)
                    for pos_data in data:
                        pos = Position.from_dict(pos_data)
                        self.positions[pos.id] = pos
                logger.info(f"Loaded {len(self.positions)} positions")
            except Exception as e:
                logger.error(f"Error loading positions: {e}")
    
    def _save_positions(self):
        """Save positions to disk."""
        try:
            data = [pos.to_dict() for pos in self.positions.values()]
            with open(self.positions_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving positions: {e}")
    
    def open_position(self, setup: SpreadSetup, contracts: int = 1) -> Position:
        """
        Open a new position from a setup.
        
        Args:
            setup: The SpreadSetup to trade
            contracts: Number of contracts
        
        Returns:
            The new Position object
        """
        position = Position.from_setup(setup, contracts)
        self.positions[position.id] = position
        self._save_positions()
        
        logger.info(
            f"Opened position {position.id}: "
            f"{position.symbol} ${position.strike} x{contracts}, "
            f"debit ${position.entry_debit:.2f}"
        )
        
        return position
    
    def update_position(
        self,
        position_id: str,
        current_value: float
    ) -> Position:
        """
        Update a position's current value.
        
        Args:
            position_id: Position ID
            current_value: Current spread value
        
        Returns:
            Updated Position
        """
        if position_id not in self.positions:
            raise ValueError(f"Position {position_id} not found")
        
        pos = self.positions[position_id]
        pos.current_value = current_value
        pos.unrealized_pnl = (current_value - pos.entry_debit) * pos.contracts
        
        self._save_positions()
        return pos
    
    def check_exit_conditions(self, position: Position) -> ExitSignal:
        """
        Check if a position should be closed.
        
        Returns:
            ExitSignal with decision and reason
        """
        if not position.is_open:
            return ExitSignal(False)
        
        # Check profit target
        if position.current_value >= position.profit_target:
            pnl_pct = position.pnl_pct
            return ExitSignal(
                should_exit=True,
                reason=ExitReason.PROFIT_TARGET,
                message=f"Profit target hit: +{pnl_pct:.1f}%"
            )
        
        # Check stop loss
        if position.current_value <= position.stop_loss:
            pnl_pct = position.pnl_pct
            return ExitSignal(
                should_exit=True,
                reason=ExitReason.STOP_LOSS,
                message=f"Stop loss hit: {pnl_pct:.1f}%"
            )
        
        # Check max hold time
        entry_dt = datetime.fromisoformat(position.entry_time)
        hours_held = (datetime.now() - entry_dt).total_seconds() / 3600
        
        if hours_held >= MAX_HOLD_HOURS:
            return ExitSignal(
                should_exit=True,
                reason=ExitReason.MAX_HOLD_TIME,
                message=f"Max hold time reached: {hours_held:.1f} hours"
            )
        
        # Check if short leg is expiring today
        short_expiry = date.fromisoformat(position.short_expiry)
        if short_expiry <= date.today():
            return ExitSignal(
                should_exit=True,
                reason=ExitReason.SHORT_EXPIRY,
                message="Short leg expiring today"
            )
        
        return ExitSignal(False)
    
    def close_position(
        self,
        position_id: str,
        exit_value: float,
        reason: ExitReason
    ) -> Position:
        """
        Close a position.
        
        Args:
            position_id: Position ID
            exit_value: Closing spread value
            reason: Why we're closing
        
        Returns:
            Closed Position
        """
        if position_id not in self.positions:
            raise ValueError(f"Position {position_id} not found")
        
        pos = self.positions[position_id]
        
        # Update position
        pos.exit_time = datetime.now().isoformat()
        pos.exit_value = exit_value
        pos.exit_reason = reason.value
        pos.realized_pnl = (exit_value - pos.entry_debit) * pos.contracts
        
        # Set status based on P&L
        if pos.realized_pnl > 0:
            pos.status = PositionStatus.CLOSED_PROFIT.value
        else:
            pos.status = PositionStatus.CLOSED_LOSS.value
        
        self._save_positions()
        
        pnl_pct = (exit_value - pos.entry_debit) / pos.entry_debit * 100
        logger.info(
            f"Closed position {position_id}: "
            f"P&L ${pos.realized_pnl:.2f} ({pnl_pct:+.1f}%) - "
            f"{reason.value}"
        )
        
        return pos
    
    def get_open_positions(self) -> List[Position]:
        """Get all open positions."""
        return [p for p in self.positions.values() if p.is_open]
    
    def get_closed_positions(self) -> List[Position]:
        """Get all closed positions."""
        return [p for p in self.positions.values() if not p.is_open]
    
    def get_today_pnl(self) -> float:
        """Get total P&L for positions closed today."""
        today = date.today().isoformat()
        total = 0.0
        
        for pos in self.get_closed_positions():
            if pos.exit_time and pos.exit_time.startswith(today):
                total += pos.realized_pnl or 0
        
        return total
    
    def get_stats(self) -> dict:
        """Get overall statistics."""
        closed = self.get_closed_positions()
        
        wins = [p for p in closed if p.realized_pnl and p.realized_pnl > 0]
        losses = [p for p in closed if p.realized_pnl and p.realized_pnl <= 0]
        
        total_pnl = sum(p.realized_pnl or 0 for p in closed)
        
        return {
            "total_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(closed) * 100 if closed else 0,
            "total_pnl": total_pnl,
            "avg_win": sum(p.realized_pnl for p in wins) / len(wins) if wins else 0,
            "avg_loss": sum(p.realized_pnl for p in losses) / len(losses) if losses else 0,
            "open_positions": len(self.get_open_positions()),
        }

    def sync_with_tastytrade(self, client):
        """
        Sync open positions with Tastytrade (optional).
        
        Args:
            client: TastytradeClient instance
        """
        if not client or not client.is_connected:
            return
            
        try:
            broker_positions = client.get_option_positions()
            # Map broker positions by symbol/expiry/strike to match local positions
            # This is complex because a calendar spread has two legs (short/long)
            # For now, we'll just log the discrepancy if count doesn't match
            
            local_open_count = len(self.get_open_positions())
            broker_open_count = len(broker_positions)
            
            logger.info(f"Sync: Local positions: {local_open_count}, Broker positions items: {broker_open_count}")
            
            # TODO: Implement full reconciliation logic
            # This requires matching individual legs to spread IDs
            
        except Exception as e:
            logger.error(f"Error syncing with Tastytrade: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    from scanner import CalendarSpreadScanner
    
    print("Position Manager Demo")
    print("=" * 60)
    
    # Get a setup
    scanner = CalendarSpreadScanner()
    setup = scanner.get_best_setup()
    
    if not setup:
        print("No setups found")
        exit()
    
    print(f"Setup: {setup}")
    
    # Create position manager
    pm = PositionManager()
    
    # Open position
    pos = pm.open_position(setup, contracts=1)
    print(f"\nOpened: {pos.id}")
    print(f"  Entry: ${pos.entry_debit:.2f}")
    print(f"  Target: ${pos.profit_target:.2f} (+5%)")
    print(f"  Stop: ${pos.stop_loss:.2f} (-10%)")
    
    # Simulate value update
    new_value = pos.entry_debit * 1.06  # +6%
    pm.update_position(pos.id, new_value)
    
    # Check exit
    exit_signal = pm.check_exit_conditions(pos)
    print(f"\nExit signal: {exit_signal}")
    
    if exit_signal.should_exit:
        pm.close_position(pos.id, new_value, exit_signal.reason)
    
    # Show stats
    print("\nStats:")
    stats = pm.get_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")

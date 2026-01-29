"""
Portfolio Manager for Theta Strategy
====================================

Tracks open put positions and manages capital allocation.

Features:
- Track open positions with Greeks and P&L
- Reserve/release capital (strike × 100 × contracts)
- Calculate portfolio utilization and heat
- Update position Greeks in real-time
- Support capital redeployment
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Dict, Optional
import json

logger = logging.getLogger(__name__)


@dataclass
class ThetaPosition:
    """Open cash-secured put position."""
    position_id: str
    symbol: str
    strike: float
    expiration: date
    entry_date: date
    entry_price: float
    
    # Position sizing
    contracts: int
    capital_reserved: float
    premium_received: float
    
    # Current state
    current_bid: float = 0.0
    current_ask: float = 0.0
    current_mid: float = 0.0
    
    # Greeks
    delta: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    gamma: float = 0.0
    iv: float = 0.0
    
    # P&L
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    
    # Days tracking
    days_held: int = 0
    days_to_expiration: int = 0
    
    # Metadata
    last_updated: datetime = None
    status: str = "OPEN"  # OPEN, CLOSED
    
    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.now()


@dataclass
class PortfolioState:
    """Current state of Theta portfolio."""
    total_capital: float
    reserved_capital: float
    available_capital: float
    current_heat: float
    heat_pct: float
    
    position_count: int
    open_symbols: List[str]
    
    total_premium_received: float
    total_unrealized_pnl: float
    total_unrealized_pnl_pct: float
    
    positions: List[ThetaPosition]


class ThetaPortfolioManager:
    """
    Manage Theta strategy portfolio state and capital allocation.
    
    Usage:
        manager = ThetaPortfolioManager(total_capital=100000)
        
        # Add position
        position = manager.add_position(entry_signal, fill_price=1.15)
        
        # Update Greeks
        manager.update_position_greeks(position.position_id, current_data)
        
        # Check state
        state = manager.get_portfolio_state()
        print(f"Available capital: ${state.available_capital:,.0f}")
    """
    
    def __init__(
        self,
        total_capital: float,
        positions_file: str = "theta_positions.json"
    ):
        """
        Initialize portfolio manager.
        
        Args:
            total_capital: Total account capital
            positions_file: File to persist positions (default: theta_positions.json)
        """
        self.total_capital = total_capital
        self.positions_file = positions_file
        
        # In-memory position tracking
        self.positions: Dict[str, ThetaPosition] = {}
        
        # Load existing positions
        self._load_positions()
    
    def add_position(
        self,
        symbol: str,
        strike: float,
        expiration: date,
        entry_price: float,
        contracts: int,
        position_id: Optional[str] = None,
        delta: float = 0.0,
        theta: float = 0.0,
        vega: float = 0.0,
        iv: float = 0.0
    ) -> ThetaPosition:
        """
        Add a new position to the portfolio.
        
        Args:
            symbol: Stock symbol
            strike: Put strike price
            expiration: Expiration date
            entry_price: Fill price for the puts sold
            contracts: Number of contracts
            position_id: Optional custom ID
            delta, theta, vega, iv: Initial Greeks
            
        Returns:
            ThetaPosition object
        """
        if position_id is None:
            position_id = f"{symbol}_{strike}_{expiration.isoformat()}_{datetime.now().timestamp()}"
        
        capital_reserved = strike * 100 * contracts
        premium_received = entry_price * 100 * contracts
        
        position = ThetaPosition(
            position_id=position_id,
            symbol=symbol,
            strike=strike,
            expiration=expiration,
            entry_date=date.today(),
            entry_price=entry_price,
            contracts=contracts,
            capital_reserved=capital_reserved,
            premium_received=premium_received,
            current_bid=entry_price,
            current_ask=entry_price,
            current_mid=entry_price,
            delta=delta,
            theta=theta,
            vega=vega,
            iv=iv,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
            last_updated=datetime.now(),
            status="OPEN"
        )
        
        self.positions[position_id] = position
        self._save_positions()
        
        logger.info(f"Added position: {symbol} {strike}P | Contracts: {contracts} | "
                   f"Capital reserved: ${capital_reserved:,.0f} | Premium: ${premium_received:,.0f}")
        
        return position
    
    def update_position_greeks(
        self,
        position_id: str,
        current_data: Dict
    ):
        """
        Update position with current market data and Greeks.
        
        Args:
            position_id: Position ID
            current_data: Dict with bid, ask, delta, theta, vega, iv
        """
        if position_id not in self.positions:
            logger.warning(f"Position {position_id} not found")
            return
        
        position = self.positions[position_id]
        
        # Update prices
        position.current_bid = current_data.get("bid", position.current_bid)
        position.current_ask = current_data.get("ask", position.current_ask)
        position.current_mid = (position.current_bid + position.current_ask) / 2
        
        # Update Greeks
        position.delta = current_data.get("delta", position.delta)
        position.theta = current_data.get("theta", position.theta)
        position.vega = current_data.get("vega", position.vega)
        position.gamma = current_data.get("gamma", position.gamma)
        position.iv = current_data.get("iv", position.iv)
        
        # Calculate P&L
        # We SOLD the put, so profit when option price goes DOWN
        pnl_per_contract = (position.entry_price - position.current_ask) * 100
        position.unrealized_pnl = pnl_per_contract * position.contracts
        position.unrealized_pnl_pct = ((position.entry_price - position.current_ask) / position.entry_price) * 100
        
        position.last_updated = datetime.now()
        
        self._save_positions()
    
    def close_position(
        self,
        position_id: str,
        exit_price: float
    ) -> float:
        """
        Close a position and release capital.
        
        Args:
            position_id: Position ID
            exit_price: Exit fill price
            
        Returns:
            Capital released
        """
        if position_id not in self.positions:
            logger.warning(f"Position {position_id} not found")
            return 0.0
        
        position = self.positions[position_id]
        position.status = "CLOSED"
        
        # Calculate final P&L
        pnl_per_contract = (position.entry_price - exit_price) * 100
        realized_pnl = pnl_per_contract * position.contracts
        realized_pnl_pct = ((position.entry_price - exit_price) / position.entry_price) * 100
        
        capital_released = position.capital_reserved
        
        logger.info(f"Closed position: {position.symbol} {position.strike}P | "
                   f"P&L: ${realized_pnl:,.0f} ({realized_pnl_pct:.1f}%) | "
                   f"Capital released: ${capital_released:,.0f}")
        
        # Remove from active positions
        del self.positions[position_id]
        self._save_positions()
        
        return capital_released
    
    def reserve_capital(self, strike: float, contracts: int) -> float:
        """
        Calculate capital required for a position.
        
        Args:
            strike: Put strike price
            contracts: Number of contracts
            
        Returns:
            Capital required
        """
        return strike * 100 * contracts
    
    def release_capital(self, position_id: str) -> float:
        """
        Get capital to be released when closing a position.
        
        Args:
            position_id: Position ID
            
        Returns:
            Capital amount
        """
        if position_id in self.positions:
            return self.positions[position_id].capital_reserved
        return 0.0
    
    def get_portfolio_state(self) -> PortfolioState:
        """
        Get current portfolio state.
        
        Returns:
            PortfolioState object
        """
        reserved_capital = sum(p.capital_reserved for p in self.positions.values())
        available_capital = self.total_capital - reserved_capital
        current_heat = reserved_capital
        heat_pct = (current_heat / self.total_capital) * 100 if self.total_capital > 0 else 0
        
        position_count = len(self.positions)
        open_symbols = [p.symbol for p in self.positions.values()]
        
        total_premium_received = sum(p.premium_received for p in self.positions.values())
        total_unrealized_pnl = sum(p.unrealized_pnl for p in self.positions.values())
        total_unrealized_pnl_pct = (total_unrealized_pnl / total_premium_received) * 100 if total_premium_received > 0 else 0
        
        return PortfolioState(
            total_capital=self.total_capital,
            reserved_capital=reserved_capital,
            available_capital=available_capital,
            current_heat=current_heat,
            heat_pct=heat_pct,
            position_count=position_count,
            open_symbols=open_symbols,
            total_premium_received=total_premium_received,
            total_unrealized_pnl=total_unrealized_pnl,
            total_unrealized_pnl_pct=total_unrealized_pnl_pct,
            positions=list(self.positions.values())
        )
    
    def get_position(self, position_id: str) -> Optional[ThetaPosition]:
        """Get a specific position by ID."""
        return self.positions.get(position_id)
    
    def get_all_positions(self) -> List[ThetaPosition]:
        """Get all open positions."""
        return list(self.positions.values())
    
    def get_open_positions(self) -> List[ThetaPosition]:
        """Get all positions with status OPEN."""
        return [p for p in self.positions.values() if p.status == "OPEN"]
    
    def update_position_state(self, position_id: str, current_price: float):
        """Update position with current price and calculate P&L."""
        if position_id not in self.positions:
            return
        
        position = self.positions[position_id]
        position.current_ask = current_price
        position.current_bid = current_price
        position.current_mid = current_price
        
        # Calculate P&L (we sold puts, profit when price drops)
        pnl_per_contract = (position.entry_price - current_price) * 100
        position.unrealized_pnl = pnl_per_contract * position.contracts
        position.unrealized_pnl_pct = (
            ((position.entry_price - current_price) / position.entry_price) * 100
            if position.entry_price > 0 else 0
        )
        
        # Update days
        position.days_held = (date.today() - position.entry_date).days
        position.days_to_expiration = (position.expiration - date.today()).days
        position.last_updated = datetime.now()
        
        self._save_positions()
    
    def _save_positions(self):
        """Persist positions to disk."""
        try:
            data = {}
            for pid, position in self.positions.items():
                data[pid] = {
                    "position_id": position.position_id,
                    "symbol": position.symbol,
                    "strike": position.strike,
                    "expiration": position.expiration.isoformat(),
                    "entry_date": position.entry_date.isoformat(),
                    "entry_price": position.entry_price,
                    "contracts": position.contracts,
                    "capital_reserved": position.capital_reserved,
                    "premium_received": position.premium_received,
                    "current_bid": position.current_bid,
                    "current_ask": position.current_ask,
                    "current_mid": position.current_mid,
                    "delta": position.delta,
                    "theta": position.theta,
                    "vega": position.vega,
                    "gamma": position.gamma,
                    "iv": position.iv,
                    "unrealized_pnl": position.unrealized_pnl,
                    "unrealized_pnl_pct": position.unrealized_pnl_pct,
                    "last_updated": position.last_updated.isoformat(),
                    "status": position.status
                }
            
            with open(self.positions_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving positions: {e}")
    
    def _load_positions(self):
        """Load positions from disk."""
        try:
            with open(self.positions_file, 'r') as f:
                data = json.load(f)
            
            for pid, pos_data in data.items():
                position = ThetaPosition(
                    position_id=pos_data["position_id"],
                    symbol=pos_data["symbol"],
                    strike=pos_data["strike"],
                    expiration=datetime.fromisoformat(pos_data["expiration"]).date(),
                    entry_date=datetime.fromisoformat(pos_data["entry_date"]).date(),
                    entry_price=pos_data["entry_price"],
                    contracts=pos_data["contracts"],
                    capital_reserved=pos_data["capital_reserved"],
                    premium_received=pos_data["premium_received"],
                    current_bid=pos_data["current_bid"],
                    current_ask=pos_data["current_ask"],
                    current_mid=pos_data["current_mid"],
                    delta=pos_data["delta"],
                    theta=pos_data["theta"],
                    vega=pos_data["vega"],
                    gamma=pos_data["gamma"],
                    iv=pos_data["iv"],
                    unrealized_pnl=pos_data["unrealized_pnl"],
                    unrealized_pnl_pct=pos_data["unrealized_pnl_pct"],
                    last_updated=datetime.fromisoformat(pos_data["last_updated"]),
                    status=pos_data["status"]
                )
                self.positions[pid] = position
            
            logger.info(f"Loaded {len(self.positions)} positions from {self.positions_file}")
            
        except FileNotFoundError:
            logger.info(f"No existing positions file found at {self.positions_file}")
        except Exception as e:
            logger.error(f"Error loading positions: {e}")

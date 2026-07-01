"""
EMA-CCI-MACD Configuration
============================
Dataclass for per-ticker strategy configuration + YAML loader.

Each instrument gets its own EMA layer triplet, CCI period, MACD params,
and proximity threshold. These are loaded from config/ema_cci_macd.yaml
and can be recalibrated quarterly without code changes.
"""

import os
import yaml
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Project root (tastywork-trading-1/)
ROOT = Path(__file__).parent.parent.parent


@dataclass
class InstrumentConfig:
    """Configuration for a single instrument in the watchlist."""
    symbol: str
    timeframe: str = "1d"               # "1m","5m","15m","1h","1d"
    ema_layers: List[int] = field(default_factory=lambda: [40, 120, 350])
    cci_period: int = 20
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    proximity_pct: float = 0.003        # 0.3% — price must be within this of EMA
    cci_lookback: int = 10              # Bars to look back for CCI extreme before crossover


@dataclass
class SchedulerConfig:
    """Scheduler timing configuration."""
    interval_minutes: int = 15


@dataclass
class AlertConfig:
    """Alert dispatch configuration."""
    telegram: bool = False
    discord: bool = False
    trademind_api: bool = True
    trademind_endpoint: str = "https://www.trademind.bot/api/signals/notify"


@dataclass
class EngineConfig:
    """Top-level engine configuration."""
    watchlist: List[InstrumentConfig] = field(default_factory=list)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)

    @classmethod
    def from_yaml(cls, path: Optional[str] = None) -> "EngineConfig":
        """Load configuration from YAML file."""
        if path is None:
            path = str(ROOT / "config" / "ema_cci_macd.yaml")

        if not os.path.exists(path):
            logger.warning(f"Config file not found: {path}. Using defaults.")
            return cls(watchlist=[
                InstrumentConfig(symbol="QQQ", timeframe="1d",
                                 ema_layers=[40, 120, 350]),
            ])

        with open(path, "r") as f:
            raw = yaml.safe_load(f)

        # Parse watchlist
        watchlist = []
        for item in raw.get("watchlist", []):
            watchlist.append(InstrumentConfig(**item))

        # Parse scheduler
        sched_raw = raw.get("scheduler", {})
        scheduler = SchedulerConfig(**sched_raw)

        # Parse alerts
        alert_raw = raw.get("alerts", {})
        alerts = AlertConfig(**{k: v for k, v in alert_raw.items()
                                if k in AlertConfig.__dataclass_fields__})

        return cls(watchlist=watchlist, scheduler=scheduler, alerts=alerts)

    @classmethod
    def default_qqq(cls) -> "EngineConfig":
        """Quick default config for QQQ backtesting."""
        return cls(watchlist=[
            InstrumentConfig(
                symbol="QQQ",
                timeframe="1d",
                ema_layers=[40, 120, 350],
                cci_period=20,
                proximity_pct=0.003,
                cci_lookback=10,
            ),
        ])

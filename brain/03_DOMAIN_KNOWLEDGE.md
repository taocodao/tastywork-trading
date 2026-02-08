# Domain Knowledge - Options Trading

## Options Basics

### Put Options
- **Cash-Secured Put (CSP)**: Sell a put option while holding enough cash to buy shares if assigned
- **Delta**: Probability of option being in-the-money at expiration (0.20 = 20% chance)
- **Theta**: Time decay - how much option loses per day
- **DTE (Days to Expiration)**: Time remaining until option expires

### Calendar Spreads
- **Definition**: Sell near-term option, buy longer-term option at same strike
- **Profit from**: Time decay differential (near-term decays faster)
- **Best conditions**: Low implied volatility with expected increase

## THETA_UNIVERSE

The system trades only highly liquid ETFs:
```python
THETA_UNIVERSE = [
    # Large Cap ETFs
    "SPY", "QQQ", "IWM", "DIA",
    # Bonds
    "TLT", "IEF", "LQD", "HYG", "SHY", "AGG",
    # Commodities
    "GLD", "SLV", "USO", "UNG", "DBC", "PDBC",
    # Sectors
    "XLV", "XLK", "XLF", "XLI", "XLY", "XLE", "XLRE", "XLU", "XLP", "XLB",
    # Volatility
    "VXX", "UVXY",
    # International
    "EEM", "FXI", "EWJ", "EWG", "EWZ", "EWU",
]
```

**Why ETFs only?**
- No earnings risk
- High liquidity
- Tight bid-ask spreads
- Lower assignment risk

## External APIs

### Interactive Brokers Gateway
- **Purpose**: Market data, Greeks, option chains
- **Port**: 4004 (Docker container)
- **Client ID 3000**: Data client
- **Client ID 3001**: Order client
- **Library**: `ib_insync`

### Tastytrade API
- **Purpose**: Order execution (production)
- **Auth**: OAuth 2.0
- **Endpoints**:
  - `/accounts/{id}/orders` - Place orders
  - `/accounts/{id}/positions` - Get positions
- **Library**: `tastytrade` (official Python SDK)

### WebSocket
- **Purpose**: Real-time signal delivery to frontend
- **Port**: 8003
- **Channels**: `theta_entry`, `theta_exit`, `calendar_spread`

## Risk Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| ACCOUNT_SIZE | $50,000 | Max portfolio value |
| THETA_MAX_POSITIONS | 6 | Max concurrent positions |
| THETA_MAX_PORTFOLIO_HEAT | $50,000 | Max capital at risk |
| THETA_TARGET_DELTA | 0.25 | Target put delta |
| THETA_DTE_MIN | 30 | Minimum days to expiry |
| THETA_DTE_MAX | 45 | Maximum days to expiry |
| THETA_MIN_PREMIUM | $1.00 | Minimum premium to collect |

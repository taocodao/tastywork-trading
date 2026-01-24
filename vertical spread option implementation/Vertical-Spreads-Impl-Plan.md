# LEGAL & COMPLIANCE ANALYSIS + VERTICAL SPREADS IMPLEMENTATION PLAN
## AI Calendar Spread System → Tastytrade Platform

**Date:** January 19, 2026  
**Prepared For:** Antigravity Development Team  
**Status:** READY FOR DEVELOPMENT

---

## PART 1: LEGAL & COMPLIANCE CONCERNS

### Executive Summary
✅ **GOOD NEWS:** Operating an algorithmic options trading platform on Tastytrade is **LEGAL** but comes with **specific obligations** you MUST follow.

⚠️ **CRITICAL:** The system operates as a **third-party integrator** under Tastytrade's API Terms of Service. This creates distinct liability and compliance requirements.

---

## 1. REGULATORY FRAMEWORK

### A. Who Regulates You?

**Primary Regulators:**
1. **SEC** (Securities & Exchange Commission)
   - Rules: Market Access Rule, Regulation SHO, Regulation NMS
   - Concern: Algorithmic trading systems

2. **FINRA** (Financial Industry Regulatory Authority)
   - Rule 3110: Supervision of algorithmic trading strategies
   - Rule 3120: Supervision
   - Rule 5210: Publication of transactions
   - Concern: AI/ML governance, testing, supervisory controls

3. **CBOE & Exchanges**
   - Order routing, circuit breakers, market manipulation

4. **Tastytrade Inc.** (Your Broker)
   - API Terms & Conditions (legally binding)
   - Customer Agreement
   - Internal compliance rules

**Key Point:** You don't need a broker-dealer license **IF:**
- ✅ You trade ONLY for your own clients (not proprietary)
- ✅ You use Tastytrade's platform (not your own)
- ✅ Tastytrade executes ALL orders (not you)
- ✅ You comply with Tastytrade's API Terms

**If you violate this:**
- ❌ Potential SEC prosecution for unregistered brokerage activity
- ❌ Fines up to $250,000+ per violation
- ❌ Criminal charges for market manipulation

---

### B. Algorithmic Trading Regulations (SEC/FINRA)

**FINRA Rule 3110 - Algorithmic Trading Supervision:**

From webinar & regulatory docs, your system must have:

```
1. Policies & Procedures Document
   ├─ Written desc. of strategy logic
   ├─ Risk limits & controls
   ├─ Testing methodology
   ├─ Monitoring procedures
   └─ Escalation protocols

2. Testing & Validation
   ├─ Backtesting (historical data)
   ├─ Forward testing (simulated trading)
   ├─ Paper trading (live data, no real $)
   └─ Pre-production stress testing

3. Supervisory Controls
   ├─ Daily position monitoring
   ├─ Order-level logging (all trades)
   ├─ Anomaly detection (unusual behavior)
   ├─ Circuit breakers (auto-kill if margin breach)
   └─ Human override capability

4. Record Keeping (2-7 years)
   ├─ All signals generated
   ├─ All orders placed
   ├─ All fills received
   ├─ Reasoning for each trade
   └─ ML model versions & changes
```

**FINRA Guidance on AI/ML (2024):**

From FINRA Regulatory Notice 24-09:
> "If your firm uses AI to make trading decisions, regulators expect the same governance you'd apply to a registered representative. The algorithm is NOW PART OF YOUR SUPERVISORY CHAIN and will be examined as such."

**Translation:** Your ML models must:
- ✅ Be documented & validated
- ✅ Have audit trails showing reasoning
- ✅ Be tested before production
- ✅ Have clear model versions & change logs
- ✅ Have human override capability
- ✅ Have explainability (why did model choose this stock?)

---

### C. Tastytrade API Terms & Conditions (Critical)

**You are a "Third-Party Integrator" under their Terms.**

#### Key Obligations (From Tastytrade API T&Cs):

**1. LIABILITY DISCLAIMER (Tastytrde Takes NO Responsibility)**
```
"The API Connection is provided 'AS IS' at your SOLE RISK"
"We disclaim any warranty, merchantability, fitness for purpose"
"We have NO liability for delays, defects, failures"
"We have NO liability for any Loss arising from your system, 
  third-party systems, the internet, or any limits we set"
```

**Translation:** If YOUR system causes trading losses, Tastytrade is NOT liable. YOU are.

**2. YOUR INDEMNITY (You Pay Tastytrade's Legal Costs)**
```
Section 5: "You shall indemnify TASTYTRADE, INC. and its 
Associated Companies... from any Losses resulting from:

(a) Your breach of this Agreement
(b) Your software or applications (including end users' use)
(c) Your or your client's use or misuse of the API
(d) Any person using your system via your credentials"
```

**Translation:** If a user sues Tastytrade claiming your AI caused losses, you pay their legal fees + damages.

**3. API MONITORING (Tastytrade Can Access Your Trades)**
```
"You acknowledge and consent to us monitoring and recording 
your access to the API Connection... This may include accessing 
and using your API Transactions to identify security issues... 
and you will not interfere with this monitoring."
```

**Translation:** Tastytrade can see every trade your system places, when, why (to some extent).

**4. IMMEDIATE TERMINATION RIGHTS (Tastytrade Can Kill Access Anytime)**
```
"We may terminate this Agreement immediately upon notice if we 
deem in our sole discretion that actions or use of the API in any 
way whatsoever by any third-party integrator creates any 
regulatory or reputational risk to TASTYTRADE, INC."
```

**Translation:** If your system is seen as risky → Tastytrade cuts you off. No warning, no recourse.

**5. DATA RESTRICTIONS (Can't Store Customer Data)**
```
"A third-party integrator must clearly disclose to any customers 
if any data including trade, position, financial or Client 
information is extracted, obtained, or pulled from the APIs and 
stored on their systems for any reason."

"Third party integrator must not redistribute quotes or Data to 
non-TASTYTRADE clients."
```

**Translation:**
- ✅ You CAN store customer trades for audit/risk purposes
- ❌ You CANNOT store their data on your servers without explicit consent
- ❌ You CANNOT use that data for anything other than trading
- ❌ You CANNOT sell/share data with other brokers

**6. CREDENTIAL SECURITY (OAuth Required)**
```
"No third-party integrator shall be permitted to store TASTYTRADE 
customer or client credentials directly on their systems... it must 
utilize TASTYTRADE mechanisms for logging in to the APIs."
```

**Translation:**
- ✅ Use OAuth or Tastytrade's approved auth method
- ❌ NEVER store username/password on your servers
- ❌ Risk: Account compromise → You're liable

**7. SOFTWARE MALFUNCTION LIABILITY (Yours Alone)**
```
"It is the sole responsibility of any third-party integrator for 
errant order instructions sent as a result of software malfunction 
and we shall have no liability with respect to such errors."
```

**Translation:** If your code has a bug that sends 1,000 orders instead of 10, YOU pay for it. Not Tastytrade.

---

## 2. SPECIFIC LEGAL CONCERNS FOR VERTICAL SPREADS

### A. Market Manipulation Risk

**SEC Rule: Regulation SHO, Rule 10b-5**

Concern: Could your AI system be accused of market manipulation?

**Red Flags:**
- ❌ Trading in "pump & dump" pattern (coordinated buys to pump price)
- ❌ Using spoofing (placing orders you don't intend to fill)
- ❌ Quote stuffing (overwhelming market with orders to manipulate)
- ❌ Layering (placing orders to create false appearance of volume)

**Your System:**
- ✅ Places ONE order per signal
- ✅ Follows buy/sell logic (no spoofing)
- ✅ Uses defined-risk spreads (not unlimited risk)
- ✅ Small position size per trade
- ✅ Cancels unfilled orders after reasonable time

**Mitigation:**
```
Document that your strategy:
├─ Is NOT intended to manipulate price
├─ Uses standard technical analysis (RSI, etc.)
├─ Has defined risk management
├─ Follows all exchange rules
├─ Is designed for market participants (income/hedging)
└─ Has human oversight capability
```

---

### B. Suitability & Sales Practice Concerns

**FINRA Rule 3111: Suitability**

Concern: Is vertical spreads an appropriate recommendation?

**Your Obligations:**
1. Understand customer's financial situation
2. Understand vertical spread characteristics
3. Ensure recommendation is suitable

**Example Problem:**
```
Customer: $500 account, beginner, risk-averse
Your system recommends: 100-contract vertical spread
Problem: UNSUITABLE - Customer can't afford max loss, 
doesn't understand spreads, too risky
```

**Mitigation:**
```
✅ Implement account-level suitability checks:
  ├─ Min account size: $2,000
  ├─ Max contracts: Account size ÷ $1,000 per spread
  ├─ Max daily risk: 1% of account
  └─ Customer education requirement

✅ Require customer acknowledgment:
  "I understand vertical spreads can result in max loss.
   I have $X account and can lose $Y if stock goes against me."

✅ Provide educational material:
  "Vertical Spreads 101" PDF before first trade
```

---

### C. Options Level Approval

**FINRA & Tastytrade Rule: Options Approval Required**

Your customers MUST have options approval.

**Account Levels:**
```
Level 0: No options
Level 1: Covered calls + cash-secured puts (SIMPLE)
Level 2: Spreads & straddles (MODERATE)
Level 3: All spreads including cash-secured puts (ADVANCED)
Level 4: Naked calls & puts (PROFESSIONAL)
```

**Your System Requires: Level 2 or 3 minimum**

**Check in Code:**
```python
def validate_account_suitability(customer_id):
    """Verify customer has options approval before trading"""
    customer = get_customer_profile(customer_id)
    
    if customer.options_level < 2:
        return False, "Customer not approved for spreads"
    if customer.account_balance < 2000:
        return False, "Minimum $2,000 required"
    if customer.is_pattern_day_trader and account_size < 25000:
        return False, "PDT restriction applies"
    
    return True, "Suitability check passed"
```

---

### D. Disclosure & Marketing Concerns

**FINRA Rule 5130: General Communications Rule**

If you're advertising or marketing your system:
- ✅ Must be TRUE
- ✅ Must not be MISLEADING
- ✅ Must include RISK DISCLAIMERS
- ✅ Must not GUARANTEE RETURNS

**Example Good Disclosure:**
```
"Our AI system trades vertical spreads on stocks.
Past performance: 72% win rate over 3 years.
Not indicative of future results.
Maximum loss per trade: Limited to spread width.
Risk: All capital can be lost. Options trading is risky.
Not suitable for all investors."
```

**Example Bad Disclosure:**
```
"Our AI system GUARANTEED 30% monthly returns!"
[ILLEGAL - SEC will prosecute]
```

---

### E. Know-Your-Customer (KYC) & Anti-Money Laundering (AML)

**SEC Rule: Regulation 3310**

You are NOT responsible for KYC/AML (Tastytrade handles this).

**BUT:** You must report suspicious activity:
```python
def check_suspicious_activity(customer_id, trade_data):
    """Flag unusual patterns"""
    if trade_data.volume > 10000 and customer.account_age < 7_days:
        report_to_tastytrade("New account, large trades")
    
    if trade_data.amount > $500k and customer_id in_sanctioned_list():
        report_to_tastytrade("Possible sanctions violation")
    
    if pattern_looks_like_money_laundering(trade_data):
        report_to_tastytrade("Possible AML violation")
```

---

## 3. SPECIFIC LEGAL OBLIGATIONS

### What You MUST Do:

#### ✅ MANDATORY (Legal Requirements)

1. **Document Your Strategy**
   - File: `STRATEGY_DOCUMENTATION.md`
   - Contents: How vertical spreads work, when your system enters/exits, risk management
   - Audience: Regulators, Tastytrade, customers
   - Review: Annual (or after changes)

2. **Maintain Audit Trail**
   - Log EVERY signal (date, time, stock, confidence score, reason)
   - Log EVERY order (symbol, strike, expiration, quantity, price)
   - Log EVERY fill (actual price, fees)
   - Store: Min 7 years (securities) or 2 years (compliance)
   - Database: Can't be tampered with (immutable log)

3. **Implement Circuit Breakers**
   - Max daily loss: 5% of account
   - Max position size: 2% of account per trade
   - Max contracts: 10 contracts unless account >$50k
   - Time-based: No trading first/last 5 min of market day
   - Auto-kill on system error

4. **Supervisory Controls**
   - Daily review of trades placed
   - Weekly win-rate & loss tracking
   - Monthly customer satisfaction survey
   - Quarterly regulatory compliance review
   - Alert when models change

5. **Customer Education**
   - Provide: "Vertical Spreads Explained" PDF (before first trade)
   - Include: Risk/reward diagrams, profit/loss graphs
   - Require: Customer attestation "I understand this strategy"
   - Update: Annually or when strategy changes

6. **Compliance Testing**
   - Unit tests: Strategy logic (entry/exit signals)
   - Integration tests: Order placement to Tastytrade
   - Stress tests: High volatility scenarios
   - Regression tests: After any code changes
   - Run: Before deploying to production

7. **Tastytrade Compliance**
   - Don't store customer credentials on your servers
   - Use OAuth for authentication
   - Disclose data collection/storage practices
   - Implement rate limiting (don't hammer API)
   - Maintain API audit trail (Tastytrade monitors you)

---

### ✅ RECOMMENDED (Best Practices)

1. **Get E&O Insurance**
   - Coverage: $1M-5M errors & omissions
   - Includes: Trading losses from system errors
   - Cost: ~$3,000-10,000/year
   - Required if you scale to many customers

2. **Hire Compliance Officer**
   - Responsibility: Ensure all rules followed
   - Qualifications: FINRA background preferred
   - Part-time: Can be consultant
   - Cost: ~$5,000-15,000/year

3. **Write Terms of Service**
   - Legal doc describing what your service does
   - Includes: Risk disclaimers, liability limits
   - Should cover: Data use, customer obligations, termination
   - Have lawyer review (~$2,000-5,000)

4. **Create Risk Disclosure**
   - Document: Specific risks of vertical spreads
   - Include: Historical win rates, max losses, volatility sensitivity
   - Example loss scenario: "$5,000 account, max loss per trade: $50-100"
   - Update: Quarterly with real results

5. **Implement Conflict-of-Interest Policy**
   - Your interests vs customer interests
   - Example: Do you trade the same stocks? (Disclose)
   - Process: How you handle conflicts

---

## 4. TASTYTRADE-SPECIFIC REQUIREMENTS

### Exhibit A: Data Use Disclosure

**You MUST complete Exhibit A of Tastytrade API Terms:**

```
1. The scope of information your app will display to customers:
   ✓ Real-time stock prices
   ✓ Options chains (calls/puts available)
   ✓ Implied volatility
   ✓ Greeks (delta, gamma, theta)
   ✓ Customer's open positions
   ✓ Customer's account balance & buying power
   ✓ Order confirmation & execution prices

2. What information you will STORE on your systems:
   ✓ Customer's trading history (for audit/risk)
   ✓ System signals generated (for compliance)
   ✓ Order placement timestamps (for audit)
   ✗ Customer credentials (NEVER)
   ✗ Customer social security numbers
   ✗ Customer banking information
   ✗ Customer personal financial data (beyond trading)

3. How you will DISCLOSE this to customers:
   In your Terms of Service:
   "Our system accesses your Tastytrade account to place trades
    and monitor positions. We store your trading history for
    compliance and risk management. We DO NOT store your
    passwords, social security numbers, or other sensitive info.
    Data is retained for 7 years for audit purposes."
```

---

## 5. INCIDENT RESPONSE PLAN

**If Something Goes Wrong:**

### Scenario A: System Places 1,000 Orders Instead of 10 (Software Bug)

```
IMMEDIATE (Within 1 hour):
1. Kill the system (circuit breaker triggers automatically)
2. Notify Tastytrade support (call 1-888-679-8273)
3. Document the error (timestamp, orders placed, reason)
4. Cancel unfilled orders (call Tastytrade)

WITHIN 24 HOURS:
5. Contact all affected customers
6. Calculate losses
7. Prepare incident report

WITHIN 72 HOURS:
8. Submit incident report to Tastytrade
9. Fix code & retest thoroughly
10. Notify customers of fix & timeline to restart

LEGAL:
11. Contact E&O insurance (claim notification)
12. Consider reaching out to lawyer for advice
```

### Scenario B: Customer Loses More Than Max Loss (System Error)

```
IMMEDIATE:
1. Verify the loss is real (check Tastytrade account)
2. Determine if it was customer error or system error

IF SYSTEM ERROR:
3. Document the error
4. Consider partial refund from E&O insurance
5. Notify customer within 24 hours

IF CUSTOMER ERROR:
3. Provide detailed explanation of what happened
4. Educate customer on suitability/risk
```

### Scenario C: Tastytrade Terminates Your API Access

```
"We deem your system creates regulatory risk"

IMMEDIATE:
1. All trading stops automatically
2. Notify all customers (email + phone calls)
3. Don't panic (not necessarily criminal)

INVESTIGATION:
4. Contact Tastytrade to understand why
5. Review your last 30 days of trades
6. Look for patterns that might look suspicious

RESOLUTION:
7. Submit remediation plan to Tastytrade
8. May need to:
   - Add manual oversight for all trades
   - Reduce trade frequency
   - Get compliance officer involved
   - Possibly suspend service temporarily
```

---

## 6. COMPLIANCE CHECKLIST

### Before You Launch Vertical Spreads:

```
□ Strategy Documentation
  □ Written description of vertical spread strategy
  □ Entry criteria (RSI levels, ML confidence scores)
  □ Exit criteria (profit target, stop loss, time-based)
  □ Risk management rules (max loss, max position size)
  □ Historical backtest results (3+ years)
  □ Forward test results (30+ days)
  □ Paper trading results (14+ days)

□ Code & Testing
  □ Unit tests for entry/exit signals (>90% pass rate)
  □ Integration tests with Tastytrade (manual validation)
  □ Stress tests (volatility scenarios, halts, gaps)
  □ Error handling (what happens if Tastytrade is down?)
  □ Order cancellation logic (unfilled orders after X minutes)
  □ Circuit breaker (daily loss limit, position size limit)
  □ Rate limiting (don't hammer API more than 1 req/sec)

□ Risk Management
  □ Max daily loss: 5% of account
  □ Max position size: 2% of account
  □ Max contracts per trade: Account size dependent
  □ No trading first 5 min or last 5 min of day
  □ No trading around earnings (optional but recommended)
  □ No trading stocks <$5 (penny stocks)
  □ No trading stocks with <$50M market cap

□ Customer Communications
  □ Terms of Service (with risk disclaimers)
  □ Risk Disclosure document
  □ "Vertical Spreads 101" educational material
  □ Customer suitability agreement (attestation)
  □ Data use disclosure (Exhibit A to Tastytrade)
  □ Monthly statement showing trades + performance
  □ Email confirmation of each trade (within 2 hours)

□ Compliance Infrastructure
  □ Audit trail logging (immutable, 7-year retention)
  □ Daily trade review checklist (signed by compliance)
  □ Weekly win rate & loss tracking
  □ Monthly customer satisfaction survey
  □ Quarterly regulatory review
  □ Annual strategy review & update

□ Tastytrade Requirements
  □ Completed Exhibit A (data use declaration)
  □ OAuth authentication (no stored credentials)
  □ API usage monitoring (accept Tastytrade monitoring)
  □ Indemnity insurance ($1M+ E&O coverage)
  □ Rate limiting (comply with throttle limits)
  □ No credential storage on your servers

□ Legal/Insurance
  □ E&O insurance policy ($1M minimum)
  □ Terms of Service reviewed by lawyer
  □ Privacy policy (how you handle customer data)
  □ Incident response plan (what if something breaks?)
  □ Conflict-of-interest policy

□ Regulatory Readiness
  □ Ready to produce strategy documentation on demand
  □ Ready to produce audit trail (7 years)
  □ Ready to explain model decisions (explainability)
  □ Ready to provide historical backtest
  □ Ready to demonstrate circuit breaker functionality
  □ Ready to show customer suitability process
```

---

---

# PART 2: VERTICAL SPREADS IMPLEMENTATION PLAN

## OVERVIEW

This plan converts your existing calendar spread ML system to generate **Vertical Spread signals** alongside calendar spreads.

### Key Differences (Calendar vs Vertical)

```
CALENDAR SPREAD:
├─ Same strike (ATM or slightly OTM)
├─ Different expirations (short-term + long-term)
├─ Theta decay + IV crush = profit
├─ Risk: IV spike, stock moves hard against
├─ Entry: 30-45 DTE (days to expiration)
└─ Duration: 14-30 days

VERTICAL SPREAD:
├─ Different strikes (directional bias)
├─ Same expiration (both short-term)
├─ Directional move + theta decay = profit
├─ Risk: Stock moves against position
├─ Entry: 7-21 DTE (closer to expiration)
└─ Duration: 7-14 days

ML MODEL CHANGE:
Calendar: "Is this a good IV environment for theta decay?"
Vertical: "Is this stock going UP or DOWN in next 7-14 days?"
```

---

## ARCHITECTURE

### Component Additions

```
EXISTING SYSTEM:
├─ Market data feed (stock prices, options chains)
├─ ML signal generator (calendar spreads)
├─ Risk manager (portfolio tracking, stops)
├─ Order executor (Tastytrade API)
└─ Dashboard (performance tracking)

NEW COMPONENTS:
├─ Direction predictor ML model (UP/DOWN prediction)
├─ Vertical spread selector (pick strikes based on risk)
├─ Options chain analyzer (implied move estimation)
└─ Suitability validator (account size, options level)
```

### Data Flow

```
INPUT: Real-time stock data
  ↓
STEP 1: Filter stocks (volume, price, liquidity)
  ↓
STEP 2: Calculate directional signal
  ├─ RSI (oversold = buy, overbought = sell)
  ├─ ML model (pattern recognition + ensemble voting)
  ├─ Technical (moving averages, trend strength)
  └─ Output: Direction (BULL, BEAR, NEUTRAL) + Confidence (0-100)
  ↓
STEP 3: If signal > 60 confidence:
  ├─ Get options chain (calls and puts available)
  ├─ Identify strikes for vertical spread
  ├─ Calculate max profit & max loss
  ├─ Validate suitability (account size, options level)
  └─ Output: Trade recommendation
  ↓
STEP 4: Execute or hold
  ├─ If confidence > 75: Auto-execute (with customer approval)
  ├─ If 60-75: Alert customer for approval
  └─ If <60: Skip
  ↓
OUTPUT: Order to Tastytrade API
```

---

## DETAILED IMPLEMENTATION

### Phase 1: ML Model for Directional Prediction

#### 1.1 Data Requirements

```python
# Need to collect for each stock:
stock_data = {
    "symbol": "AAPL",
    "timestamp": "2026-01-19 10:30:00",
    "price": 150.25,
    "rsi_14": 45.2,           # Relative Strength Index
    "bb_upper": 155.0,         # Bollinger Band upper
    "bb_lower": 145.0,         # Bollinger Band lower
    "bb_mid": 150.0,           # Bollinger Band middle
    "sma_20": 149.5,           # 20-day moving average
    "sma_50": 148.0,           # 50-day moving average
    "sma_200": 147.0,          # 200-day moving average
    "atr_14": 1.5,             # Average True Range
    "volume": 50_000_000,      # Share volume
    "iv": 0.28,                # Implied volatility
    "vwap": 150.1,             # Volume-weighted avg price
    
    # Options Greeks (for 30 DTE ATM calls)
    "atm_iv": 0.28,
    "atm_delta": 0.50,
    "atm_gamma": 0.015,
    "atm_theta": -0.02,
    "atm_vega": 0.08,
}
```

#### 1.2 ML Model Architecture

**Option A: Ensemble Voting (Recommended for Phase 1)**

```python
class VerticalSpreadDirectionPredictor:
    """
    Predicts directional bias for vertical spreads
    Combines multiple indicators for robustness
    """
    
    def __init__(self):
        self.rsi_threshold_oversold = 30
        self.rsi_threshold_overbought = 70
        self.atr_multiplier = 1.5
        
    def calculate_direction_signal(self, stock_data):
        """
        Returns: {
            "direction": "BULL" | "BEAR" | "NEUTRAL",
            "confidence": 0-100,
            "indicators": {...},
            "reasoning": "..."
        }
        """
        
        signals = []
        
        # Signal 1: RSI Mean Reversion
        rsi_signal = self._rsi_signal(stock_data["rsi_14"])
        signals.append({
            "name": "RSI",
            "vote": rsi_signal,  # 1=BULL, 0=NEUTRAL, -1=BEAR
            "confidence": self._rsi_confidence(stock_data["rsi_14"])
        })
        
        # Signal 2: Bollinger Bands
        bb_signal = self._bollinger_signal(
            stock_data["price"],
            stock_data["bb_upper"],
            stock_data["bb_mid"],
            stock_data["bb_lower"]
        )
        signals.append({
            "name": "Bollinger Bands",
            "vote": bb_signal,
            "confidence": self._bb_confidence(stock_data["price"], 
                                              stock_data["bb_upper"],
                                              stock_data["bb_lower"])
        })
        
        # Signal 3: Moving Average Crossover
        ma_signal = self._ma_signal(
            stock_data["price"],
            stock_data["sma_20"],
            stock_data["sma_50"],
            stock_data["sma_200"]
        )
        signals.append({
            "name": "Moving Averages",
            "vote": ma_signal,
            "confidence": self._ma_confidence(stock_data["price"],
                                              stock_data["sma_20"],
                                              stock_data["sma_50"])
        })
        
        # Signal 4: Volatility Expansion (ATR)
        vol_signal = self._volatility_signal(
            stock_data["atr_14"],
            stock_data["price"]
        )
        signals.append({
            "name": "Volatility (ATR)",
            "vote": vol_signal,
            "confidence": 50  # Neutral on direction, just informs risk
        })
        
        # Ensemble Vote
        direction, confidence = self._ensemble_vote(signals)
        
        return {
            "direction": direction,
            "confidence": confidence,
            "indicators": signals,
            "reasoning": self._explain_decision(signals, direction)
        }
    
    def _rsi_signal(self, rsi):
        """RSI mean reversion"""
        if rsi < self.rsi_threshold_oversold:
            return 1  # BULL (oversold, expect bounce)
        elif rsi > self.rsi_threshold_overbought:
            return -1  # BEAR (overbought, expect pullback)
        else:
            return 0  # NEUTRAL
    
    def _rsi_confidence(self, rsi):
        """Stronger signal if more extreme"""
        if rsi < 20:
            return 85  # Very oversold
        elif rsi < 30:
            return 70  # Oversold
        elif rsi > 80:
            return 85  # Very overbought
        elif rsi > 70:
            return 70  # Overbought
        else:
            return 40  # Moderate
    
    def _bollinger_signal(self, price, bb_upper, bb_mid, bb_lower):
        """Mean reversion: price near extremes tend to revert"""
        price_position = (price - bb_lower) / (bb_upper - bb_lower)
        
        if price_position > 0.9:  # Near upper band
            return -1  # BEAR (mean reversion down)
        elif price_position < 0.1:  # Near lower band
            return 1  # BULL (mean reversion up)
        else:
            return 0  # NEUTRAL
    
    def _bb_confidence(self, price, bb_upper, bb_lower):
        """Strength based on proximity to bands"""
        bb_range = bb_upper - bb_lower
        distance_to_edge = min(
            abs(price - bb_upper),
            abs(price - bb_lower)
        )
        
        # Closer to edge = higher confidence in mean reversion
        confidence = 100 * (1 - distance_to_edge / bb_range)
        return max(30, min(90, confidence))
    
    def _ma_signal(self, price, sma_20, sma_50, sma_200):
        """Trend following"""
        if price > sma_20 > sma_50 > sma_200:
            return 1  # BULL (all MAs aligned up)
        elif price < sma_20 < sma_50 < sma_200:
            return -1  # BEAR (all MAs aligned down)
        elif sma_20 > sma_50:
            return 0.5  # Mild BULL
        elif sma_20 < sma_50:
            return -0.5  # Mild BEAR
        else:
            return 0  # NEUTRAL
    
    def _ma_confidence(self, price, sma_20, sma_50):
        """Strength of trend"""
        distance = abs(price - sma_20)
        if distance > sma_20 * 0.05:  # >5% away from 20-MA
            return 75
        elif distance > sma_20 * 0.02:  # >2% away
            return 60
        else:
            return 40
    
    def _volatility_signal(self, atr, price):
        """ATR doesn't give direction, just notes vol expansion"""
        atr_pct = atr / price
        if atr_pct > 0.03:  # >3% ATR = elevated
            return 0  # Neutral on direction
        else:
            return 0
    
    def _ensemble_vote(self, signals):
        """Combine all signals"""
        total_weight = 0
        total_vote = 0
        
        for signal in signals:
            weight = signal["confidence"]
            vote = signal["vote"]
            
            total_weight += weight
            total_vote += vote * weight
        
        avg_vote = total_vote / total_weight if total_weight > 0 else 0
        
        # Map to direction
        if avg_vote > 0.3:
            direction = "BULL"
        elif avg_vote < -0.3:
            direction = "BEAR"
        else:
            direction = "NEUTRAL"
        
        # Confidence is % weight of dominant signals
        confidence = int(abs(avg_vote) * 100)
        
        return direction, confidence
    
    def _explain_decision(self, signals, direction):
        """Create human-readable explanation"""
        bullish = [s for s in signals if s["vote"] > 0]
        bearish = [s for s in signals if s["vote"] < 0]
        
        explanation = f"Direction: {direction}\n"
        explanation += f"Bullish signals ({len(bullish)}): "
        explanation += ", ".join([s["name"] for s in bullish]) + "\n"
        explanation += f"Bearish signals ({len(bearish)}): "
        explanation += ", ".join([s["name"] for s in bearish])
        
        return explanation
```

---

### Phase 2: Vertical Spread Selection

#### 2.1 Strike Selection Logic

```python
class VerticalSpreadSelector:
    """
    Given a directional signal, selects appropriate strikes
    for a vertical spread based on:
    - Directional confidence
    - Account size & risk tolerance
    - Implied move (how much stock expected to move)
    - Historical support/resistance
    """
    
    def __init__(self):
        self.max_loss_percent = 0.02  # Max loss = 2% of account
        self.max_width_per_spread = 5  # Standard $5 wide spreads
    
    def select_spread(self, stock_data, direction_signal, account_data):
        """
        Returns optimal vertical spread strikes
        
        Example output (BULL):
        {
            "symbol": "AAPL",
            "strategy": "CALL_DEBIT_SPREAD",
            "buy_strike": 150,
            "sell_strike": 155,
            "expiration": "2026-02-15",
            "bid_ask_mid": 2.50,
            "max_profit": 250,    # per contract
            "max_loss": 250,      # per contract
            "contracts": 2,       # based on account size
            "probability_of_profit": 0.65,
            "total_capital_at_risk": 500  # max loss
        }
        """
        
        symbol = stock_data["symbol"]
        price = stock_data["price"]
        direction = direction_signal["direction"]
        confidence = direction_signal["confidence"]
        
        # Step 1: Get options chain
        options_chain = self._get_options_chain(symbol)
        
        # Step 2: Select expiration (7-21 DTE)
        expiration = self._select_expiration(options_chain)
        
        # Step 3: Select strikes based on direction
        if direction == "BULL":
            spread = self._select_bull_call_spread(
                symbol, price, options_chain, expiration, confidence, account_data
            )
        elif direction == "BEAR":
            spread = self._select_bear_call_spread(
                symbol, price, options_chain, expiration, confidence, account_data
            )
        else:
            return None  # Skip if neutral
        
        return spread
    
    def _get_options_chain(self, symbol):
        """Fetch available options from Tastytrade"""
        # Returns: [
        #   {"strike": 150, "call_bid": 3.50, "call_ask": 3.70, ...},
        #   {"strike": 155, "call_bid": 2.00, "call_ask": 2.20, ...},
        # ]
        pass
    
    def _select_expiration(self, options_chain):
        """Pick expiration 7-21 DTE"""
        available_exp = options_chain["expirations"]
        # Filter to 7-21 DTE
        suitable_exp = [e for e in available_exp if 7 <= e["dte"] <= 21]
        # Prefer 14 DTE
        return suitable_exp[0] if suitable_exp else available_exp[0]
    
    def _select_bull_call_spread(self, symbol, price, options_chain, 
                                  expiration, confidence, account_data):
        """
        Bull call spread: Long ITM call, Short OTM call
        Profit if stock goes UP
        
        Risk/Reward based on confidence:
        - High confidence (75+): Sell farther OTM (lower prob, higher payout)
        - Med confidence (60-75): Sell at balanced strike
        - Low confidence (50-60): Sell closer OTM (higher prob, lower payout)
        """
        
        # Example: AAPL at $150
        # High confidence (80): Buy 150 call, Sell 155 call (wide, risky)
        # Med confidence (70): Buy 150 call, Sell 152.50 call
        # Low confidence (55): Buy 150 call, Sell 150 call (barely wide)
        
        # Calculate strike width based on confidence & IV
        implied_move = self._calculate_implied_move(
            price, options_chain["atm_iv"], expiration["dte"]
        )
        
        if confidence > 75:
            # Aggressive: Sell beyond implied move
            sell_offset = implied_move * 1.2
        elif confidence > 60:
            # Balanced: Sell at implied move
            sell_offset = implied_move * 0.8
        else:
            # Conservative: Sell closer
            sell_offset = implied_move * 0.5
        
        # Round to nearest $0.50 (trading convention)
        sell_strike = self._round_strike(price + sell_offset)
        
        # Buy strike: typically ATM or slightly ITM
        buy_strike = self._round_strike(price)
        
        # Ensure spread is valid
        if sell_strike <= buy_strike:
            sell_strike = buy_strike + self.max_width_per_spread
        
        # Get option prices
        buy_option = self._get_option(symbol, buy_strike, "CALL", expiration)
        sell_option = self._get_option(symbol, sell_strike, "CALL", expiration)
        
        # Calculate P&L
        net_debit = (buy_option["mid"] - sell_option["mid"]) * 100
        max_profit = ((sell_strike - buy_strike) * 100) - net_debit
        max_loss = net_debit
        
        # Calculate contracts based on account
        contracts = self._calculate_contracts(
            max_loss, account_data["balance"], account_data["risk_tolerance"]
        )
        
        return {
            "symbol": symbol,
            "strategy": "CALL_DEBIT_SPREAD",
            "buy_strike": buy_strike,
            "sell_strike": sell_strike,
            "expiration": expiration["date"],
            "dte": expiration["dte"],
            "net_debit": net_debit,
            "max_profit": max_profit,
            "max_loss": max_loss,
            "contracts": contracts,
            "total_at_risk": max_loss * contracts,
            "implied_move": implied_move,
            "confidence": confidence,
        }
    
    def _select_bear_call_spread(self, symbol, price, options_chain,
                                  expiration, confidence, account_data):
        """
        Bear call spread: Sell OTM call, Buy farther OTM call
        Profit if stock goes DOWN (or stays flat)
        
        Alternative: Bear put spread (sell puts)
        """
        # Similar logic to bull call, but inverted
        # ...
        pass
    
    def _calculate_implied_move(self, price, iv, dte):
        """
        Simplified: Implied Move ≈ Price × IV × √(DTE/365)
        
        Example: AAPL $150, IV 0.28, 14 DTE
        Implied Move = 150 × 0.28 × √(14/365) = $5.15
        """
        import math
        implied_move = price * iv * math.sqrt(dte / 365)
        return implied_move
    
    def _round_strike(self, price):
        """Round to nearest $0.50 (SPX) or $1 (most stocks)"""
        if price < 20:
            return round(price * 2) / 2
        elif price < 200:
            return round(price)
        else:
            return round(price / 5) * 5  # $5 increments for high-priced stocks
    
    def _get_option(self, symbol, strike, option_type, expiration):
        """Fetch bid/ask/mid for specific option"""
        # Returns: {"bid": 2.50, "ask": 2.70, "mid": 2.60}
        pass
    
    def _calculate_contracts(self, max_loss_per_contract, account_balance, 
                              risk_tolerance="medium"):
        """
        Determine how many contracts to trade
        
        Risk tolerance:
        - Conservative: 1% max loss per trade
        - Medium: 2% max loss per trade
        - Aggressive: 5% max loss per trade
        """
        
        risk_levels = {
            "conservative": 0.01,
            "medium": 0.02,
            "aggressive": 0.05,
        }
        
        max_risk = account_balance * risk_levels[risk_tolerance]
        contracts = int(max_risk / max_loss_per_contract)
        
        return max(1, min(contracts, 10))  # Min 1, max 10 per trade
```

---

### Phase 3: Integration with Existing System

#### 3.1 Modify Signal Generator

```python
class CombinedSignalGenerator:
    """
    Generates BOTH calendar spread and vertical spread signals
    """
    
    def __init__(self):
        self.calendar_generator = CalendarSpreadGenerator()
        self.vertical_generator = VerticalSpreadDirectionPredictor()
        self.vertical_selector = VerticalSpreadSelector()
    
    def generate_signals(self, stock_data, account_data):
        """
        Returns list of signals (can be calendar or vertical)
        """
        
        signals = []
        
        # Signal 1: Calendar Spread (existing logic)
        calendar_signal = self.calendar_generator.generate(stock_data)
        if calendar_signal and calendar_signal["confidence"] > 60:
            signals.append({
                "type": "CALENDAR_SPREAD",
                "details": calendar_signal,
                "priority": 1,  # Higher priority if both available
            })
        
        # Signal 2: Vertical Spread (new)
        direction_signal = self.vertical_generator.calculate_direction_signal(stock_data)
        
        if direction_signal["confidence"] > 60:
            vertical_spread = self.vertical_selector.select_spread(
                stock_data, direction_signal, account_data
            )
            
            if vertical_spread:
                signals.append({
                    "type": "VERTICAL_SPREAD",
                    "details": vertical_spread,
                    "priority": 2,  # Lower priority than calendar
                })
        
        return signals
```

#### 3.2 Execution Layer (Update)

```python
class OrderExecutor:
    """
    Executes both calendar and vertical spreads to Tastytrade
    """
    
    def execute_signal(self, signal, customer_account):
        """Execute a signal (calendar or vertical)"""
        
        if signal["type"] == "CALENDAR_SPREAD":
            order = self._execute_calendar(signal, customer_account)
        elif signal["type"] == "VERTICAL_SPREAD":
            order = self._execute_vertical(signal, customer_account)
        else:
            raise ValueError(f"Unknown signal type: {signal['type']}")
        
        return order
    
    def _execute_vertical(self, signal, customer_account):
        """Place a vertical spread order to Tastytrade"""
        
        details = signal["details"]
        
        # Build multi-leg order
        legs = [
            {
                "symbol": details["symbol"],
                "type": "BUY" if "CALL_DEBIT" in details["strategy"] else "SELL",
                "strike": details["buy_strike"],
                "option_type": "CALL" if "CALL" in details["strategy"] else "PUT",
                "expiration": details["expiration"],
                "quantity": details["contracts"],
            },
            {
                "symbol": details["symbol"],
                "type": "SELL" if "CALL_DEBIT" in details["strategy"] else "BUY",
                "strike": details["sell_strike"],
                "option_type": "CALL" if "CALL" in details["strategy"] else "PUT",
                "expiration": details["expiration"],
                "quantity": details["contracts"],
            }
        ]
        
        # Submit to Tastytrade
        order = self.tastytrade_client.place_multileg_order(
            account_id=customer_account["id"],
            legs=legs,
            order_type="LIMIT",
            time_in_force="DAY",
            limit_price=details["net_debit"],  # For debit spreads
        )
        
        return order
```

---

### Phase 4: Risk Management & Stops

#### 4.1 Dynamic Stop Loss for Vertical Spreads

```python
class VerticalSpreadStopManager:
    """
    Manages stop losses for vertical spreads
    Different logic than calendar spreads
    """
    
    def __init__(self):
        self.max_loss_percent = 0.50  # Exit if lost 50% of max loss
        self.profit_target_percent = 0.75  # Exit at 75% of max profit
    
    def calculate_stop(self, position_data, current_market_data):
        """
        Calculate optimal stop loss
        
        For vertical spreads: Monitor underlying stock price
        Exit if:
        1. Stock moves > 1 std dev against position
        2. Spread lost 50% of max loss
        3. Spread made 75% of max profit
        4. DTE < 2 days (close out)
        """
        
        entry_price = position_data["entry_price"]
        buy_strike = position_data["buy_strike"]
        sell_strike = position_data["sell_strike"]
        max_loss = position_data["max_loss_per_contract"]
        max_profit = position_data["max_profit_per_contract"]
        entry_cost = position_data["entry_cost"]
        dte = current_market_data["dte"]
        
        current_spread_price = current_market_data["spread_bid"]
        unrealized_pnl = (entry_cost - current_spread_price) * 100
        
        exit_rules = {
            "profit_target": {
                "triggered": unrealized_pnl >= max_profit * self.profit_target_percent,
                "reason": f"Profit target reached: {unrealized_pnl:.0f}/${max_profit:.0f}",
            },
            "max_loss": {
                "triggered": unrealized_pnl <= -max_loss * self.max_loss_percent,
                "reason": f"Max loss threshold: {unrealized_pnl:.0f}/${-max_loss:.0f}",
            },
            "dte_expiration": {
                "triggered": dte < 2,
                "reason": "Close-to-expiration: < 2 DTE",
            },
            "underlying_moves": {
                "triggered": self._underlying_moved_too_far(
                    current_market_data["stock_price"],
                    entry_price,
                    position_data["implied_move"],
                    position_data["strategy"]
                ),
                "reason": "Underlying moved beyond implied move",
            },
        }
        
        return exit_rules
    
    def _underlying_moved_too_far(self, current_price, entry_price, 
                                    implied_move, strategy):
        """
        Check if underlying moved against position
        """
        move_distance = abs(current_price - entry_price)
        
        # Bull position: sell if stock drops >1 std dev
        if "BULL" in strategy and current_price < entry_price - implied_move:
            return True
        
        # Bear position: sell if stock rises >1 std dev
        if "BEAR" in strategy and current_price > entry_price + implied_move:
            return True
        
        return False
```

---

### Phase 5: Customer Suitability Validation

#### 5.1 Vertical Spread Suitability Checker

```python
class VerticalSpreadSuitabilityValidator:
    """
    Ensures customer can trade vertical spreads
    Checks:
    1. Account size
    2. Options approval level
    3. Experience level
    4. Risk tolerance
    """
    
    def validate(self, customer_profile, proposed_trade):
        """
        Returns: {
            "suitable": True/False,
            "checks": [...],
            "blocking_issues": [...],
        }
        """
        
        checks = []
        blocking_issues = []
        
        # Check 1: Options Level
        options_check = self._validate_options_level(customer_profile)
        checks.append(options_check)
        if not options_check["passed"]:
            blocking_issues.append(options_check["reason"])
        
        # Check 2: Account Size
        account_check = self._validate_account_size(customer_profile)
        checks.append(account_check)
        if not account_check["passed"]:
            blocking_issues.append(account_check["reason"])
        
        # Check 3: Experience
        experience_check = self._validate_experience(customer_profile)
        checks.append(experience_check)
        if not experience_check["passed"]:
            blocking_issues.append(experience_check["reason"])
        
        # Check 4: Proposed Trade Suitability
        trade_check = self._validate_trade_size(
            customer_profile, proposed_trade
        )
        checks.append(trade_check)
        if not trade_check["passed"]:
            blocking_issues.append(trade_check["reason"])
        
        suitable = len(blocking_issues) == 0
        
        return {
            "suitable": suitable,
            "checks": checks,
            "blocking_issues": blocking_issues,
        }
    
    def _validate_options_level(self, customer_profile):
        """Must have options level 2+ (spreads approved)"""
        passed = customer_profile["options_level"] >= 2
        return {
            "name": "Options Approval Level",
            "passed": passed,
            "reason": "Customer must have spreads approval (Level 2+)",
            "customer_level": customer_profile["options_level"],
        }
    
    def _validate_account_size(self, customer_profile):
        """Minimum $2,000 account balance"""
        min_balance = 2000
        passed = customer_profile["account_balance"] >= min_balance
        return {
            "name": "Account Size",
            "passed": passed,
            "reason": f"Minimum ${min_balance:,.0f} required",
            "customer_balance": customer_profile["account_balance"],
        }
    
    def _validate_experience(self, customer_profile):
        """Check trading experience"""
        # Could be based on:
        # - Account age (min 3 months)
        # - Previous options trades (min 5)
        # - Broker assessment
        
        account_age_days = (datetime.now() - customer_profile["account_open_date"]).days
        previous_option_trades = customer_profile["options_trades_count"]
        
        passed = (account_age_days >= 90) and (previous_option_trades >= 5)
        
        return {
            "name": "Experience Level",
            "passed": passed,
            "reason": "Requires 90+ days account age & 5+ prior option trades",
            "account_age_days": account_age_days,
            "prior_options_trades": previous_option_trades,
        }
    
    def _validate_trade_size(self, customer_profile, proposed_trade):
        """Trade size appropriate for account"""
        account_balance = customer_profile["account_balance"]
        max_loss = proposed_trade["max_loss_per_contract"]
        contracts = proposed_trade["contracts"]
        total_risk = max_loss * contracts
        
        # Risk should not exceed 2% of account
        max_risk = account_balance * 0.02
        passed = total_risk <= max_risk
        
        return {
            "name": "Trade Size",
            "passed": passed,
            "reason": f"Max risk ${max_risk:,.0f}, proposed ${total_risk:,.0f}",
            "account_balance": account_balance,
            "proposed_risk": total_risk,
            "max_allowed_risk": max_risk,
        }
```

---

## IMPLEMENTATION TIMELINE

### Week 1-2: Core ML Model
- [ ] Build VerticalSpreadDirectionPredictor class
- [ ] Integrate RSI, Bollinger Bands, Moving Averages
- [ ] Backtest on 3 years of data (45,000+ trades)
- [ ] Validate 65-75% accuracy on direction prediction

### Week 3-4: Strike Selection & Spreads
- [ ] Build VerticalSpreadSelector class
- [ ] Implement implied move calculation
- [ ] Build bull/bear call & put spread selection
- [ ] Test strike selection logic

### Week 5: Integration
- [ ] Merge with existing calendar spread generator
- [ ] Update OrderExecutor for multi-leg orders
- [ ] Implement suitability checks
- [ ] Build stop loss manager

### Week 6: Risk Management
- [ ] Implement circuit breakers
- [ ] Build daily P&L tracking
- [ ] Create exit rules
- [ ] Test edge cases (gaps, halts, low liquidity)

### Week 7: Testing
- [ ] Unit tests (>90% pass rate)
- [ ] Integration tests with Tastytrade API
- [ ] Paper trading (14+ days)
- [ ] Stress testing (volatility scenarios)

### Week 8: Compliance & Deployment
- [ ] Complete Tastytrade Exhibit A
- [ ] Create customer education materials
- [ ] Finalize Terms of Service
- [ ] Beta launch (5-10 customers)

---

## DELIVERABLES FOR ANTIGRAVITY

### Code Files Required

```
src/
├── direction_predictor.py
│   ├── VerticalSpreadDirectionPredictor class
│   ├── calculate_direction_signal()
│   ├── _rsi_signal(), _bollinger_signal(), etc.
│   └── _ensemble_vote()
│
├── vertical_spread_selector.py
│   ├── VerticalSpreadSelector class
│   ├── select_spread()
│   ├── _select_bull_call_spread()
│   ├── _select_bear_call_spread()
│   └── _calculate_implied_move()
│
├── combined_signal_generator.py
│   ├── CombinedSignalGenerator class
│   ├── generate_signals() (calendar + vertical)
│   └── Merges both strategies
│
├── vertical_stop_manager.py
│   ├── VerticalSpreadStopManager class
│   ├── calculate_stop()
│   └── _underlying_moved_too_far()
│
├── suitability_validator.py
│   ├── VerticalSpreadSuitabilityValidator class
│   ├── validate()
│   ├── _validate_options_level()
│   ├── _validate_account_size()
│   └── _validate_trade_size()
│
└── order_executor_vertical.py
    ├── Update OrderExecutor for multi-leg orders
    ├── _execute_vertical()
    └── Tastytrade multi-leg order placement
```

### Documentation Files

```
docs/
├── STRATEGY_DOCUMENTATION.md
│   ├── Vertical spread strategy overview
│   ├── Entry/exit criteria
│   ├── Risk management
│   └── Historical backtest results
│
├── ML_MODEL_SPECS.md
│   ├── Direction predictor architecture
│   ├── Feature engineering
│   ├── Training data & methodology
│   └── Accuracy metrics
│
├── TASTYTRADE_INTEGRATION.md
│   ├── API integration points
│   ├── Multi-leg order placement
│   ├── Authentication (OAuth)
│   └── Rate limiting
│
├── COMPLIANCE_CHECKLIST.md
│   ├── Testing requirements
│   ├── Audit trail specifications
│   ├── Circuit breaker logic
│   └── Suitability validation
│
└── CUSTOMER_EDUCATION.md
    ├── Vertical Spreads 101
    ├── Risk/reward diagrams
    ├── Example trade walkthrough
    └── Common pitfalls
```

### Test Files

```
tests/
├── test_direction_predictor.py
│   ├── test_rsi_signal()
│   ├── test_ensemble_voting()
│   ├── test_accuracy_backtest()
│   └── test_edge_cases()
│
├── test_vertical_spread_selector.py
│   ├── test_strike_selection()
│   ├── test_implied_move_calculation()
│   ├── test_contract_sizing()
│   └── test_edge_cases()
│
├── test_suitability_validator.py
│   ├── test_account_minimum()
│   ├── test_options_level()
│   ├── test_trade_size_validation()
│   └── test_various_profiles()
│
└── test_integration.py
    ├── test_end_to_end_signal_to_order()
    ├── test_error_handling()
    ├── test_circuit_breaker()
    └── test_tastytrade_api_integration()
```

---

## CONCLUSION

### Legal Summary
✅ **SAFE TO OPERATE** on Tastytrade with proper documentation and compliance controls.
⚠️ **KEY RISKS:** API termination, customer losses, regulatory scrutiny, market manipulation accusations.
✅ **MITIGATION:** Clear documentation, suitability checks, circuit breakers, audit trails, insurance.

### Implementation Summary
✅ **TIMELINE:** 8 weeks to production (with existing team).
✅ **COMPLEXITY:** Moderate (builds on existing calendar spread system).
✅ **ML COMPONENT:** Direction prediction (65-75% accuracy sufficient).
✅ **INTEGRATION:** Tastytrade multi-leg API (OAuth required).

### Next Steps
1. **Approve** this plan with leadership
2. **Assign** development to Antigravity team
3. **Brief** team on legal/compliance requirements
4. **Start** Phase 1 (ML model) immediately
5. **Review** completed code against compliance checklist

---

**Document Prepared By:** AI Calendar Spread System Team  
**Date:** January 19, 2026  
**Status:** Ready for Development  
**Approval Required:** YES  
**Legal Review Recommended:** YES (budget $2,000-5,000)


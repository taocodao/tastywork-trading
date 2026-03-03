# TurboBounce Legal & Compliance Plan: Signal Provider with Auto-Approve Execution

## Executive Summary

TurboBounce must navigate a critical legal boundary: the line between a **software tool / trade signal provider** and a **registered investment adviser (RIA)**. The safest and most scalable legal positioning is as a **SaaS technology platform** that publishes impersonal trade signals and provides users with optional auto-approve functionality — where the user retains full control at all times. This plan covers the regulatory framework, the exact legal structure to adopt, every disclaimer required, website design requirements, Terms of Service architecture, and the complete compliance implementation roadmap.

***

## Part 1: Regulatory Landscape

### The Investment Advisers Act of 1940

Under Section 202(a)(11) of the Investment Advisers Act, an "investment adviser" is any person who, for compensation, advises others on the value of securities or the advisability of investing in, purchasing, or selling securities. If TurboBounce meets this definition, it would need to register as an RIA with the SEC or state regulators.[^1][^2][^3]

However, there are exclusions. The most relevant one for TurboBounce is the **Publisher's Exclusion** under Section 202(a)(11)(D), which exempts publishers of bona fide financial publications of general and regular circulation. To qualify, a publication must be:[^2][^4]

1. **General and impersonal** — advice is not adapted to any specific subscriber's portfolio or needs[^4]
2. **Bona fide / genuine** — disinterested commentary, not promotional material designed to evade registration[^3]
3. **General and regular circulation** — not timed to specific market events or episodic market activity[^4]

### The Auto-Trading Risk Zone

The SEC has explicitly taken enforcement action against providers who combine newsletter signals with auto-trading and make misleading performance claims. In the landmark **Terry's Tips case (2005)**, the SEC charged an auto-trading newsletter provider with Advisers Act violations for obtaining discretionary trading authority over subscriber accounts and publishing misleading return projections. The SEC considers firms that publish investment newsletters **and** engage in auto-trading to generally be investment advisers.[^5][^6][^7]

### FINRA's 2025 Warning on Unregistered Auto-Trading

In July 2025, FINRA issued a direct warning about unregistered entities offering auto-trading services to retail investors. FINRA identified an increase in unregistered entities making misleading claims — including "beginner-friendly," "risk-free," and "consistent monthly returns of more than 10 percent". Services offered by registered entities must comply with rules requiring prioritization of client's best interest and avoidance of conflicts of interest. Services by unregistered parties lack these protections.[^8][^9][^10]

### The Option Alpha SaaS Precedent

Option Alpha provides the clearest legal precedent for TurboBounce's positioning. Option Alpha explicitly states: **"No, Option Alpha is not a registered investment advisor (RIA) nor a brokerage. We are a software-as-a-service (SaaS) technology provider."** The key distinctions that protect Option Alpha:[^11]

- Users build their own bots and define their own automation logic
- The platform only submits orders at the user's direction and instruction
- Users retain complete control — nothing runs without explicit permission
- Option Alpha does not exercise discretion over any account
- Revenue comes from software subscriptions, not commissions or AUM fees[^11]

### The tastytrade NSP (Newsletter Service Provider) Model

tastytrade's Autotrade program provides another viable legal pathway. Under this model, TurboBounce would function as a **Newsletter Service Provider (NSP)** that sends trade recommendations to tastytrade. Critically, tastytrade's legal agreement states: "The unaffiliated NSPs may or may not be registered investment advisers, and inclusion in the Autotrade program does not imply that they either are or are not required to be so registered. tastytrade does not require NSPs to be registered in any capacity."[^12]

Under this model, the **customer** grants limited trading authorization to **tastytrade** (the broker), not to TurboBounce. tastytrade acts as the customer's agent, and TurboBounce merely sends signal recommendations. tastytrade does not evaluate the suitability of NSP-recommended transactions.[^12]

***

## Part 2: TurboBounce's Optimal Legal Structure

### Recommended Model: Hybrid SaaS + Signal Publisher

TurboBounce should position itself as a **SaaS technology platform** that:

1. **Publishes** impersonal, algorithmic trade signals to all subscribers equally (Publisher's Exclusion)
2. **Provides software tools** that allow users to configure, review, and approve/reject each trade signal (SaaS model)
3. **Integrates with brokerages** via API where the user grants authorization to the broker, not to TurboBounce (NSP model)

### Critical Legal Boundaries — What TurboBounce Must NEVER Do

| Prohibited Action | Why It's Dangerous | Legal Risk |
|---|---|---|
| Tailor signals to individual subscriber portfolios | Crosses into personalized investment advice | RIA registration required[^4] |
| Exercise discretionary authority over user accounts | Triggers investment adviser classification | SEC enforcement[^5] |
| Guarantee or project specific returns | Violates Advisers Act anti-fraud provisions | SEC/state enforcement[^5][^6] |
| Auto-execute trades without any user approval mechanism | Removes user control — looks like discretionary management | FINRA/SEC scrutiny[^9] |
| Claim to "manage" user money or assets | Implies fiduciary relationship | RIA registration required[^13] |
| Use terms like "assets under management" | FINRA specifically flagged this as a red flag[^9] |  |

### What TurboBounce CAN Safely Do

| Permitted Action | Legal Basis |
|---|---|
| Publish identical trade signals to all subscribers | Publisher's Exclusion — impersonal, general circulation[^3] |
| Provide software where users configure auto-approve settings | SaaS tool model (Option Alpha precedent)[^11] |
| Charge subscription fees for software access | SaaS revenue — not compensation for investment advice |
| Display backtest results with proper disclaimers | Permitted if not misleading[^14] |
| Integrate with broker APIs where user grants authorization to the broker | NSP/Autotrade model (tastytrade precedent)[^12] |
| Offer educational content about options strategies | Publisher's Exclusion — educational[^15] |

***

## Part 3: Business Entity Setup

### LLC Formation

TurboBounce should be incorporated as a **Limited Liability Company (LLC)** in a business-friendly state (Delaware or Wyoming). The LLC provides:[^16]

- Asset protection for personal assets of the founders
- Flexible tax election (partnership or S-Corp)
- Standard structure for SaaS businesses

### Required Registrations

| Registration | When Required | Notes |
|---|---|---|
| State LLC formation | Before launch | Delaware or Wyoming recommended |
| EIN (IRS) | Before opening bank accounts | Required for all business entities |
| State business license | Before operation | Varies by state |
| SEC/State IA registration | **NOT required** if properly structured as SaaS/publisher | Only if crossing into investment advice |
| Money transmitter license | **NOT required** | TurboBounce never holds or moves customer funds |

### Insurance

- **Errors & Omissions (E&O) insurance** — covers claims arising from software failures, signal errors, or alleged negligence
- **General commercial liability** — standard business coverage
- **Cyber liability insurance** — covers data breaches (critical since broker API credentials are involved)

***

## Part 4: Website Legal Pages — Complete Specifications

### Page 1: Terms of Service (ToS)

The Terms of Service must include every section below. Each section heading should appear as a numbered article on the website.[^17][^18]

**Article 1 — Acceptance of Terms**
- User must affirmatively accept ToS via checkbox before creating an account
- Acceptance logged with user ID, timestamp, IP address, and ToS version
- Continued use constitutes acceptance of updated terms

**Article 2 — Service Description**
- "TurboBounce is a software-as-a-service (SaaS) platform that publishes algorithmic trade signal notifications and provides automation tools for options trading."
- "TurboBounce is NOT a registered investment advisor (RIA), broker-dealer, or fiduciary. We are a technology company that provides software tools."
- "All trade signals are generated algorithmically and delivered identically to all subscribers. No signal is personalized or tailored to any individual subscriber's account, portfolio, risk tolerance, or financial situation."

**Article 3 — User Responsibilities**
- Users are solely responsible for all trading decisions
- Users must evaluate the suitability of any trade signal for their own financial situation
- Users must maintain appropriate options approval levels at their brokerage
- Users must monitor their accounts and understand the strategies being deployed
- Users acknowledge they have read and understand the OCC's Characteristics and Risks of Standardized Options

**Article 4 — Auto-Approve Feature**
- "The auto-approve feature is a **user-configured** software setting that allows trade signal orders to be submitted to the user's connected brokerage account."
- "Users may enable or disable auto-approve at any time."
- "Users define their own allocation limits, position limits, and risk parameters."
- "TurboBounce does not exercise discretionary authority over any user account. All auto-approve settings are configured and controlled entirely by the user."
- "Users may override, pause, cancel, or modify any trade at any time through the platform or directly through their brokerage."

**Article 5 — No Investment Advice**
- "Nothing on this website or within the TurboBounce platform constitutes investment advice, financial advice, trading advice, or any other form of professional advice."
- "Trade signals are informational outputs of an algorithmic system and should not be construed as recommendations to buy or sell any security."
- "You should consult a qualified financial advisor before making any investment decisions."

**Article 6 — Subscription and Payment**
- Subscription tiers, pricing, billing cycle
- Auto-renewal terms
- Cancellation and refund policy (7-day refund window on annual plans)
- BNPL terms if applicable

**Article 7 — Limitation of Liability**
- TurboBounce is not liable for any trading losses, missed signals, technical failures, or broker execution errors
- Maximum liability capped at the subscription fees paid in the preceding 12 months
- No liability for third-party services (broker platforms, API failures)
- Software provided "AS IS" without warranties[^14]

**Article 8 — Indemnification**
- Users agree to indemnify and hold harmless TurboBounce from any claims, losses, or liabilities arising from their use of the platform[^14]

**Article 9 — Intellectual Property**
- All algorithms, strategies, signals, and platform code are proprietary
- Users may not reverse-engineer, copy, or redistribute signals

**Article 10 — Dispute Resolution**
- Mandatory binding arbitration (AAA rules)
- Class action waiver
- Governing law: [State] law

**Article 11 — Termination**
- TurboBounce reserves the right to terminate any account for ToS violations
- User-initiated cancellation process
- Effect on open positions upon termination

**Article 12 — Privacy**
- Reference to separate Privacy Policy
- Data collection, broker credential handling (OAuth only — TurboBounce never stores passwords)
- CCPA/GDPR compliance as applicable

**Article 13 — Modifications**
- Material changes require affirmative re-acceptance
- Non-material changes effective upon email notice + continued use[^17]

***

### Page 2: Risk Disclosure Statement

This must be a **standalone page**, prominently linked from the footer, signup flow, and dashboard. It must cover:

**Section A — General Investment Risk**
> "Trading securities, including options, involves substantial risk of loss and is not suitable for all investors. You should carefully consider whether trading is appropriate for you in light of your financial condition. Past performance is not indicative of future results."

**Section B — Options-Specific Risks**
> "Options involve special risks and are not suitable for all investors. Prior to buying or selling an option, a person must receive a copy of Characteristics and Risks of Standardized Options (ODD). Copies of the ODD are available from your broker, by calling The Options Clearing Corporation at 1-888-OPTIONS, or by visiting www.theocc.com/about/publications/character-risks.jsp."

**Section C — Algorithmic / AI Trading Risks**
> "TurboBounce uses machine learning algorithms to generate trade signals. These algorithms are trained on historical data and may not perform similarly in future market conditions. Algorithmic systems are subject to model risk, overfitting risk, technology failures, and may generate signals that result in significant losses."

**Section D — Backtesting Limitations**
> "All performance figures presented on this website are based on backtested simulations using historical data from 2019–2025. Backtested results are hypothetical and have inherent limitations: (1) they are designed with the benefit of hindsight, (2) they do not reflect actual trading, (3) they do not account for all costs including commissions and slippage, (4) they cannot fully account for the impact of financial risk in actual trading. Actual results may differ materially from backtested results."

**Section E — Auto-Approve Risk**
> "If you enable the auto-approve feature, trades will be submitted to your brokerage account based on algorithmic signals without further manual review by you for each individual trade. You are responsible for configuring appropriate allocation limits, position limits, and risk parameters. You may disable auto-approve at any time. Enabling auto-approve does not relieve you of responsibility for monitoring your account."

**Section F — Leverage and Margin Risk**
> "Options trading may involve leverage, which can amplify both gains and losses. Margin requirements may change without notice. You may be required to deposit additional funds on short notice."

**Section G — No Guarantees**
> "TurboBounce makes no guarantees, representations, or warranties regarding the accuracy, reliability, or completeness of any trade signal, performance data, or algorithmic output. There is no guarantee that any trade signal will be profitable."

***

### Page 3: Disclaimer Page

A concise, plain-language version displayed prominently:

**Required Disclaimer Text (must appear on every page with performance data):**

> **IMPORTANT DISCLAIMER:** TurboBounce is a software technology platform, not a registered investment advisor, broker-dealer, or financial planner. We do not provide personalized investment advice. All trade signals are algorithmically generated and delivered identically to all subscribers. Past performance, whether actual or indicated by backtests, is not indicative of future results. Trading options involves substantial risk of loss and is not appropriate for all investors. You could lose some or all of your invested capital. Consult a qualified financial professional before making investment decisions. See full Risk Disclosure for details.

**CFTC Disclaimer (if any underlying assets touch commodities/futures):**

> "CFTC RULE 4.41 — Hypothetical or simulated performance results have certain limitations. Unlike an actual performance record, simulated results do not represent actual trading. Also, since the trades have not been executed, the results may have under- or over-compensated for the impact, if any, of certain market factors, such as lack of liquidity. Simulated trading programs in general are also subject to the fact that they are designed with the benefit of hindsight. No representation is being made that any account will or is likely to achieve profit or losses similar to those shown."[^19]

***

### Page 4: Privacy Policy

Must include:
- What data is collected (name, email, broker OAuth tokens, trading activity metadata)
- How data is used (signal delivery, platform improvement, analytics)
- Third-party sharing (broker API only — for order execution at user's direction)
- Data retention periods
- User rights (access, deletion, portability)
- CCPA rights for California residents
- Security measures (encryption, OAuth — never store broker passwords)
- Cookie policy

***

## Part 5: Website Design — Compliance Requirements

### Signup Flow (Mandatory Compliance Gates)

The signup process must include these legal checkpoints in this exact order:

**Step 1 — Account Creation**
- Email, password, basic profile
- Checkbox: "I have read and agree to the Terms of Service" (linked)
- Checkbox: "I acknowledge the Risk Disclosure" (linked)
- Both must be checked to proceed — no pre-checked boxes

**Step 2 — Options Knowledge Acknowledgment**
- Brief questionnaire (not suitability — that's the broker's job)
- "Have you traded options before?" (Yes/No)
- "Do you understand that options trading involves risk of loss?" (Yes/No)
- "Have you read the OCC Characteristics and Risks of Standardized Options?" (Yes/No with link)
- Educational tooltip: link to OCC document

**Step 3 — Auto-Approve Configuration (if user enables)**
- Clear explanation: "Auto-approve means trade signals will be sent to your brokerage for execution without individual manual approval. You retain full control and can disable this at any time."
- User sets allocation limit (maximum capital per trade)
- User sets position limit (maximum concurrent positions)
- User sets daily trade limit
- Additional checkbox: "I understand that enabling auto-approve means trades will execute in my account based on algorithmic signals. I accept full responsibility for monitoring my account."

**Step 4 — Broker Connection**
- OAuth flow to tastytrade, IBKR, or other supported broker
- User grants limited trading authorization to the broker (not to TurboBounce)
- Display broker's own risk disclosures during connection

### Dashboard Design — Compliance Elements

Every dashboard page must include:

| Element | Location | Content |
|---|---|---|
| Disclaimer banner | Top of dashboard, persistent | "TurboBounce provides trade signals, not investment advice. Past performance ≠ future results." |
| Auto-approve status indicator | Prominent, top-right | Green "AUTO ON" or grey "MANUAL" — one-click toggle |
| Override button | Next to every open position | User can close, modify, or pause any position instantly |
| Performance watermark | On all backtest charts | "HYPOTHETICAL BACKTESTED RESULTS — NOT ACTUAL TRADING" |
| Risk parameters display | Dashboard sidebar | Shows user's current allocation limit, position limit, daily limit |
| Pause all button | Top navigation, red | Immediately stops all auto-approve activity |

### Performance Display Rules

When showing any backtest or performance data on the website:

- **Always** label as "Backtested / Simulated / Hypothetical" — never imply live trading results unless verified[^5]
- **Always** show losing years (2020, 2022) alongside winning years — cherry-picking is fraudulent[^6]
- **Always** display the full CFTC Rule 4.41 disclaimer near performance tables[^19]
- **Never** project future returns as guaranteed or expected
- **Never** use phrases like "will make you money," "guaranteed returns," or "risk-free"[^9]
- **Always** include context: "These results are from a backtest simulation. Actual results may differ."
- **Recommended:** Show side-by-side comparison with benchmark (SPY, QQQ) for honest context

### Landing Page Compliance

The landing page (as described in the implementation files) must include:

- Footer disclaimer visible on every scroll position
- Performance data always paired with "BACKTESTED RESULTS" label
- Compounding calculator disclaimer: "Projections based on historical backtest averages. Past performance does not guarantee future results. Actual returns will vary."
- No claims of "guaranteed," "risk-free," or "easy money"
- Clear identification that TurboBounce is a software platform, not an investment adviser

***

## Part 6: Marketing Compliance — What You Can and Cannot Say

### Permitted Marketing Language

| ✅ Safe to Say | Why |
|---|---|
| "Our backtest showed a 23.4% CAGR over 7 years" | Factual, with required disclaimers |
| "AI-powered trade signal platform" | Describes software function |
| "Defined-risk options strategies" | Factual description of trade structure |
| "Automated trade execution with your approval" | Emphasizes user control |
| "Start with as little as $5,000" | Factual minimum, not a promise |
| "7-year backtest through two market crashes" | Factual, includes bad periods |

### Prohibited Marketing Language

| ❌ Never Say | Why |
|---|---|
| "Guaranteed returns" / "Risk-free" | FINRA specifically flagged this[^9] |
| "We manage your money" | Implies RIA/fiduciary relationship[^13] |
| "Our strategy will make you rich" | Misleading projection |
| "You can't lose" / "No losses" | Fraudulent[^5] |
| "$5K becomes $21K" without disclaimer | Misleading without backtest context[^19] |
| "Assets under management" | FINRA red flag for unregistered entities[^9] |
| "Financial advice" / "Investment advice" | Triggers adviser classification[^4] |

### Social Media Compliance (TikTok, YouTube, Reddit)

All social media content must follow these rules:[^20]

- Every post with performance numbers must include a disclaimer (in caption or pinned comment)
- Short-form video minimum: verbal mention "backtested results, not a guarantee" + on-screen text
- YouTube descriptions: full disclaimer text in every video description
- Reddit posts: include disclaimer at bottom of every post with performance data
- Never make return projections without the word "hypothetical" or "backtested"
- Maintain records of all social media communications[^20]

***

## Part 7: Auto-Approve Architecture — Legal-Safe Implementation

### How Auto-Approve Must Work (Legally Safe Design)

The auto-approve feature is the highest-risk legal element. Here is the exact architecture that keeps TurboBounce on the right side of the law:

**Model A — Signal + One-Click Approve (Safest)**

1. Algorithm generates trade signal
2. Signal is published to all subscribers simultaneously (impersonal)
3. User receives notification (push, email, dashboard)
4. User reviews the signal (symbol, strategy, strikes, expiration, risk)
5. User clicks "Approve" or "Reject"
6. If approved, the platform submits the order to the user's broker via API
7. Broker executes the order in the user's account

**Model B — Auto-Approve with User-Defined Parameters (Moderate Risk)**

1. User pre-configures: allocation limit, position limit, strategy types allowed, ticker universe
2. Algorithm generates signal
3. If signal fits within user's parameters → order is auto-submitted to broker
4. If signal exceeds any parameter → held for manual review
5. User receives real-time notification of every trade (approved or executed)
6. User can pause, override, or close any position at any time

**Model C — Full Auto with NSP/Autotrade (tastytrade-Specific)**

1. TurboBounce registers as NSP with tastytrade's Autotrade program
2. User signs tastytrade's Limited Trading Authorization (grants authority to tastytrade, not TurboBounce)[^12]
3. TurboBounce sends signals to tastytrade
4. tastytrade executes in user's account per the Autotrade agreement
5. This is the cleanest legal structure because the legal relationship is between the user and tastytrade

### Recommended Implementation Order

| Phase | Model | When |
|---|---|---|
| Phase 1 (Launch) | Model A — Signal + One-Click Approve | Month 1–3 |
| Phase 2 (Growth) | Model B — Auto-Approve with User Parameters | Month 4–6 |
| Phase 3 (Scale) | Model C — tastytrade NSP Autotrade | Month 6–12 |

Starting with Model A establishes the strongest legal foundation. Users manually approve every trade, making it unambiguous that TurboBounce has zero discretionary authority. Model B adds convenience while maintaining user-defined guardrails. Model C leverages tastytrade's existing legal infrastructure.

***

## Part 8: Record Keeping Requirements

Even without RIA registration, TurboBounce should maintain comprehensive records for legal protection:[^20]

| Record | Retention Period | Purpose |
|---|---|---|
| All trade signals published | 7 years | Prove signals were impersonal and identical to all subscribers |
| User ToS acceptance logs | 7 years | Prove informed consent |
| Auto-approve configuration history | 7 years | Prove user controlled all parameters |
| All marketing materials | 7 years | Defend against misleading claims allegations |
| Social media posts | 7 years | FINRA/SEC may request communications records |
| Customer support interactions | 5 years | Prove no personalized advice was given |
| Backtest methodology documentation | Indefinite | Defend performance claims |
| Algorithm version history | Indefinite | Prove consistency and good faith |

***

## Part 9: Compliance Monitoring — Ongoing Obligations

### Monthly Compliance Checklist

- Review all marketing materials for prohibited language
- Audit social media posts for disclaimer inclusion
- Verify auto-approve disclosure is functioning in signup flow
- Confirm backtest disclaimer appears on all performance displays
- Review customer support interactions for any instances of personalized advice (and retrain team if found)
- Verify record retention systems are operational

### Quarterly Compliance Review

- Engage a securities attorney to review any new marketing campaigns
- Review regulatory updates from SEC, FINRA, and state regulators
- Update disclaimers and ToS if regulations change
- Review the Publisher's Exclusion analysis in light of any new SEC guidance[^21]
- Assess whether TurboBounce's growing sophistication requires RIA registration

### Annual Actions

- Full legal audit by a securities attorney
- E&O insurance policy review and renewal
- Update Terms of Service with annual version number
- Review and update Risk Disclosure for any new strategy types or risk factors
- File state business renewals

***

## Part 10: Implementation Roadmap

### Month 1 — Legal Foundation

- Form LLC (Delaware or Wyoming)
- Obtain EIN, open business bank account
- Hire a securities attorney for initial consultation and ToS drafting
- Obtain E&O insurance quote
- Draft Terms of Service, Risk Disclosure, Disclaimer, Privacy Policy

### Month 2 — Website Legal Integration

- Implement signup flow with all compliance gates
- Add disclaimer banner to all pages
- Implement backtest watermarks on all performance charts
- Build auto-approve configuration with user-defined limits
- Implement ToS acceptance logging with timestamps and versioning

### Month 3 — Pre-Launch Legal Review

- Securities attorney reviews entire website, all marketing materials, all legal pages
- Penetration test for data security (broker OAuth tokens)
- Test auto-approve flow end-to-end for legal compliance
- Verify all record retention systems are operational
- Soft launch to beta users with full compliance stack active

### Month 4–6 — Launch and Monitor

- Public launch with Model A (Signal + One-Click Approve)
- Begin social media marketing with disclaimer templates
- Monitor for any customer support interactions that could be construed as personalized advice
- Apply to tastytrade NSP/Autotrade program
- Weekly compliance review of all published content

### Month 6–12 — Scale with Compliance

- Activate Model B auto-approve with user-defined parameters
- Launch tastytrade Autotrade integration (Model C)
- Expand to additional broker APIs (IBKR)
- Quarterly legal audit
- Annual comprehensive legal review

***

## Part 11: Estimated Legal Costs

| Item | Cost | Frequency |
|---|---|---|
| LLC formation (Delaware) | $300–$500 | One-time |
| Securities attorney — initial consultation & ToS | $3,000–$8,000 | One-time |
| E&O insurance | $1,500–$3,000/year | Annual |
| Cyber liability insurance | $1,000–$2,500/year | Annual |
| Ongoing legal review (quarterly) | $1,000–$2,000/quarter | Quarterly |
| Annual comprehensive audit | $3,000–$5,000 | Annual |
| **Year 1 Total** | **$12,000–$25,000** | |

This is the cost of operating legally. The cost of operating *illegally* — SEC enforcement, FINRA penalties, and civil litigation — ranges from $57,000+ in fines to criminal prosecution and imprisonment.[^20]

---

## References

1. [RIA vs. IAR: Understanding the Difference - InnReg](https://www.innreg.com/blog/ria-vs-iar) - RIA vs. IAR explained for fintech founders: firm vs. individual roles, registration paths, fiduciary...

2. [Jonathon Hendricks, January 26, 2015 - SEC.gov](https://www.sec.gov/divisions/investment/noaction/2015/jonathon-hendricks-012615-202a.htm) - Section 202(a)(11)(D) of the Advisers Act excludes from the definition of an investment adviser a “p...

3. [Navigating the Publisher's Exclusion Under the Advisers Act](https://www.jdsupra.com/legalnews/navigating-the-publisher-s-exclusion-6595699/) - In other words, the publication cannot serve as a vehicle for providing personalized investment advi...

4. [Navigating the Publisher's Exclusion Under the Advisers Act | Winstead](https://www.winsteadinvestmentmanagement.com/2025/12/navigating-the-publishers-exclusion-under-the-advisers-act/) - As financial markets and investors increasingly rely on instant access to data online, financial pro...

5. [SEC Sues Online Adviser for Conduct Involving “Auto-Trading”](https://www.sec.gov/news/press/2005-98.htm)

6. [SEC issues “auto-trading” alert | Investment Executive](https://www.investmentexecutive.com/news/from-the-regulators/sec-issues-auto-trading-alert/) - Regulator files charges regarding allegedly misleading performance projections

7. [Disclosure Concerning Auto Trading Service Providers](https://www.interactivebrokers.co.uk/en/?f=%2Fen%2Faccounts%2FlegalDocuments%2FautoTradingServiceDisclosure.php) - Disclosure Concerning Auto Trading Service Providers

8. [Know the Risks of Auto-Trading Services Offered by Unregistered ...](https://www.finra.org/investors/insights/auto-trading-unregistered-entities) - Many unregistered entities are increasingly promoting their auto-trading services to retail investor...

9. [Know the Risks of Auto-Trading Services Offered by Unregistered Entities](https://www.mitrade.com/insights/news/live-news/article-8-1012857-20250805) - FINRA has identified an increase in unregistered entities claiming to provide automated or "auto-tra...

10. [Know the Risks of Auto-Trading Services Offered by Unregistered Entities](https://www.fool.com/retirement/2025/08/05/know-the-risks-of-auto-trading-services-offered-by/) - Ads for these services can be enticing, offering increased convenience and the use of AI to inform t...

11. [Option Alpha FAQs | Get Answers to Common Questions](https://optionalpha.com/faqs) - Is Option Alpha an RIA? No, Option Alpha is not a registered investment advisor (RIA) nor a brokerag...

12. [Limited Trading Authorization and Agreement for Autotrade ...](https://assets.tastyworks.com/production/documents/broker_autotrade_limited_trading_authorization_and_agreement.pdf)

13. [Broker-Dealers vs. RIAs: Key Differences for Investors - Investopedia](https://www.investopedia.com/articles/active-trading/100915/rias-and-independent-brokerdealers-comparison.asp) - Broker-dealers often offer a wide range of investment products and services, whereas RIAs focus on p...

14. [Disclaimer - Advanced Trading Signals](https://www.advancedtradingsignals.com/disclaimer.html) - Advanced Trading Signals is not engaged in rendering any legal or professional services by placing t...

15. [Cryptocurrency Lawyer Adam Tracy on Trade Signal Providers](https://adamtracy.io/2019/10/05/cryptocurrency-lawyer-discusses-trade-signal-providers-and-crypto/) - They used to come in huge binders, and they were exempt from investment advisor registration because...

16. [How To Structure The Legal Ownership Of An RIA?](https://www.youtube.com/watch?v=od--Ihqs0u0) - I'm Brad Wales with Transition To RIA.  This is video #52 of the Transition To RIA video series wher...

17. [Trading Platform Terms of Service Template | Terms.Law](https://terms.law/Trading-Legal/guides/trading-platform-tos-template.html) - Complete, ready-to-use Terms of Service template for trading platforms with regulatory disclaimers, ...

18. [Sample Terms of Service Template - Termly](https://termly.io/resources/templates/terms-of-service-template/) - Download our free terms of service template for your website or app and learn how to fill it out pro...

19. [Disclaimer - Signal Trading Group](https://signaltradinggroup.com/disclaimer/) - Risk Disclosure Please read this required regulatory disclaimer prior to viewing any material on our...

20. [Regulatory Framework for Signal Trading - Micro Alphas](https://microalphas.com/signal-trading-regulation/) - Brokers face strict regulatory hurdles in signal trading, but what makes these rules so crucial for ...

21. [Information…or Advice? SEC Regulation of “Information Providers ...](https://www.jdsupra.com/legalnews/information-or-advice-sec-regulation-of-7053434/) - A significant reason behind the publisher's exclusion is that covered publishers do not provide tail...


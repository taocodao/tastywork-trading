# TradeMind.bot Brain Index

## How to Use This Brain
- This folder is the complete knowledge base for this workspace.
- Before doing anything significant:
  - Read this file.
  - Skim headings of all other brain/*.md files.
  - Ask the user which sub-area is relevant if unclear.

## Document Map

| File | Description |
|------|-------------|
| [LAST_SESSION.md](./LAST_SESSION.md) | ⚡ Quick "where we left off" — **read first** |
| [00_INDEX.md](./00_INDEX.md) | This file - table of contents |
| [01_PRODUCT_VISION.md](./01_PRODUCT_VISION.md) | Product goals, audience, constraints |
| [02_ARCHITECTURE_OVERVIEW.md](./02_ARCHITECTURE_OVERVIEW.md) | System diagram & components |
| [03_DOMAIN_KNOWLEDGE.md](./03_DOMAIN_KNOWLEDGE.md) | Options concepts, trading rules, APIs |
| [10_BACKEND_DESIGN.md](./10_BACKEND_DESIGN.md) | Backend services, data models |
| [11_FRONTEND_DESIGN.md](./11_FRONTEND_DESIGN.md) | UX flows, pages, components |
| [20_TRADING_LOGIC.md](./20_TRADING_LOGIC.md) | Strategies, risk logic, pre-trade checks |
| [25_SIGNAL_FRAMEWORK.md](./25_SIGNAL_FRAMEWORK.md) | Signal publishing pipeline: Theta/TQQQ/TurboBounce comparison |
| [30_IB_DIAGNOSIS.md](./30_IB_DIAGNOSIS.md) | IB Gateway diagnosis (Feb 2026) |
| [40_EC2_OPERATIONS.md](./40_EC2_OPERATIONS.md) | EC2 server startup & operations guide |
| [90_DECISIONS_LOG.md](./90_DECISIONS_LOG.md) | All key decisions with timestamps |

## Archive
Historical documentation from previous sessions is available in `archive/`:
- `theta_strategy_explained.md`
- `calendar_strategy_explained.md`
- `production_flow.md`
- `risk_management_system.md`
- And more...

## Session Snapshots
Located in `sessions/` - per-session summaries of work done.

## Agent Instructions
At start of each session:
1. Read this file
2. Skim document headings
3. Ask user which module(s) to focus on
4. Summarize current state before proceeding

At end of each session:
1. Create snapshot in `sessions/YYYY-MM-DD-session-NN.md`
2. Update relevant docs with any new decisions
3. Append entries to `90_DECISIONS_LOG.md`

---

## Recent Activity

### 2026-03-02
- Created `25_SIGNAL_FRAMEWORK.md`: comprehensive signal pipeline analysis across Theta, TQQQ and TurboBounce strategies
- Identified 6 critical gaps preventing TurboBounce signals from appearing in frontend
- Documented the Theta pattern (DB + WebSocket + Auto-approve) as the gold standard

### 2026-02-05
- Created workspace-scoped brain structure per implementation plan
- Set up .agent/rules, workflows, and skills
- Migrated documentation from conversation-scoped brain
- Fixed IB connection and Docker configuration issues

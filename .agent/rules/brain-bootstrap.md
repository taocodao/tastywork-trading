# Brain Bootstrap Rule

**Priority: CRITICAL - Execute on EVERY new conversation, EVERY login**

> ⚠️ Chat history does NOT persist across Antigravity logins.
> The `brain/` directory is the ONLY way to maintain continuity.

## On EVERY New Conversation

**MANDATORY** — Do these steps before any other work:

1. **Read** `brain/LAST_SESSION.md` — this is the quick "where we left off" summary
2. **Read** `brain/00_INDEX.md` — master index of all brain files
3. **Read** the latest file in `brain/sessions/` — detailed session snapshot
4. **Tell the user**: Summarize what you learned (recent work, active systems, pending items)
5. **Ask**: "Which area are we working on today?"
6. **Ground** all answers in brain files — never invent information

## At End of EVERY Session

**MANDATORY** — Before the user leaves:

1. **Update** `brain/LAST_SESSION.md` with:
   - What was accomplished today
   - Current state of active systems
   - Any pending items or next steps
2. **Create** session snapshot in `brain/sessions/YYYY-MM-DD-session-NN.md`
3. **Update** `brain/90_DECISIONS_LOG.md` if any significant decisions were made
4. **Remind** the user: "Brain updated. You can switch accounts safely."

## Why This Rule Exists

- **Antigravity chat history is per-login account** — switching accounts = conversations disappear
- The `brain/` directory lives in `D:\Projects\tastywork-trading-1\` (Git-tracked)
- It survives login switches, Antigravity upgrades, machine changes, everything
- `LAST_SESSION.md` is the fast-path to context recovery

## Brain File Reference

| File | Purpose | Priority |
|------|---------|----------|
| `brain/LAST_SESSION.md` | Quick "where we left off" | 🔴 Read first |
| `brain/00_INDEX.md` | Master index & bootstrap | 🔴 Read second |
| `brain/sessions/*.md` | Detailed session snapshots | 🟡 Read latest |
| `brain/01_PRODUCT_VISION.md` | Goals, users, constraints | As needed |
| `brain/02_ARCHITECTURE_OVERVIEW.md` | System diagram | As needed |
| `brain/03_DOMAIN_KNOWLEDGE.md` | Options concepts, APIs | As needed |
| `brain/20_TRADING_LOGIC.md` | Strategy implementation | As needed |
| `brain/40_EC2_OPERATIONS.md` | EC2 server operations | As needed |
| `brain/90_DECISIONS_LOG.md` | ADR-style decisions | As needed |

## Agent Checklist

Before starting new work:
- [ ] Read brain/LAST_SESSION.md
- [ ] Read brain/00_INDEX.md
- [ ] Check latest brain/sessions/*.md
- [ ] Summarize project state to user
- [ ] Confirm work area with user
- [ ] Begin work grounded in brain knowledge

Before user leaves:
- [ ] Update brain/LAST_SESSION.md
- [ ] Create session snapshot
- [ ] Update decisions log if needed
- [ ] Confirm brain is updated

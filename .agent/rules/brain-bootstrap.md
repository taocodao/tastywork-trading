# Brain Bootstrap Rule

**Priority: HIGH - Execute on EVERY new conversation**

On EVERY new conversation in this workspace:

1. **Read** `brain/00_INDEX.md`
2. **Load** the latest session snapshot from `brain/sessions/`
3. **Confirm** work area with user by asking: "Which area are we working on today?"
4. **Summarize** current project state before accepting new work
5. **Ground** all answers in brain files - never invent information

## Why This Rule Exists

- Antigravity sessions don't automatically share memory
- Changing login or closing window loses context
- The `brain/` directory is the ONLY persistent knowledge base
- This ensures continuity across sessions, machines, and logins

## Brain File Reference

| File | Purpose |
|------|---------|
| `brain/00_INDEX.md` | Master index & bootstrap |
| `brain/01_PRODUCT_VISION.md` | Goals, users, constraints |
| `brain/02_ARCHITECTURE_OVERVIEW.md` | System diagram |
| `brain/03_DOMAIN_KNOWLEDGE.md` | Options concepts, APIs |
| `brain/20_TRADING_LOGIC.md` | Strategy implementation |
| `brain/90_DECISIONS_LOG.md` | ADR-style decisions |
| `brain/sessions/*.md` | Per-session summaries |

## Agent Checklist

Before starting new work:
- [ ] Read brain/00_INDEX.md
- [ ] Check latest brain/sessions/*.md
- [ ] Confirm work area with user
- [ ] Summarize project state
- [ ] Begin work grounded in brain knowledge

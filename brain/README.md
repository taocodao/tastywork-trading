# TradeMind.bot Brain - Knowledge Base

## What Is This?

This `brain/` directory is the **persistent knowledge base** for the TradeMind.bot project. It ensures continuity across AI sessions, machine changes, and logins.

## How It Works

1. **On session start**: Agent reads `00_INDEX.md` and latest session snapshot
2. **During session**: Agent updates brain docs as decisions are made
3. **On session end**: Run `/end-session` to create snapshot

## Directory Structure

```
brain/
├── 00_INDEX.md           # Master index (read first)
├── 01_PRODUCT_VISION.md  # Product goals
├── 02_ARCHITECTURE_OVERVIEW.md  # System design
├── 03_DOMAIN_KNOWLEDGE.md       # Options trading concepts
├── 10_BACKEND_DESIGN.md  # Backend services
├── 11_FRONTEND_DESIGN.md # Frontend design
├── 20_TRADING_LOGIC.md   # Strategy implementation
├── 30_IB_DIAGNOSIS.md    # IB Gateway debugging
├── 40_EC2_OPERATIONS.md  # Server operations
├── 90_DECISIONS_LOG.md   # ADR-style decisions
├── sessions/             # Per-session snapshots
└── archive/              # Reference docs from old sessions
```

## For Developers

### Starting Work
1. Open workspace in code editor with AI assistant
2. Agent should automatically load `00_INDEX.md`
3. Confirm which area you're working on
4. Agent summarizes current state

### During Work
- Agent grounds all answers in brain files
- Significant decisions go to `90_DECISIONS_LOG.md`
- New knowledge added to relevant brain file

### Ending Work
1. Run `/end-session` workflow
2. Snapshot created in `sessions/`
3. Next session picks up where you left off

## Maintenance

Monthly:
- [ ] Review brain files for accuracy
- [ ] Archive old session snapshots (keep last 10)
- [ ] Split any files over 500 lines

## Related Config

- `.agent/rules/brain-bootstrap.md` - Forces brain loading
- `.agent/workflows/end-session.md` - Session snapshot generation
- `.agent/skills/brain-manager/SKILL.md` - Knowledge management

## Version Control

This directory should be tracked in Git:
```bash
git add brain/ .agent/
git commit -m "update: brain knowledge base"
```

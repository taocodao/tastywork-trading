---
name: brain-manager
description: Manages brain/ knowledge base. Use when updating documentation, adding decisions, or reorganizing brain files.
---

# Brain Manager Skill

## Purpose
Manage the `brain/` knowledge base to ensure persistent memory across sessions.

## When to Use
- When user makes a significant architectural decision
- When implementing new features that change system behavior
- When discovering new domain knowledge
- When reorganizing or splitting brain files

## Actions

### Log a Decision
When user makes a significant decision:

1. Add entry to `brain/90_DECISIONS_LOG.md`:
```markdown
## YYYY-MM-DD: [Decision Title]

**Decision**: [What was decided]

**Context**: [Why this decision was needed]

**Resolution**: [What was done]

**Affected**: [What files/components are impacted]
```

2. Update related brain files to reflect the decision

3. Confirm changes made to user

### Update Knowledge
When learning new project information:

1. Identify appropriate brain file:
   - Domain concepts → `03_DOMAIN_KNOWLEDGE.md`
   - Architecture → `02_ARCHITECTURE_OVERVIEW.md`
   - Strategy logic → `20_TRADING_LOGIC.md`
   - Backend services → `10_BACKEND_DESIGN.md`
   - Frontend UX → `11_FRONTEND_DESIGN.md`

2. Add information to appropriate section

3. Update `00_INDEX.md` if new files are created

### Split Large Files
When a brain file exceeds 500 lines:

1. Identify logical sub-sections
2. Create new numbered files (e.g., `21_THETA_DETAILS.md`)
3. Update `00_INDEX.md` with new file
4. Add cross-references between related files

## File Naming Convention

| Range | Category |
|-------|----------|
| 00 | Index/Bootstrap |
| 01-09 | Vision & Overview |
| 10-19 | Design Docs |
| 20-29 | Implementation Details |
| 30-39 | Operations & Debugging |
| 40-49 | Guides & How-Tos |
| 90-99 | Logs & History |

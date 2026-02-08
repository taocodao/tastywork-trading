# Antigravity Brain Persistence & Knowledge Migration Plan

## Problem Summary

You're experiencing the exact issue Antigravity is known for: **session isolation**. Every time you change login or close the window, Antigravity starts fresh because each conversation creates a new brain folder with a unique UUID in `~/.gemini/antigravity/brain/[uuid]/`. There's no automatic cross-session memory[^59][^63][^65].

## Solution: Centralized Workspace Brain Directory

The fix is to create a **dedicated `brain/` folder in your workspace** that serves as the single source of truth. By combining this with Antigravity's native features (rules, workflows, skills), you force the agent to load this persistent knowledge at every session start[^41][^49][^52][^62].

---

## Architecture Overview

### Directory Structure
```
<workspace-root>/
  .agent/
    rules/
      brain-bootstrap.md          # Forces brain loading at startup
    workflows/
      end-session.md              # Generates session snapshots
    skills/
      brain-manager/              # Manages brain documentation
        SKILL.md
  brain/                          # ← NEW: Your persistent knowledge base
    00_INDEX.md                   # Master index & bootstrap instructions
    01_PRODUCT_VISION.md          # Product goals, audience, constraints
    02_ARCHITECTURE_OVERVIEW.md   # System architecture, components
    03_DOMAIN_KNOWLEDGE.md        # Trading concepts, Tastytrade API
    10_BACKEND_DESIGN.md          # Services, data models, integrations
    11_FRONTEND_DESIGN.md         # UX flows, components, state
    20_TRADING_LOGIC.md           # Calendar spreads, risk rules
    90_DECISIONS_LOG.md           # Architectural decisions (ADR-style)
    sessions/
      2026-02-05-session-01.md    # Per-session summaries
    README.md                     # Documentation for humans
```

### How It Works

**On Every New Session:**
1. Antigravity loads `.agent/rules/brain-bootstrap.md` (enforced rule)
2. Rule forces agent to read `brain/00_INDEX.md`
3. Agent loads latest session snapshot from `brain/sessions/`
4. Agent asks: "Which area are we working on today?"
5. Agent summarizes current state before accepting new work

**During Session:**
- Agent grounds all answers in brain files
- When learning new information, agent updates relevant brain/*.md files
- Decisions automatically logged to `90_DECISIONS_LOG.md`

**At Session End:**
- Type `/end-session` workflow
- Agent generates snapshot in `brain/sessions/YYYY-MM-DD-session-NN.md`
- Snapshot includes: work summary, file changes, next steps, open questions

**Why This Works:**
- **File-based**: Survives across logins, machines, window closures
- **Version controlled**: Track changes in Git
- **Explicit loading**: Bootstrap rule ensures no session starts "blank"
- **Incremental**: Session snapshots provide fast context recovery

---

## Complete Implementation Plan

I've created a **6-phase implementation plan** with exact file contents, directory structures, and step-by-step instructions. Here's what you'll hand to Antigravity:



---

## Phase Breakdown

### Phase 1: Create Brain Structure (1-2 hours)
- Create `brain/` directory with core knowledge files
- Populate `00_INDEX.md` with bootstrap instructions
- Create initial documentation files:
  - `01_PRODUCT_VISION.md` - TradeMind.bot goals, users, constraints
  - `02_ARCHITECTURE_OVERVIEW.md` - Tech stack, components, data flow
  - `03_DOMAIN_KNOWLEDGE.md` - Options trading, Tastytrade API concepts
  - `20_TRADING_LOGIC.md` - Calendar spread implementation, validation rules
  - `90_DECISIONS_LOG.md` - Architectural decision records

**Key Content Example:**

```markdown
# brain/00_INDEX.md

## Purpose
This directory is the **single source of truth** for all project knowledge.
Every Antigravity session must load this brain at startup to maintain 
continuity across logins, window closures, and different machines.

## For Antigravity Agent:
1. On every new conversation, read this file first
2. Skim headings of all brain/*.md files
3. Ask user which area is relevant
4. Load relevant documents before generating responses
5. Never assume knowledge - always ground answers in these files
```

### Phase 2: Integrate with Antigravity Native Features (30-60 min)

**Create Bootstrap Rule** (`.agent/rules/brain-bootstrap.md`):
```markdown
# Brain Bootstrap Rule

On EVERY new conversation in this workspace:
1. Read brain/00_INDEX.md
2. Load latest session snapshot from brain/sessions/
3. Confirm work area with user
4. Summarize current state before accepting new work
5. Ground all answers in brain files - never invent information

## Why This Rule Exists
- Antigravity sessions don't automatically share memory
- Changing login or closing window loses context
- brain/ is the ONLY persistent knowledge base
```

**Create Session Snapshot Workflow** (`.agent/workflows/end-session.md`):
```markdown
# End Session Workflow

Generate brain/sessions/YYYY-MM-DD-session-NN.md with:
- Session info (date, duration, work area)
- What was accomplished
- Files changed
- Brain updates made
- Known issues
- Next steps
- Questions for next session
```

**Create Brain Manager Skill** (`.agent/skills/brain-manager/SKILL.md`):
```markdown
---
name: brain-manager
description: Manages brain/ knowledge base. Use when updating documentation,
  adding decisions, or reorganizing brain files.
---

When user makes significant decision:
1. Add entry to brain/90_DECISIONS_LOG.md
2. Update related brain files to reflect decision
3. Confirm changes made
```

### Phase 3: Testing & Validation (30 min)

**Test new session bootstrap:**
1. Close all conversations
2. Open new conversation
3. Type: "What's the current status of this project?"
4. ✅ Agent should read brain/00_INDEX.md and summarize from brain files

**Test session snapshots:**
1. Make some changes
2. Type: `/end-session`
3. ✅ Agent should generate `brain/sessions/2026-02-05-session-01.md`

**Test cross-session continuity:**
1. Generate snapshot, close conversation
2. Open new conversation
3. Type: "Continue from where we left off"
4. ✅ Agent should know what was done in previous session

**Test cross-login persistence:**
1. Sign out and back in (or close/reopen Antigravity)
2. Open same workspace
3. ✅ Agent should still load brain correctly

### Phase 4: Migrate Existing Documentation (1-2 hours)

**Find scattered documentation:**
```bash
# Check old Antigravity sessions
ls -lt ~/.gemini/antigravity/brain/

# Read latest session notes
cat ~/.gemini/antigravity/brain/[latest-uuid]/current_issues.md
cat ~/.gemini/antigravity/brain/[latest-uuid]/task_list.md

# Find loose markdown files in project
find . -name "*.md" -not -path "*/node_modules/*"
```

**Consolidate into brain/ files:**
- Extract relevant information from old sessions
- Paste into appropriate brain/*.md files
- Remove redundancy
- Add cross-references between files

**Document current implementation status:**
Add "Current Status" sections to each brain file:
```markdown
## Current Status (as of 2026-02-05)

### Implemented
- OAuth flow with Tastytrade
- Signal approval API endpoint

### In Progress
- Preflight validation implementation

### Not Started
- Stop-loss automation
```

### Phase 5: Optimization & Maintenance (30 min)

**Set up version control:**
```bash
git add brain/ .agent/
git commit -m "feat: add centralized brain knowledge base

- brain/00_INDEX.md with bootstrap instructions
- Core knowledge files
- .agent/rules/brain-bootstrap.md for automatic loading
- .agent/workflows/end-session.md for snapshots"

git push origin main
```

**Sync to cloud (optional):**
- Move workspace to Google Drive/Dropbox for automatic sync
- OR push to Git remote for multi-machine access

**Create maintenance checklist:**
```markdown
## Maintenance Checklist (Monthly)
- [ ] Review all brain/*.md files for accuracy
- [ ] Archive old session snapshots (keep last 10)
- [ ] Split any files over 500 lines
- [ ] Verify bootstrap rule still triggers
```

### Phase 6: Documentation & Handoff (30-60 min)

**Create brain/README.md:**
- Explain brain system to future developers
- Document usage patterns
- Troubleshooting guide

**Update project README:**
```markdown
## Knowledge Management

This project uses a brain/ directory for persistent knowledge.

### Quick Start
1. Open workspace in Antigravity
2. Agent automatically loads brain/00_INDEX.md
3. Start coding with full context

### Workflows
- /end-session - Generate session snapshot
```

**Create brain/HANDOFF.md:**
- Onboarding guide for new developers
- Context transfer protocol for agents
- Emergency recovery procedures

---

## Key Benefits of This Approach

### ✅ **Survives Session Changes**
- Login changes: brain/ is workspace-local, not account-local
- Window closures: brain/ is file-based, persists on disk
- Machine switches: sync via Git/Drive/Dropbox

### ✅ **Explicit Loading**
- Bootstrap rule forces agent to read brain at startup
- No reliance on Antigravity's automatic memory (which is session-scoped)
- Clear visibility into what agent knows

### ✅ **Incremental Context**
- Session snapshots provide fast "pick up where you left off"
- Don't need to re-read entire codebase every time
- Open questions carry forward automatically

### ✅ **Team Collaboration**
- Version-controlled knowledge
- New developers onboard via brain/README.md
- Shared understanding of project state

### ✅ **Extensible**
- Add new brain files as project grows
- Split large files into sub-files
- Integrate with RAG/vector search later if needed

---

## How to Hand This to Antigravity

### Option 1: Full Automation (Recommended)

Open Antigravity in your TradeMind.bot workspace and paste:

```
I need you to implement a centralized brain knowledge base system
for this project to solve session isolation issues. 

Follow the complete implementation plan in the attached markdown file.
Execute all 6 phases:

1. Create brain/ directory structure with initial knowledge files
2. Set up .agent/rules, workflows, and skills for automatic loading
3. Test bootstrap, snapshot generation, and cross-session continuity
4. Migrate all existing documentation from scattered locations
5. Set up Git tracking and maintenance procedures
6. Create documentation and handoff guides

**CRITICAL**: Copy ALL existing documentation from:
- ~/.gemini/antigravity/brain/[latest-uuid]/ session files
- Any loose markdown files in this project
- Previous conversation context from Antigravity Inbox

Consolidate everything into the new brain/ structure.

Start with Phase 1, Task 1.1. After completing each task, 
show me what you created and ask for confirmation before
proceeding to the next task.
```

Then attach the complete plan file (link above).

### Option 2: Step-by-Step with Verification

For each phase:

```
Execute Phase [N] from the brain implementation plan.

Phase [N] tasks:
[Paste specific tasks from plan]

Show me the files you create and their contents.
Wait for my approval before proceeding to Phase [N+1].
```

### Option 3: Manual with Agent Assistance

Create the structure yourself, then ask Antigravity to populate:

```bash
# Create directories
mkdir -p brain/sessions .agent/rules .agent/workflows .agent/skills/brain-manager

# Create files
touch brain/00_INDEX.md
touch brain/01_PRODUCT_VISION.md
touch brain/02_ARCHITECTURE_OVERVIEW.md
touch brain/03_DOMAIN_KNOWLEDGE.md
touch brain/20_TRADING_LOGIC.md
touch brain/90_DECISIONS_LOG.md
touch .agent/rules/brain-bootstrap.md
touch .agent/workflows/end-session.md
touch .agent/skills/brain-manager/SKILL.md
```

Then in Antigravity:
```
I've created the brain/ directory structure per the plan.
Now populate each file with appropriate content based on:
- Our previous conversations about TradeMind.bot
- Tastytrade API implementation
- Calendar spread trading logic
- Architecture decisions we've made

Start with brain/00_INDEX.md. Use the template from the plan
but customize it for TradeMind.bot specifics.
```

---

## Critical Files to Include in Initial Brain

### For TradeMind.bot Specifically:

**`brain/03_DOMAIN_KNOWLEDGE.md`** should include:
- Tastytrade API authentication (OAuth 2.0 flow)
- Order submission endpoint (`POST /accounts/{account}/orders`)
- Preflight checks (buying power, symbol validity, account permissions)
- Dry-run validation endpoint (`/accounts/{account}/orders/dry-run`)
- OCC symbol format requirements (e.g., `SPY   260303P00575000`)
- Common error codes (`422 preflight_check_failure`, `margin_check_failed`)

**`brain/20_TRADING_LOGIC.md`** should include:
- Calendar spread structure (sell near-term, buy far-term)
- Pre-trade validation rules (signal ID, token freshness, market hours)
- Order payload format (time-in-force, order-type, price-effect, legs)
- Error handling strategy (undefined signal ID, token expiration, dry-run failures)
- Risk management rules (position limits, daily trade caps)

**`brain/90_DECISIONS_LOG.md`** should include:
- **2026-02-05**: Centralized brain directory decision
- **2026-02-04**: Tastytrade API dry-run strategy (always validate before real submission)
- **2026-02-02**: No browser storage APIs (SecurityError in sandbox environment)

### Migration from Old Sessions:

When migrating content from `~/.gemini/antigravity/brain/[old-uuid]/`, look for:
- `current_issues.md` - Active problems and blockers
- `task_list.md` - Planned work items
- `plan.md` - Implementation roadmaps
- Any architecture or decision artifacts

Copy these into appropriate brain files or session snapshots.

---

## Troubleshooting

### Agent Still Doesn't Remember Past Sessions

**Possible causes:**
1. Bootstrap rule not triggering
   - **Fix**: Verify `.agent/rules/brain-bootstrap.md` exists
   - **Test**: Type "Read the brain bootstrap rule" to confirm it's loaded

2. Opened different workspace folder
   - **Fix**: Ensure Antigravity opened the EXACT same folder (not a copy)
   - **Test**: Type "What is the current working directory?"

3. Brain files empty
   - **Fix**: Populate brain files with actual content
   - **Test**: Type "Show me the contents of brain/00_INDEX.md"

### Session Snapshots Not Generating

**Possible causes:**
1. Workflow file missing
   - **Fix**: Verify `.agent/workflows/end-session.md` exists
   - **Test**: Type `/` in chat and check if `end-session` appears

2. Agent doesn't have write permissions
   - **Fix**: Check folder permissions: `ls -la brain/sessions/`

3. Workflow not following template
   - **Fix**: Compare your workflow file to template in plan

### Cross-Login Persistence Fails

**Possible causes:**
1. Workspace folder not synced
   - **Fix**: Use Git push/pull or cloud sync (Drive/Dropbox)
   
2. Different machine, different workspace path
   - **Fix**: Clone repo to same relative path or update workspace reference

### Brain Files Out of Date

**Recovery process:**
```bash
# Check Git history
git log --oneline brain/

# Restore from backup
git checkout HEAD~1 -- brain/

# Or regenerate from current code
# Ask Antigravity:
"Analyze the current codebase and update brain/ to match reality"
```

---

## Timeline & Effort

| Phase | Description | Time | Can Parallelize? |
|-------|-------------|------|------------------|
| 1 | Create structure & populate | 1-2 hours | No |
| 2 | Integrate Antigravity features | 30-60 min | No |
| 3 | Testing & validation | 30 min | No |
| 4 | Migrate existing docs | 1-2 hours | Partially |
| 5 | Git setup & maintenance | 30 min | No |
| 6 | Documentation & handoff | 30-60 min | Yes |

**Total: 4-6 hours** for complete implementation.

**Antigravity can automate:** 90% of this (file creation, content population, testing)

**You should verify:** Bootstrap triggering, snapshot quality, migration completeness

---

## Success Criteria Checklist

### ✅ Phase 1 Complete
- [ ] `brain/` directory exists with all core files
- [ ] `00_INDEX.md` has complete document map and bootstrap instructions
- [ ] Initial knowledge files populated with TradeMind.bot specifics
- [ ] All existing documentation migrated into brain files

### ✅ Phase 2 Complete
- [ ] `.agent/rules/brain-bootstrap.md` exists and triggers on new conversations
- [ ] `.agent/workflows/end-session.md` exists and accessible via `/end-session`
- [ ] `.agent/skills/brain-manager/` exists with SKILL.md

### ✅ Phase 3 Complete
- [ ] New session automatically loads brain/00_INDEX.md
- [ ] `/end-session` generates proper snapshot in brain/sessions/
- [ ] Next session loads previous snapshot and knows what was done
- [ ] Cross-login persistence verified (sign out/in or window close/reopen)

### ✅ Phase 4 Complete
- [ ] All scattered docs consolidated (old sessions, loose files, conversation history)
- [ ] Current implementation status documented in brain files
- [ ] No orphaned knowledge outside brain/

### ✅ Phase 5 Complete
- [ ] brain/ tracked in Git with clear commit message
- [ ] Changes synced to remote repository (if using)
- [ ] Maintenance checklist created and documented

### ✅ Phase 6 Complete
- [ ] brain/README.md explains system to humans
- [ ] brain/HANDOFF.md provides onboarding guide
- [ ] Main project README.md references brain system
- [ ] New developer could onboard using brain alone

### ✅ Final Validation
- [ ] Close Antigravity completely
- [ ] Reopen and start new conversation in workspace
- [ ] Agent summarizes project status from brain WITHOUT prompting
- [ ] Ask: "What were we working on last time?" → Agent cites session snapshot

---

## Long-Term Evolution

### Maintenance Routine (Monthly)
1. Review brain files for accuracy
2. Archive old session snapshots (keep last 10)
3. Check for broken cross-references
4. Split any files over 500 lines
5. Update 00_INDEX.md with any new files

### Future Enhancements

**Local RAG Integration (Optional):**
Once brain/ is established, you can layer vector search on top:
```bash
# Embed all brain/*.md files
# Create local vector store (LlamaIndex, Chroma)
# Expose "search brain" command for semantic queries
```

**Global Brain (Multi-Project):**
If you want cross-project memory:
```
~/.gemini/
  GEMINI.md                      # Global rules
  global_brain/
    GLOBAL_INDEX.md              # Cross-project knowledge
    TRADEMIND_BOT.md             # High-level summary + link to workspace brain
    OTHER_PROJECT.md
```

**Automated Snapshot Generation:**
Instead of manual `/end-session`:
```
# .agent/rules/auto-snapshot.md
After every 10 agent messages OR 30 minutes of activity,
automatically generate session snapshot in brain/sessions/
```

**Team Collaboration:**
When multiple developers use Antigravity:
- Each pulls latest brain/ from Git
- Session snapshots show who did what
- Decisions log prevents conflicting changes

---

## Related Resources

### Official Antigravity Documentation
- **Skills**: https://antigravity.google/docs/skills[^41]
- **Rules & Workflows**: https://antigravity.google/docs[^49]
- **GEMINI.md Guide**: https://antigravityai.directory/gemini-md-guide[^62]

### Community Resources
- **Brain directory discovery**: Reddit discussions[^65][^63]
- **Context recovery techniques**: Blog post on extracting Antigravity context[^59]

### Implementation Patterns
- **Progressive Disclosure**: Skills load only when needed[^41]
- **Markdown-based configuration**: All Antigravity configs are markdown[^52]
- **Workspace vs Global scope**: Rules/skills can be project or user-wide[^49]

---

## Final Recommendation

**Start with automated approach:**
1. Hand the complete plan to Antigravity (Option 1 above)
2. Let it execute Phase 1-3 fully
3. Verify bootstrap rule triggers correctly
4. Then supervise Phase 4 (migration) to ensure quality
5. Complete Phase 5-6 for long-term maintainability

**Expected outcome after 4-6 hours:**
- ✅ Never lose context again across sessions
- ✅ Agent knows full project history at conversation start
- ✅ Session snapshots provide fast context recovery
- ✅ Version-controlled knowledge base
- ✅ Multi-machine persistence via Git sync

**First test after implementation:**
Close Antigravity, open tomorrow, start new conversation. Agent should say:
> "I've loaded the brain. According to the latest session snapshot from 2026-02-05, we were working on [X]. The current open issues are [Y]. Which area would you like to continue with today?"

If you see that response, the system is working perfectly.

---

## Questions & Next Steps

**Ready to implement?** Paste the plan into Antigravity and let it execute Phase 1.

**Need customization?** Modify brain file names/structure in plan before starting.

**Want to test manually first?** Create `brain/00_INDEX.md` with a simple note, then ask Antigravity to read it.

The complete implementation plan is ready for Antigravity to code. Let me know if you need any section explained in more detail or want me to generate specific file templates!


---

## References

41. [Authoring Google Antigravity Skills](https://codelabs.developers.google.com/getting-started-with-antigravity-skills) - In this codelab, we will use Antigravity to build Agent Skills, a lightweight, open format for exten...

49. [Undo changes](https://codelabs.developers.google.com/getting-started-google-antigravity) - This codelab guides you through the process of installing and experiencing the features of Google An...

52. [antigravity File Complete Reference Guide](https://antigravityai.directory/antigravity-file-guide) - Master the .antigravity configuration file. Rules, settings, and best practices for Google Antigravi...

59. [Don't lose to Google's Antigravity. How to extract your context ...](https://moghaoui.substack.com/p/hack-dont-lose-to-googles-antigravity) - You have reached the quota limit for Gemini - Solution

62. [GEMINI.md Guide | Global Rules for Google Antigravity IDE](https://antigravityai.directory/gemini-md-guide) - Master the GEMINI.md file - configure global rules for Google Antigravity IDE across all your projec...

63. [Antigravityが重くなった時の会話引き継ぎ方法 - Zero-Shot Log](https://zeroshotlog.com/blog/antigravity-hidden-brain-feature/) - Antigravityで長時間作業すると動作が重くなる現象の対策と、brainディレクトリを使った会話引き継ぎ方法を解説。UUIDを指定するだけで新しいセッションにコンテキストを引き継げます。

65. [Does antigravity keep memory across conversations? - Reddit](https://www.reddit.com/r/google_antigravity/comments/1p8rw3r/does_antigravity_keep_memory_across_conversations/) - Yes there is a persistent memory or at least pretty much every conversation you had "with the IDE". ...


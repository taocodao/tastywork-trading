---
description: Generate session snapshot before ending work
---

# End Session Workflow

Generate a session snapshot to preserve work done in this session.

## Steps

1. Create file `brain/sessions/YYYY-MM-DD-session-NN.md` where:
   - `YYYY-MM-DD` is today's date
   - `NN` is the session number for today (01, 02, etc.)

2. Include these sections in the snapshot:

```markdown
# Session Snapshot - YYYY-MM-DD Session NN

## Date
[Full date]

## Work Summary
[Bullet points of what was accomplished]

## Files Changed
[List of files created, modified, or deleted]

## Brain Updates Made
[Which brain/*.md files were updated]

## Known Issues
[Any bugs or problems discovered]

## Next Steps
[What should be done next session]

## Open Questions
[Anything requiring user input or decision]
```

3. Update `brain/90_DECISIONS_LOG.md` if any significant decisions were made

4. Confirm with user that snapshot looks accurate

## Example Output

```
✅ Session snapshot created: brain/sessions/2026-02-05-session-02.md

Summary:
- Fixed IB Gateway connection issue
- Stopped Docker containers causing wrong trades
- Created workspace-scoped brain structure

Next session should:
- Verify IB connection works at 9:35 AM
- Monitor theta scheduler for successful trades
```

---
description: How to review and document implementation changes
---

## Before Starting Any Implementation

1. Review existing implementation notes to understand prior work:
   ```
   List files in: d:\Projects\tastywork-trading-1\implementation_notes\
   ```

2. Read relevant notes that may impact the current task.

3. Check if there are any known issues or gotchas documented.

---

## After Completing an Implementation

// turbo
1. Create a new implementation note in `d:\Projects\tastywork-trading-1\implementation_notes\`

2. Use the naming format: `YYYY-MM-DD_<short_description>.md`
   - Example: `2026-01-23_oauth_scope_fix.md`

3. Include in the note:
   - **Date**: When the change was made
   - **Status**: Implemented / In Progress / Planned
   - **Problem**: What issue was being solved
   - **Root Cause**: Why the issue occurred
   - **Solution**: What was changed and where
   - **Files Modified**: List of files touched
   - **Deployment Steps**: If applicable (restart services, env vars, etc.)
   - **Prevention**: How to avoid this in the future (if applicable)

4. Commit the note with the related code changes.

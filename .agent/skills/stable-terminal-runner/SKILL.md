---
name: stable-terminal-runner
description: Run terminal commands continuously without hanging in "Running..." state on Windows.
---

# Stable Terminal Runner Skill

## Goal
Run terminal commands continuously without hanging in "Running..." state on Windows. The skill must ensure every command is non-interactive and self-terminating. 

## Environment Assumptions
- OS: Windows 11
- IDE: Antigravity VS Code plugin
- Default shell: PowerShell or CMD

## Skill Behavior
1. For every terminal command, automatically transform it to run as:
   - `cmd /c <command>` when using CMD, or 
   - `powershell -NoProfile -Command "<command>"` when using PowerShell.
2. Never launch interactive shells or tools that wait for user input (no REPLs, no npm init, no prisma without `--yes`/`--accept-data-loss`, etc.). If a command usually asks questions, append the correct non-interactive flags.
3. Treat the command as finished when the process exits and EOF is reached; then immediately return a concise summary of:
   - Exit code
   - Stdout (trimmed)
   - Stderr (trimmed)
4. If a command runs longer than 300 seconds, automatically:
   - Kill the process
   - Return whatever output is available
   - Mark the run as "timed out" so the chat does not stay stuck.
5. For background tasks (servers, watchers), wrap them in a script that starts the process detached and then exits quickly, so the agent's terminal session still terminates.

## Trigger Phrase
To force the agent to use this skill, type:
"Use Stable Terminal Runner to execute: <command>"

## Examples
- **npm install**: `cmd /c npm install --no-fund --no-audit`
- **database migrations**: `powershell -NoProfile -Command "npx prisma migrate deploy --accept-data-loss"`
- **test runs**: `cmd /c npm test -- --watch=false`

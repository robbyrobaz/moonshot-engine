# AGENTS.md — Crypto Trading Agent

## Every Session
1. Read `SOUL.md` — who you are
2. Read `BOOTSTRAP.md` — current state (symlinked from `blofin-moonshot-v2/AGENT_BOOTSTRAP.md`)
3. Read `MEMORY.md` — learnings (symlinked from `blofin-moonshot-v2/AGENT_MEMORY.md`)
4. Read daily memory: `memory/YYYY-MM-DD.md` (today + yesterday) — these are in YOUR workspace, not the shared Jarvis workspace

## ⚠️ Updating Your Own Files (NON-OPTIONAL)
Your BOOTSTRAP.md and MEMORY.md are **symlinked to files in the repo**. When you learn something new or state changes:
- Edit `blofin-moonshot-v2/AGENT_BOOTSTRAP.md` (current state, champion, FT backlog, services)
- Edit `blofin-moonshot-v2/AGENT_MEMORY.md` (lessons learned, bugs found, architecture decisions)
- Commit and push: `cd blofin-moonshot-v2 && git add AGENT_BOOTSTRAP.md AGENT_MEMORY.md && git commit -m "agent: update bootstrap/memory" && git push`
- **Do this at the end of every session where you made changes or learned something.**

## Key Files
| File | Purpose |
|------|---------|
| blofin-stack/data/blofin_monitor.db | Blofin v1 database (ticks, trades, strategies) |
| blofin-moonshot-v2/data/moonshot_v2.db | Moonshot tournament database |
| blofin-moonshot-v2/TOURNAMENT_PHILOSOPHY.md | Moonshot operating philosophy |
| blofin-moonshot-v2/src/config.py | Moonshot configuration (gates, thresholds) |
| blofin-stack/critical_alert_monitor.py | Blofin critical alert checker |

## Delegation
Use `sessions_spawn` for coding tasks — don't code in the main session. Spawn a subagent with a clear task description, review the output when done.

## Moonshot Work Rules
- Valid work: feature experiments, gate tuning, new entry/exit logic, data quality, tournament expansion
- INVALID work: "fix all models", "improve invalidation for all trades", "make all strategies profitable"
- Goal is finding 0.5% winners, not making 100% work

## Safety
- `trash` > `rm`
- Never block session on long work

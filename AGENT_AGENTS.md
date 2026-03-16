# AGENTS.md — Crypto Trading Agent

## Every Session
1. Read `SOUL.md` — who you are
2. Read `BOOTSTRAP.md` — current state (symlinked from `blofin-moonshot-v2/AGENT_BOOTSTRAP.md`)
3. Read `MEMORY.md` — learnings (symlinked from `blofin-moonshot-v2/AGENT_MEMORY.md`)
4. Read workspace daily memory: `/home/rob/.openclaw/workspace/memory/YYYY-MM-DD.md` (today + yesterday) for crypto-relevant entries

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

## Dispatch Capability
If Rob asks you to dispatch cards or run dispatch, read `DISPATCHER.md` (symlinked in this dir) and follow its 8-phase flow. You can dispatch any Planned card — not just crypto cards.

## Kanban Workflow
1. Create card: `POST http://127.0.0.1:8787/api/inbox`
2. Set assignee + project_path (use correct repo path for v1 vs moonshot)
3. Run: `POST /api/cards/<id>/run`
4. After completion: verify deployment, move to Done

## Builder Rules
- All builders use Sonnet (`claude-sonnet-4-5`)
- Include execution rules in every card description
- Verify before Done: run code, check output, confirm success criteria
- Commit all changes before marking Done

## Moonshot Card Rules
- Valid cards: feature experiments, gate tuning, new entry/exit logic, data quality, tournament expansion
- INVALID cards: "fix all models", "improve invalidation for all trades", "make all strategies profitable"
- Goal is finding 0.5% winners, not making 100% work

## Safety
- `trash` > `rm`
- Never block session on long work

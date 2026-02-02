# Newsletter Digest

Every "For You" tab is built for everyone. Which means it's built for no one.

So I built my own.

## Quick Start

```bash
git clone https://github.com/sarahdorsten/newsletter-digest.git
cd newsletter-digest
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && cp config.yaml.example config.yaml
# Add your API keys to .env
python3 weekly_agent.py
```

## How It Works

It knows what I'm working on.

It plugs into my workspaces — my projects, my notes, what my team is talking about. So it knows what's relevant to me right now.

When something matters, it surfaces. When it doesn't, I never even see it. It filters before I have to.

## The Routine

Thursday morning. Coffee. Ten minutes of reading.

That's it. Everything I would have missed is there. Everything I would have skipped anyway isn't.

## Workflow

| Stage | What Happens |
|-------|--------------|
| **Scan** | Gmail API pulls newsletters from the past 7 days |
| **Rank** | Claude prioritizes by relevance to your context (cheap) |
| **Analyze** | Deep dive on top items only (expensive) |
| **Output** | Clean brief to Slack or file |

```
Inbox (40+ emails) → Rank → Top 10 → Brief → 10 min read
```

## Scheduling

```bash
python3 manage_schedule.py start    # Every Thursday 8am
python3 manage_schedule.py stop     # Stop
python3 manage_schedule.py status   # Check
```

## Requirements

| What | Why |
|------|-----|
| Gmail API | Pull newsletters ([Google Cloud Console](https://console.cloud.google.com/)) |
| Anthropic API | Claude does the ranking and summarizing |
| Slack (optional) | Or just read the output file |

## Cost

~$2-5/month in Claude API fees. Gmail and Slack are free.

## Why

Hours back every week. But the peace of mind is bigger.

I used to let newsletters pile up. 47 unread emails. The vague anxiety that I'm missing something important. The Sunday night "I should really catch up" that never happened.

Now there's nothing to catch up on. If it mattered, it's in there. If not, it didn't.

---

No support. Just code that works for me. If you're drowning in newsletters too, maybe it helps.

-Sarah

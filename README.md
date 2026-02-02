# Newsletter Digest

40+ newsletters in my inbox every week. Most are noise.

Only 3-4 actually matter. But you have to read through all 40+ to find them.

So I built this. Scans Gmail for AI newsletters, ranks by relevance, posts a weekly summary to Slack.

Hours back every week. But the peace of mind is bigger.

## What It Does

Runs once a week (Thursdays at 8 AM). Does four things:

1. **Scans Gmail** - Pulls newsletters from the past 7 days
2. **Ranks everything** - Quick prioritization of all emails (cheap)
3. **Deep-dives top items** - Full analysis of what matters (expensive)
4. **Posts to Slack** - Clean summary with sources

Two-stage pipeline keeps costs low. Stage 1 ranks all emails fast. Stage 2 does expensive analysis on only the top items.

## Setup

**You'll need:**
- Gmail API access (Google Cloud setup)
- Slack workspace and bot token
- Anthropic API key for Claude
- About an hour to get it running

**Steps:**

1. Clone this repo
2. Install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Set up Gmail API:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project
   - Enable Gmail API
   - Create OAuth 2.0 credentials (Desktop app)
   - Download credentials → save as `credentials.json`

4. Set up Slack:
   - Create a Slack App at [api.slack.com/apps](https://api.slack.com/apps)
   - Add bot token scopes: `chat:write`, `channels:read`
   - Install app to your workspace
   - Copy Bot User OAuth Token

5. Configure:
   ```bash
   cp .env.example .env
   cp config.yaml.example config.yaml
   ```
   - Add your keys to `.env`
   - Edit `config.yaml` to match YOUR newsletters

6. Run it:
   ```bash
   python3 weekly_agent.py
   ```

First run will open a browser to authenticate Gmail. After that it's automatic.

## Cost

~$2-5/month in Anthropic API fees. Depends how many newsletters you scan.

Gmail API is free (under quota). Slack is free.

## What to Change

The Gmail query in `config.yaml` is set for AI newsletters. Change it to match what YOU want to track.

The Slack channel defaults to `#ai-brief`. Set `SLACK_CHANNEL` in `.env` to change it.

## Scheduling

To run automatically every Thursday:

```bash
python3 manage_schedule.py start    # Start automated runs
python3 manage_schedule.py stop     # Stop automated runs
python3 manage_schedule.py status   # Check if running
python3 manage_schedule.py test     # Test run now
```

## No Support

This is the code that works for me. No guarantees. No support.

If you're drowning in newsletters too, maybe it helps. If not, at least you can see how it's built and make your own version.

## How It Works

`weekly_agent.py` - Main script. Fetches emails, ranks them, generates summary, posts to Slack.

`gmail_ingest.py` - Gmail API wrapper. Handles authentication, fetching, parsing.

`slack_post.py` - Slack API wrapper. Formats markdown, handles threading, posts messages.

`manage_schedule.py` - Scheduling utility for macOS (uses launchd).

`config.yaml` - Gmail query and settings.

`.env` - API keys (don't commit this).

That's it. Three API calls (Gmail, Claude, Slack) and some glue code.

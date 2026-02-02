# Newsletter Digest

Every "For You" tab is built for everyone. Which means it's built for no one.

So I built my own.

---

It knows what I'm working on.

It plugs into my workspaces — my projects, my notes, what my team is talking about. So it knows what's relevant to me right now.

When something matters, it surfaces. When it doesn't, I never even see it. It filters before I have to.

---

Thursday morning. Coffee. Ten minutes of reading.

That's it. That's the whole routine now. Everything I would have missed is there. Everything I would have skipped anyway isn't.

---

Hours back every week. But the peace of mind is bigger.

I used to let newsletters pile up. 47 unread emails. The vague anxiety that I'm missing something important. The Sunday night "I should really catch up" that never happened.

Now there's nothing to catch up on. If it mattered, it's in there. If not, it didn't.

---

## Setup

Python. Gmail API. Claude. About an hour to get it running.

```bash
# 1. Clone and install
git clone https://github.com/sarahdorsten/newsletter-digest.git
cd newsletter-digest
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
cp config.yaml.example config.yaml
# Add your API keys to .env
# Edit config.yaml to match YOUR newsletters

# 3. Run
python3 weekly_agent.py
```

**You'll need:**
- Gmail API credentials ([Google Cloud Console](https://console.cloud.google.com/) → Enable Gmail API → OAuth 2.0 Desktop credentials)
- Anthropic API key
- Slack bot token (optional — or just read the output file)

First run opens a browser for Gmail auth. After that it's automatic.

---

## Scheduling

```bash
python3 manage_schedule.py start    # Run every Thursday 8am
python3 manage_schedule.py stop     # Stop
python3 manage_schedule.py status   # Check
```

---

## Cost

~$2-5/month in Claude API fees. Gmail and Slack are free.

---

## No Support

This is code that works for me. No guarantees. No support.

If you're drowning in newsletters too, maybe it helps.

-Sarah

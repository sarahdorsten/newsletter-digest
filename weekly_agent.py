#!/usr/bin/env python3
# weekly_agent.py - Simple weekly AI brief: 30-day email sweep + team context → Slack

import os
import pathlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import yaml
from anthropic import Anthropic
from dotenv import load_dotenv

from gmail_ingest import fetch_newsletters
from slack_post import SlackBriefPoster

load_dotenv()

ROOT = pathlib.Path(__file__).parent
# Point to Pulse folder for team context
PULSE_DIR = pathlib.Path.home() / "Desktop/library/design-projects/vaults/pulse"
CONTEXT_DIR = PULSE_DIR / "context"

def get_thursday_window():
    """
    Calculate Thu→Thu window for weekly brief (America/Denver timezone).
    Returns dict with start/end dates and formatted string for display.
    """
    tz = ZoneInfo("America/Denver")
    now = datetime.now(tz)

    # Use current week ending today for fresh news
    end_date = now
    start_date = end_date - timedelta(days=7)

    # Format for display: "Oct 31–Nov 7"
    if start_date.month == end_date.month:
        date_str = f"{start_date.strftime('%b %d')}–{end_date.strftime('%d')}"
    else:
        date_str = f"{start_date.strftime('%b %d')}–{end_date.strftime('%b %d')}"

    return {
        "start": start_date,
        "end": end_date,
        "display": date_str,
        "start_ms": int(start_date.timestamp() * 1000),
        "end_ms": int(end_date.timestamp() * 1000)
    }

def load_team_context() -> str:
    """Load team context files from Pulse folder for curation lens"""
    context_parts = []

    # Team overview from Pulse
    team_file = CONTEXT_DIR / "team-overview.md"
    if team_file.exists():
        context_parts.append(f"TEAM CONTEXT:\n{team_file.read_text(encoding='utf-8')[:10000]}")
    else:
        print(f"⚠️  Team overview not found: {team_file}")

    # Latest 3 meeting notes from Pulse
    meet_dir = CONTEXT_DIR / "meet"
    if meet_dir.exists():
        # Get 3 newest files by modification time
        meet_files = sorted(meet_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:3]
        if meet_files:
            meeting_context = []
            for f in meet_files:
                meeting_context.append(f"MEETING: {f.name}\n{f.read_text(encoding='utf-8')[:4000]}")
            context_parts.append("RECENT MEETINGS:\n" + "\n---\n".join(meeting_context))
        else:
            print(f"⚠️  No meeting notes found in {meet_dir}")
    else:
        print(f"⚠️  Meeting directory not found: {meet_dir}")

    if not context_parts:
        print("⚠️  No context loaded - check Pulse folder paths")
        return "No team context available."

    return "\n\n".join(context_parts)

def load_previous_briefs() -> str:
    """Load recent brief history to avoid repetition and build continuity"""
    weekly_dir = ROOT / "summaries" / "weekly"
    if not weekly_dir.exists():
        return "No previous briefs found."
    
    # Get the 3 most recent weekly briefs
    brief_files = sorted(weekly_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:3]
    
    if not brief_files:
        return "No previous briefs found."
    
    brief_summaries = []
    for brief_file in brief_files:
        try:
            content = brief_file.read_text(encoding='utf-8')
            # Extract key topics/tools mentioned for continuity
            lines = content.split('\n')
            brief_summary = f"FILE: {brief_file.name}\n"
            
            # Get the main sections to understand what was covered
            current_section = None
            key_points = []
            
            for line in lines[:50]:  # First 50 lines should cover main content
                if line.startswith('## '):
                    current_section = line.strip()
                elif line.startswith('• ') and current_section:
                    # Extract the main topic from each bullet
                    topic = line.split('•')[1].strip().split('→')[0].strip()
                    if len(topic) > 10:  # Only meaningful topics
                        key_points.append(f"{current_section}: {topic[:100]}")
            
            brief_summary += "\n".join(key_points[:8])  # Top 8 key points
            brief_summaries.append(brief_summary)
            
        except Exception as e:
            print(f"Warning: Could not read {brief_file}: {e}")
            continue
    
    return "\n\n---\n\n".join(brief_summaries)

def generate_weekly_brief() -> str:
    """Generate weekly brief from emails + context"""

    # 1. Calculate Thu→Thu window
    window = get_thursday_window()
    print(f"📅 Coverage window: {window['display']}")

    # 2. Load configuration
    config = yaml.safe_load((ROOT / "config.yaml").read_text())

    # 3. Load team context
    team_context = load_team_context()

    # 4. Load previous briefs for continuity
    print("📚 Loading previous brief history...")
    previous_briefs = load_previous_briefs()

    # 5. Fetch emails from Thu→Thu window (using 30-day buffer for safety)
    print(f"📧 Fetching emails from last 30 days (filtering to {window['display']})...")
    emails = fetch_newsletters({"mode": "days", "days": 30}, config["news_query"])

    # Filter to Thu→Thu window
    emails = [e for e in emails if window['start_ms'] <= e['internal_ts'] <= window['end_ms']]
    print(f"📊 Found {len(emails)} emails in {window['display']} window")

    # 6. Two-stage processing to handle ALL emails
    if len(emails) > 20:
        print(f"🤖 Using two-stage processing for all {len(emails)} emails...")
        
        # STAGE 1: Quick prioritization scan of ALL email titles
        print("Stage 1: Prioritizing emails by relevance...")
        email_headers = [{
            "title": email["title"],
            "source": email["source"],
            "date": email["date"][:10],  # Just date, not time
            "index": i
        } for i, email in enumerate(emails)]
        
        # Initialize anthropic client for priority analysis
        anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        
        priority_prompt = f"""You are filtering AI emails for a design/development consultancy team focused on systematic AI workflows.

TEAM FOCUS: {team_context[:2000]}

EMAIL HEADERS TO PRIORITIZE:
{yaml.dump(email_headers, default_flow_style=False)}

Return JSON with two lists:
{{
  "high_priority": [0, 5, 12, ...],  // indexes of most relevant emails
  "medium_priority": [2, 8, 15, ...]  // indexes of somewhat relevant emails
}}

Prioritize emails about: tools/workflows, agent orchestration, systematic approaches, practical implementations, JASON FRIED content.
Give HIGHEST priority to: Jason Fried tweets/content, major tool updates, workflow insights from team's existing tools.
Skip: pure research, consumer features, general AI hype.

BIAS TOWARD RECENT CONTENT: Give extra weight to emails from the last 7 days for breaking developments."""
        
        priority_response = anthropic_client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=800,
            temperature=0,
            messages=[{"role": "user", "content": priority_prompt}]
        )
        
        priority_text = "".join(getattr(b, "text", "") for b in priority_response.content)
        
        # Parse priority response
        import json
        try:
            start = priority_text.find("{")
            end = priority_text.rfind("}") + 1
            priorities = json.loads(priority_text[start:end])
            high_priority_indexes = priorities.get("high_priority", [])
            medium_priority_indexes = priorities.get("medium_priority", [])
            
            print(f"✅ Identified {len(high_priority_indexes)} high-priority + {len(medium_priority_indexes)} medium-priority emails")
        except:
            print("⚠️  Priority parsing failed, using chronological order")
            high_priority_indexes = list(range(min(15, len(emails))))
            medium_priority_indexes = list(range(15, min(25, len(emails))))
        
        # STAGE 2: Deep analysis of prioritized emails
        print("Stage 2: Deep analysis of prioritized emails...")
        priority_emails = [emails[i] for i in high_priority_indexes[:20]]  # Top 20 for deep analysis
        summary_emails = [emails[i] for i in medium_priority_indexes[:10]]   # Next 10 for brief summary
        
        # Prepare detailed data for priority emails
        email_data = []
        for email in priority_emails:
            email_data.append({
                "title": email["title"],
                "source": email["source"], 
                "date": email["date"],
                "text": email["text"][:3000],
                "url": email.get("web_link") or email.get("gmail_link")
            })
        
        # Add brief summaries of medium priority
        summary_data = []
        for email in summary_emails:
            summary_data.append({
                "title": email["title"],
                "source": email["source"], 
                "date": email["date"],
                "brief_text": email["text"][:500]  # Much shorter for summary
            })
        
        print(f"🔍 Processing {len(email_data)} emails in detail + {len(summary_data)} email summaries")
        
    else:
        print(f"✅ Processing all {len(emails)} emails found")
        # Simple processing for smaller batches
        email_data = []
        summary_data = []
        for email in emails:
            email_data.append({
                "title": email["title"],
                "source": email["source"], 
                "date": email["date"],
                "text": email["text"][:3000],
                "url": email.get("web_link") or email.get("gmail_link")
            })
    
    # 7. Generate brief with Claude
    anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    prompt = f"""You are writing a weekly AI brief in the voice of Jason Fried.

VOICE & STYLE — THIS IS CRITICAL:

Jason Fried writes like he talks. Calm confidence. No hedging. Short sentences that land. He states things as facts, then lets you sit with them.

From his writing:
> "What was simple is now complicated. What was clear is now cluttered. What just worked now takes work."
> "Delegating to competency lets you forget about it completely. That's real leverage."
> "Lag is the giveaway that the system is working too hard for too little."

RULES:
1. Cut 70% of the words. If it can be shorter, make it shorter.
2. Specific over abstract. "Claude Code grew up" not "The tools are settling"
3. Let the reader figure it out. NO "what this means for you" sections. Just state the thing.
4. End with a punch. Last sentence of each section should land. Period does the work.
5. Calm, not excited. No exclamation points. No "game-changing" or "revolutionary."
6. NO bullet points for steps. Collapse to one line.
7. NO time estimates. NO "Solves:" labels.
8. NO "Worth watching:" — if it's worth watching, say why in the prose.

WORDS TO NEVER USE:
- "comprehensive" — cut it
- "significant" — be specific instead
- "utilize" — say "use"
- "leverage" — say "use"
- "implement" — say "build" or "add"
- "facilitate" — say "help" or cut
- "In order to" — just say what happens
- "It's important to note that" — cut entirely
- "This is significant because" — just state the significance

TEAM CONTEXT (for relevance filtering, not for explicit mention):
{team_context[:3000]}

PREVIOUS BRIEFS (avoid repetition):
{previous_briefs[:2000]}

NEWSLETTERS FROM {window['display'].upper()}:
{yaml.dump(email_data, default_flow_style=False)[:12000]}

---

OUTPUT FORMAT — FOLLOW EXACTLY:

# [Headline grounded in specific content]

The headline must be specific. Not "AI Tools Mature" — instead "Claude Code grew up and now other tools can follow"
Formula: [Specific thing that happened] + [what it means]

## What Actually Happened

**[Most important thing. Bold, declarative, like a headline].** (Date)

[2-3 short paragraphs. State facts with confidence. No "What it is:" labels. End with insight, not summary. The last sentence should punch.]

**[Second thing].** (Date)

[1-2 paragraphs. Shorter than the first. End with punch.]

**[Third thing].** (Date)

[1-2 paragraphs. Can be very brief. End with punch.]

---

## Worth Your Attention

**[Topic as conversational hook, not formal title]** (Date)

[2-3 sentences. The point, not the details. Trust the reader.]

**[Topic]** (Date)

[1-2 sentences. Even shorter.]

**[Topic]**

[One sentence is fine.]

---

## Things to Try

**[Action in bold].** [One sentence of context. No bullet points. Simple.]

**[Action].** [Context.]

**[Action].** [Context.]

---

## The Pattern

[The meta-insight in 2-3 sentences. What did this week reveal about where things are going? End with punch.]

---

*Sources: [comma-separated list]*

---

EXAMPLE OF CORRECT VOICE:

BAD (verbose, labeled):
**Claude Code Updates** (Jan 22-29)
**What it is:** Anthropic released several updates to Claude Code this week including VS Code extension GA, a new desktop app called Cowork, and a diff viewer on web.
**What it means for you:** This represents a significant maturation of the tooling. Teams should consider...

GOOD (Jason Fried voice):
**Claude Code grew up.** (Jan 22-29)
Anthropic shipped a lot this month. The VS Code extension hit general availability. A desktop app called Cowork launched for non-coding tasks. A diff viewer showed up on web.
But here's what matters: these aren't features for early adopters anymore. They're features for everyone else. Less configuration, more just working.

BAD (bullet list):
**Set up Claude Code in VS Code** → Solves: Development workflow → Time: 30 min
• Download the extension
• Configure your API key
• Start with @-mentioning files

GOOD (collapsed, punchy):
**Set up Claude Code in VS Code.** Now GA. Start with @-mentioning files for context. Use slash commands. Simple.

---

FINAL CHECK — Before outputting, ask:
1. Would Jason Fried write this? If it sounds corporate, rewrite.
2. Can I cut more? If yes, cut.
3. Does each section end with a punch?
4. Did I explain too much? Trust the reader."""

    response = anthropic_client.messages.create(
        model="claude-3-7-sonnet-20250219",
        max_tokens=8000,  # Increased for more thorough analysis
        temperature=0.3,  # Slight creativity for better connections
        messages=[{"role": "user", "content": prompt}]
    )
    
    brief_text = "".join(getattr(b, "text", "") for b in response.content)
    return brief_text, window

def main():
    """Generate and post weekly brief"""
    try:
        print("🤖 Generating weekly AI brief...")

        # Generate brief
        brief, window = generate_weekly_brief()

        # Save to file (original location)
        weekly_dir = ROOT / "summaries" / "weekly"
        weekly_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{datetime.now().strftime('%Y-%m-%d')}-weekly.md"
        output_file = weekly_dir / filename
        output_file.write_text(brief, encoding="utf-8")

        print(f"✅ Brief saved: {output_file}")

        # Also save to Pulse workflow for Obsidian
        pulse_newsletter_dir = PULSE_DIR / "context" / "newsletter"
        pulse_newsletter_dir.mkdir(parents=True, exist_ok=True)
        pulse_output_file = pulse_newsletter_dir / filename
        pulse_output_file.write_text(brief, encoding="utf-8")

        print(f"📝 Brief also saved to Pulse: {pulse_output_file}")

        # Post to Slack with date window
        poster = SlackBriefPoster()
        thread_ts = poster.post_brief(brief, str(output_file), window['display'])
        print(f"🧵 Posted to Slack: {thread_ts}")

        return str(output_file)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    main()

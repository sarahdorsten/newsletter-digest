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

    prompt = f"""You are the Weekly AI Brief Agent creating a deeply personalized AI industry analysis for this specific team.

TEAM CONTEXT - USE THIS TO CONNECT EVERYTHING:
{team_context}

PREVIOUS BRIEF HISTORY (for continuity, avoid pure repetition):
{previous_briefs[:4000]}

NEWSLETTERS & CONTENT FROM {window['display'].upper()}:
{yaml.dump(email_data, default_flow_style=False)[:12000]}

Your job: Transform these newsletters into actionable intelligence for THIS specific team. Every item must answer: "What does this mean for OUR work, OUR clients, OUR tools?"

# Weekly AI Brief — {window['display']}

## What this means for your team

Create 6-10 deeply analyzed items that connect news/developments to the team's specific context, projects, discussions, and needs.

For EACH item, use this format:

**[Clear headline of the news/development]** (Source, Date)

**What it is:**
[Explain what the news/development actually IS - the facts, what changed, what was announced. Keep this objective and descriptive.]

**What it means for you:**
[Connect it to team context - how it relates to their work, discussions, projects, philosophies. Include specific, concrete implications.]

EXAMPLE:
**Claude Code's dual-mode approach** (Every, Nov 14)

**What it is:**
Every's workshop highlighted how Claude Code combines "buttons" (slash commands) with "bash" (full flexibility). This dual-mode design lets users start with structured commands but doesn't constrain power users who need custom workflows.

**What it means for you:**
This validates Michael's insight about the sweet spot between Cora's rigid structure and complete flexibility. Your team identified this exact pattern in your Nov 6 discussion about deterministic workflows - providing structured starting points that don't become prisons. Apply this pattern to your own tool development by providing clear slash commands for common actions while preserving natural language flexibility for custom needs.

RULES FOR THIS SECTION:
- Mine the team context deeply - reference their specific projects, tools they use, problems they're solving, philosophies they follow
- Connect dots between multiple sources if relevant (e.g., "This validates Michael's insight about..." or "This builds on Sarah's experiment with...")
- Be specific about WHO on the team, WHAT project, WHICH problem this relates to
- Include concrete next steps or implications in the "Impact for you" line
- Prioritize HIGH-SIGNAL content: Jason Fried tweets, major tool updates, workflow insights, practical implementations
- Skip generic AI news that doesn't connect to their actual work

## Worth keeping an eye on

2-4 emerging patterns, early-stage developments, or trends that aren't immediately actionable but could matter soon.

For EACH item:
**[Trend or development]** (Source, Date)
[1-2 paragraphs explaining what it is and why it matters]
→ Worth watching: [Specific reason this team should track it]

RULES:
- Still connect to team context, but these are "watch this space" items
- Focus on early signals, not established facts
- Explain the potential future impact

## Things to try this week

3-5 concrete, specific experiments or actions the team could take based on this week's news.

For EACH:
**[Action item]** → Solves: [Specific team problem] → Time: [Estimate]
• [2-3 bullet points with concrete steps]

RULES:
- Make these VERY specific to the team's actual context and problems
- Reference actual team members, projects, or discussions when relevant
- Give realistic time estimates (15-60 min range usually)
- Focus on high-leverage, low-effort experiments

---
**Sources:** [List all sources: newsletters, team meetings, specific emails]

CRITICAL RULES:
- EVERY item must explicitly connect to team context - no generic summaries
- Use team member names when relevant (Michael, Musa, Sarah, etc.)
- Reference specific team concepts/language ("fossil chat," "buttons vs bash," "deterministic workflows," etc.)
- Prioritize JASON FRIED content very highly - his tweets are labeled high-signal
- Include dates for all items
- Be specific and actionable, not abstract
- The newsletter should feel like it was written by someone who deeply knows this team's work
- Aim for 8-12 substantial items in "What this means for your team" - don't be brief, be thorough"""

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

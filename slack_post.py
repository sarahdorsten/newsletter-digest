# slack_post.py - Post AI briefs to Slack and handle threaded conversations
import os
import pathlib
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

load_dotenv()

class SlackBriefPoster:
    def __init__(self):
        self.token = os.getenv("SLACK_BOT_TOKEN")
        if not self.token:
            raise ValueError("SLACK_BOT_TOKEN not found in environment variables")
        self.client = WebClient(token=self.token)
        self.channel = os.getenv("SLACK_CHANNEL", "#ai-brief")  # Default channel
    
    def post_brief(self, brief_content: str, brief_file_path: str = None, date_window: str = None) -> str:
        """
        Post a brief to Slack and return the thread timestamp for replies.

        Args:
            brief_content: The markdown content of the brief
            brief_file_path: Optional path to the brief file for reference
            date_window: Optional date window display string (e.g., "Oct 31–Nov 7")

        Returns:
            thread_ts: The timestamp of the posted message (for threading)
        """
        try:
            # Check if this brief was already posted
            if brief_file_path and self._already_posted(brief_file_path):
                print(f"⏭️  Brief already posted to Slack, skipping")
                return None

            # Split content into main brief and sources
            main_content, sources_content = self._split_brief_and_sources(brief_content)

            # Convert markdown to Slack-friendly format
            slack_formatted = self._format_for_slack(main_content)

            # Create a nice header message with date window
            if date_window:
                header = f"📊 *AI Pulse Brief* — Coverage: {date_window}"
                # Add web brief link (localhost for v1 - deploy to real URL later)
                # Extract date from brief_file_path for web URL
                if brief_file_path:
                    brief_date = brief_file_path.split('/')[-1].replace('-weekly.md', '')
                    header += f"\n🔗 <http://localhost:5001/brief/{brief_date}|Read full brief on web>"
            else:
                timestamp = datetime.utcnow().strftime("%B %d, %Y at %H:%M UTC")
                header = f"🤖 *AI Builder Brief* — {timestamp}"

            if brief_file_path and not date_window:
                header += f"\n📄 _Saved to:_ `{brief_file_path.split('/')[-1]}`"
            
            # Check if content needs to be split due to Slack's 4000 char limit
            full_message = header + "\n\n" + slack_formatted
            
            if len(full_message) > 3900:  # Leave some buffer
                # Split the content intelligently at section boundaries
                sections = self._split_at_sections(slack_formatted)
                
                # Post header with first section
                response = self.client.chat_postMessage(
                    channel=self.channel,
                    text=header + "\n\n" + sections[0],
                    mrkdwn=True
                )
                thread_ts = response["ts"]
                
                # Post remaining sections as threaded replies
                for section in sections[1:]:
                    self.client.chat_postMessage(
                        channel=self.channel,
                        text=section,
                        thread_ts=thread_ts,
                        mrkdwn=True
                    )
            else:
                # Post as single message
                response = self.client.chat_postMessage(
                    channel=self.channel,
                    text=full_message,
                    mrkdwn=True
                )
                thread_ts = response["ts"]
            
            # Post sources as a threaded reply
            if sources_content:
                sources_formatted = self._format_for_slack(sources_content)
                self.client.chat_postMessage(
                    channel=self.channel,
                    text=f"📚 *Sources*\n{sources_formatted}",
                    thread_ts=thread_ts,
                    mrkdwn=True
                )
            
            # Mark this brief as posted
            if brief_file_path:
                self._mark_as_posted(brief_file_path)
            
            print(f"✅ Brief posted to Slack channel {self.channel}")
            print(f"📚 Sources posted as thread reply")
            print(f"🧵 Thread ID: {thread_ts}")
            return thread_ts
            
        except SlackApiError as e:
            print(f"❌ Error posting to Slack: {e.response['error']}")
            if e.response['error'] == 'channel_not_found':
                print(f"   Make sure the channel {self.channel} exists and the bot is invited to it")
            elif e.response['error'] == 'not_in_channel':
                print(f"   Invite the bot to {self.channel} with: /invite @your-bot-name")
            raise
    
    def _format_for_slack(self, markdown_content: str) -> str:
        """
        Convert markdown to Slack-friendly formatting.
        """
        lines = markdown_content.split('\n')
        formatted_lines = []
        
        for line in lines:
            # Handle headers
            if line.startswith('# '):
                formatted_lines.append(f"*{line[2:].strip()}*")
            elif line.startswith('## '):
                formatted_lines.append(f"\n*{line[3:].strip()}*")
            elif line.startswith('### '):
                formatted_lines.append(f"\n_{line[4:].strip()}_")
            # Handle bullet points
            elif line.startswith('- '):
                # Convert [n] citations to links if possible
                bullet_text = line[2:].strip()
                formatted_lines.append(f"• {bullet_text}")
            # Handle horizontal rules
            elif line.strip() == '---':
                formatted_lines.append("\n━━━━━━━━━━━━━━━━━━━━\n")
            # Handle bold markdown
            elif '**' in line:
                # Convert **text** to *text* for Slack
                converted = line.replace('**', '*')
                formatted_lines.append(converted)
            # Regular lines
            elif line.strip():
                formatted_lines.append(line)
            else:
                formatted_lines.append("")
        
        return '\n'.join(formatted_lines)
    
    def _split_brief_and_sources(self, content: str) -> tuple[str, str]:
        """
        Split the brief content into main content and sources section.
        """
        lines = content.split('\n')
        sources_start = -1
        
        # Find where sources section starts
        for i, line in enumerate(lines):
            if line.strip() == '---' or line.strip().startswith('**Sources'):
                sources_start = i
                break
        
        if sources_start == -1:
            # No sources section found
            return content, ""
        
        main_content = '\n'.join(lines[:sources_start]).strip()
        sources_content = '\n'.join(lines[sources_start:]).strip()
        
        return main_content, sources_content
    
    def _split_at_sections(self, content: str, max_length: int = 3800) -> list[str]:
        """
        Split content at section boundaries to keep related content together.
        """
        lines = content.split('\n')
        sections = []
        current_section = ""
        
        for line in lines:
            # Check if this is a new section header
            if line.strip().startswith('*') and not current_section:
                # First section, start building
                current_section = line + '\n'
            elif line.strip().startswith('*') and current_section:
                # New section header, finish current section
                if current_section.strip():
                    sections.append(current_section.strip())
                current_section = line + '\n'
            else:
                # Add to current section
                potential_section = current_section + line + '\n'
                
                # If adding this line would exceed limit, finish section
                if len(potential_section) > max_length and current_section.strip():
                    sections.append(current_section.strip())
                    current_section = line + '\n'
                else:
                    current_section = potential_section
        
        # Add the last section
        if current_section.strip():
            sections.append(current_section.strip())
        
        # If no sections were found, fall back to simple splitting
        if not sections:
            return self._split_content(content, max_length)
        
        return sections
    
    def _already_posted(self, brief_file_path: str) -> bool:
        """
        Check if this brief file has already been posted to Slack.
        """
        posted_file = pathlib.Path(brief_file_path + ".slack_posted")
        return posted_file.exists()
    
    def _mark_as_posted(self, brief_file_path: str):
        """
        Mark this brief file as posted to Slack.
        """
        posted_file = pathlib.Path(brief_file_path + ".slack_posted")
        posted_file.write_text(datetime.utcnow().isoformat(), encoding="utf-8")
    
    def _split_content(self, content: str, max_length: int = 3500) -> list[str]:
        """Split content into chunks that fit within Slack's message limits."""
        if len(content) <= max_length:
            return [content]
        
        chunks = []
        lines = content.split('\n')
        current_chunk = ""
        
        for line in lines:
            # If adding this line would exceed the limit, start a new chunk
            if len(current_chunk) + len(line) + 1 > max_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = line + '\n'
                else:
                    # Single line is too long, force split
                    chunks.append(line[:max_length])
                    current_chunk = line[max_length:] + '\n'
            else:
                current_chunk += line + '\n'
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def reply_to_thread(self, thread_ts: str, message: str) -> bool:
        """
        Reply to a specific thread (useful for follow-up responses).
        
        Args:
            thread_ts: The timestamp of the original thread message
            message: The reply message
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.client.chat_postMessage(
                channel=self.channel,
                text=message,
                thread_ts=thread_ts,
                mrkdwn=True
            )
            return True
        except SlackApiError as e:
            print(f"❌ Error replying to thread: {e.response['error']}")
            return False


def post_brief_to_slack(brief_file_path: str) -> str:
    """
    Convenience function to post a brief file to Slack.
    
    Args:
        brief_file_path: Path to the markdown brief file
    
    Returns:
        thread_ts: The thread timestamp for follow-up conversations
    """
    with open(brief_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    poster = SlackBriefPoster()
    return poster.post_brief(content, brief_file_path)


if __name__ == "__main__":
    # Test posting the latest brief
    import pathlib
    briefs_dir = pathlib.Path(__file__).parent / "briefs"
    latest_brief = briefs_dir / "latest.md"
    
    if latest_brief.exists():
        post_brief_to_slack(str(latest_brief))
    else:
        print("No latest.md found. Run python brief.py first.")

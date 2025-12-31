#!/usr/bin/env python3
"""
Manage Weekly AI Brief Scheduling
Usage: python3 manage_schedule.py [start|stop|status|test]
"""

import subprocess
import sys
import os
from pathlib import Path

PLIST_FILE = "/Users/sarahfoster/Library/LaunchAgents/com.ai_news_brief.weekly.plist"
SERVICE_NAME = "com.ai_news_brief.weekly"

def run_command(cmd):
    """Run shell command and return result"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def start_schedule():
    """Start the weekly brief scheduling"""
    success, stdout, stderr = run_command(f"launchctl load {PLIST_FILE}")
    if success:
        print("✅ Weekly AI brief scheduling started")
        print("📅 Will run every Thursday at 8:00 AM")
        return True
    else:
        print(f"❌ Failed to start scheduling: {stderr}")
        return False

def stop_schedule():
    """Stop the weekly brief scheduling"""  
    success, stdout, stderr = run_command(f"launchctl unload {PLIST_FILE}")
    if success:
        print("🛑 Weekly AI brief scheduling stopped")
        return True
    else:
        print(f"❌ Failed to stop scheduling: {stderr}")
        return False

def check_status():
    """Check if the service is running"""
    success, stdout, stderr = run_command(f"launchctl list | grep {SERVICE_NAME}")
    if success and stdout.strip():
        print("✅ Weekly AI brief scheduling is ACTIVE")
        print("📅 Next run: Thursday at 8:00 AM")
        print(f"📝 Logs: {Path(__file__).parent}/logs/")
        return True
    else:
        print("❌ Weekly AI brief scheduling is NOT running")
        return False

def test_run():
    """Run the weekly brief immediately for testing"""
    print("🧪 Running weekly brief test...")
    script_path = Path(__file__).parent / "weekly_agent.py"
    success, stdout, stderr = run_command(f"cd {Path(__file__).parent} && python3 {script_path}")
    
    if success:
        print("✅ Test run completed successfully")
        if stdout:
            print(f"📊 Output: {stdout}")
    else:
        print(f"❌ Test run failed: {stderr}")
        if stdout:
            print(f"📊 Output: {stdout}")
    
    return success

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 manage_schedule.py [start|stop|status|test]")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "start":
        start_schedule()
    elif command == "stop":
        stop_schedule()
    elif command == "status":
        check_status()
    elif command == "test":
        test_run()
    else:
        print("Invalid command. Use: start, stop, status, or test")
        sys.exit(1)

if __name__ == "__main__":
    main()

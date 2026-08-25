#!/usr/bin/env python3
"""
QA Agentic Workflow - Slack Bot Runner
Khởi chạy Slack Bot kết nối trực tiếp với Slack Workspace của công ty/team.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.integrations.slack_bot import start_slack_bot

if __name__ == "__main__":
    start_slack_bot()

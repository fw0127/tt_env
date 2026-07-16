"""作战室独立入口：分析下一场对手。

用法: python war_room.py [my_team_id]
Cookie Token 从 .env 的 MYTT_COOKIE 读取（不再硬编码在源码里）。
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from mytt.analysis import run_war_room
from mytt.api import MyTTApi

if __name__ == "__main__":
    load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=True)
    api = MyTTApi(cookie_token=os.getenv("MYTT_COOKIE", ""))
    my_id = sys.argv[1] if len(sys.argv) > 1 else "2958811"
    run_war_room(api, my_id)

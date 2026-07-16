"""交互式 CLI：菜单定义、路由分发、主循环。"""
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List

from dotenv import load_dotenv
from rich import box
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .analysis import run_team_analysis, run_war_room
from .api import MyTTApi
from .render import (
    render_club_teams,
    render_league_table_api,
    render_meeting_live,
    render_search_clubs,
    render_search_players,
    render_team_players,
    render_team_schedule_api,
    render_ttr_history,
    render_ttr_player,
)
from .ui import console, prompt_param, show_json

ROOT = Path(__file__).resolve().parent.parent

# 常用功能：key -> (标签, 参数列表, 处理函数)
Handler = Callable[[MyTTApi, Dict[str, str]], None]

COMMON_ACTIONS: List[Dict[str, Any]] = [
    {"key": "1", "label": "搜索球员", "params": [("query", "球员姓名，例如 Dang Qiu")],
     "handler": lambda api, kw: render_search_players(api, kw["query"])},
    {"key": "2", "label": "搜索俱乐部", "params": [("query", "俱乐部名称，例如 Borussia")],
     "handler": lambda api, kw: render_search_clubs(api, kw["query"])},
    {"key": "3", "label": "获取球员实时 TTR", "params": [("nuid", "球员 NUID / personId，例如 NU7535")],
     "handler": lambda api, kw: render_ttr_player(api, kw["nuid"])},
    {"key": "4", "label": "获取球员完整 TTR 历史", "params": [("nuid", "球员 NUID / personId")],
     "handler": lambda api, kw: render_ttr_history(api, kw["nuid"])},
    {"key": "5", "label": "获取球队阵容", "params": [("team_id", "Team ID，例如 2953148")],
     "handler": lambda api, kw: render_team_players(api, kw["team_id"])},
    {"key": "6", "label": "球队分析（阵容 + 每人实时TTR）", "params": [("team_id", "Team ID，例如 2953148")],
     "handler": lambda api, kw: run_team_analysis(api, kw["team_id"])},
    {"key": "7", "label": "球队赛程（API）", "params": [("team_id", "Team ID"), ("season", "赛季，默认 25--26")],
     "handler": lambda api, kw: render_team_schedule_api(api, kw["team_id"], kw.get("season", "25--26"))},
    {"key": "8", "label": "俱乐部所有球队", "params": [("club_number", "clubNumber，例如 13118"), ("organization", "协会简称，例如 WTTV")],
     "handler": lambda api, kw: render_club_teams(api, kw["club_number"], kw["organization"])},
    {"key": "9", "label": "联赛排名表（API）", "params": [("association", "协会简称"), ("league_id", "league/group id，例如 493079")],
     "handler": lambda api, kw: render_league_table_api(api, kw["association"], kw["league_id"])},
    {"key": "10", "label": "比赛 Live 状态", "params": [("meeting_id", "比赛 ID，例如 15348642")],
     "handler": lambda api, kw: render_meeting_live(api, kw["meeting_id"])},
    {"key": "w", "label": "⚔️ 作战室 (下一场对手深度分析)", "params": [("my_team_id", "我的 Team ID，例如 2958811")],
     "handler": lambda api, kw: run_war_room(api, kw["my_team_id"])},
]


ALL_GET_ACTIONS: List[Dict[str, Any]] = [
    {"name": "get_andro_regions", "params": [("as_code", "协会代码，默认 all"), ("di", "地区代码，默认 all")]},
    {"name": "get_statistics_matches", "params": [("player_id", "球员ID"), ("date_range", "时间范围，如 current_season")]},
    {"name": "get_statistics_ttr", "params": [("player_id", "球员ID"), ("date_range", "时间范围，如 current_season")]},
    {"name": "get_ttr_history", "params": [("nuid", "NUID")]},
    {"name": "get_ttr_player", "params": [("nuid", "NUID")]},
    {"name": "get_andro_ranking", "params": [("params", "JSON对象，例如 {\"continent\":\"Europa\"}")]},
    {"name": "get_team_schedule_api", "params": [("team_id", "TeamID"), ("season", "赛季，默认 25--26")]},
    {"name": "get_team_players", "params": [("team_id", "TeamID")]},
    {"name": "get_team_player_stats", "params": [("association", "协会"), ("season", "赛季"), ("league_slug", "联赛slug"), ("group_id", "groupId"), ("team_id", "teamId"), ("team_name", "teamName"), ("filter_", "gesamt/vr/rr")]},
    {"name": "get_team_schedule_loader", "params": [("association", "协会"), ("season", "赛季"), ("league_slug", "联赛slug"), ("group_id", "groupId"), ("team_id", "teamId"), ("team_name", "teamName"), ("filter_", "gesamt/vr/rr")]},
    {"name": "get_team_info_loader", "params": [("association", "协会"), ("season", "赛季"), ("league_slug", "联赛slug"), ("group_id", "groupId"), ("team_id", "teamId"), ("team_name", "teamName")]},
    {"name": "get_club_teams", "params": [("club_number", "clubNumber"), ("organization", "organization")]},
    {"name": "get_club_teams_loader", "params": [("association", "协会"), ("season", "赛季"), ("club_id", "clubId"), ("club_slug", "clubSlug")]},
    {"name": "get_club_schedule_loader", "params": [("association", "协会"), ("season", "赛季"), ("club_id", "clubId"), ("club_slug", "clubSlug")]},
    {"name": "get_club_balance_loader", "params": [("association", "协会"), ("season", "赛季"), ("club_id", "clubId"), ("club_slug", "clubSlug"), ("filter_", "gesamt/vr/rr")]},
    {"name": "get_club_info_loader", "params": [("association", "协会"), ("season", "赛季"), ("club_id", "clubId"), ("club_slug", "clubSlug")]},
    {"name": "get_league_table_api", "params": [("association", "协会"), ("league_id", "league/group id")]},
    {"name": "get_group_table_loader", "params": [("association", "协会"), ("season", "赛季"), ("league_slug", "联赛slug"), ("group_id", "groupId"), ("filter_", "gesamt/vr/rr")]},
    {"name": "get_group_schedule_loader", "params": [("association", "协会"), ("season", "赛季"), ("league_slug", "联赛slug"), ("group_id", "groupId"), ("filter_", "gesamt/vr/rr")]},
    {"name": "get_group_contacts_loader", "params": [("association", "协会"), ("season", "赛季"), ("league_slug", "联赛slug"), ("group_id", "groupId")]},
    {"name": "get_group_balances_loader", "params": [("association", "协会"), ("season", "赛季"), ("league_slug", "联赛slug"), ("group_id", "groupId"), ("filter_", "gesamt/vr/rr")]},
    {"name": "get_group_team_registrations_loader", "params": [("association", "协会"), ("season", "赛季"), ("league_slug", "联赛slug"), ("group_id", "groupId"), ("filter_", "gesamt/vr/rr")]},
    {"name": "get_group_rankings_loader", "params": [("association", "协会"), ("season", "赛季"), ("league_slug", "联赛slug"), ("group_id", "groupId"), ("match_type", "single/double/..."), ("filter_", "gesamt/vr/rr")]},
    {"name": "get_group_viewer_matrix_loader", "params": [("association", "协会"), ("season", "赛季"), ("league_slug", "联赛slug"), ("group_id", "groupId")]},
    {"name": "get_region_schedule_loader", "params": [("association", "协会"), ("season", "赛季"), ("championship", "例如 Rhein-Wupper 25/26")]},
    {"name": "get_league_tree_loader", "params": [("association", "协会"), ("season", "赛季"), ("type_", "ligen/pokal/..."), ("championship", "例如 Rhein-Wupper 25/26")]},
    {"name": "get_meeting_live", "params": [("meeting_id", "比赛ID")]},
]


def show_common_menu() -> None:
    table = Table(title="🚀 MyTT CLI 常用功能", box=box.ROUNDED, header_style="bold blue")
    table.add_column("编号", style="cyan", width=6, justify="center")
    table.add_column("功能", style="bold white")
    table.add_column("输入参数说明", style="magenta")
    for a in COMMON_ACTIONS:
        hint = ", ".join(p[0] for p in a["params"])
        table.add_row(a["key"], a["label"], hint)
    table.add_row("a", "全量 GET 接口", "浏览所有文档接口")
    table.add_row("q", "退出", "-")
    console.print(table)


def show_all_get_menu() -> None:
    table = Table(title="📚 全量 GET 接口", box=box.ROUNDED, header_style="bold yellow")
    table.add_column("编号", style="cyan", width=6, justify="center")
    table.add_column("接口方法", style="bold white")
    table.add_column("所需参数", style="magenta")
    for i, item in enumerate(ALL_GET_ACTIONS, start=1):
        table.add_row(str(i), item["name"], ", ".join(p[0] for p in item["params"]))
    table.add_row("b", "返回主菜单", "-")
    console.print(table)


def run_all_get_menu(api: MyTTApi) -> None:
    while True:
        show_all_get_menu()
        choice = Prompt.ask("选择接口编号").strip().lower()
        if choice == "b":
            return
        if not choice.isdigit() or not (1 <= int(choice) <= len(ALL_GET_ACTIONS)):
            console.print("[red]无效输入。[/red]")
            continue

        item = ALL_GET_ACTIONS[int(choice) - 1]
        kwargs: Dict[str, Any] = {}
        for p_name, p_hint in item["params"]:
            if p_name == "params":
                raw = prompt_param("params", p_hint)
                try:
                    kwargs[p_name] = json.loads(raw)
                except Exception:
                    kwargs[p_name] = {}
            else:
                kwargs[p_name] = prompt_param(p_name, p_hint, allow_empty=True)

        res = getattr(api, item["name"])(**kwargs)
        show_json(res, title=f"Result: {item['name']}")


def main() -> None:
    load_dotenv(dotenv_path=ROOT / ".env", override=True)

    from .auth import ensure_fresh
    token_default, status = ensure_fresh(os.getenv("MYTT_COOKIE", ""), allow_browser=False)
    if status == "refreshed":
        console.print("[green]🔄 Token 已自动续期并写回 .env[/green]")
    elif status == "manual_required" and token_default:
        console.print("[yellow]⚠ Token 已失效且无法自动续期，可在浏览器登录后运行 Web 版一键导入[/yellow]")
    token = Prompt.ask("🔑 Cookie Token (可选)", default=token_default or "").strip()
    api = MyTTApi(cookie_token=token)

    console.print(Panel.fit(
        "[bold blue]myTischtennis 助手[/bold blue]\n[dim]支持球员搜索、TTR历史、球队分析等[/dim]",
        border_style="blue", title="MyTT CLI v1.0",
    ))

    while True:
        show_common_menu()
        choice = Prompt.ask("👉 请选择").strip().lower()
        if choice == "q":
            break
        if choice == "a":
            run_all_get_menu(api)
            continue

        selected = next((a for a in COMMON_ACTIONS if a["key"] == choice), None)
        if not selected:
            console.print("[red]无效选择。[/red]")
            continue

        kwargs: Dict[str, str] = {}
        for p_name, p_hint in selected["params"]:
            val = prompt_param(p_name, p_hint, allow_empty=(p_name == "season"))
            if p_name == "season" and not val:
                val = "25--26"
            kwargs[p_name] = val

        selected["handler"](api, kwargs)

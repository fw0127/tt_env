"""深度分析：数据收集层（CLI 与 Web 共用）+ CLI 终端渲染。"""
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from rich import box
from rich.panel import Panel
from rich.table import Table

from .api import MyTTApi, clean_roster
from .ui import console, format_ttr


# ---------- 数据层 ----------

def player_recent_form(api: MyTTApi, nuid: str) -> Optional[Dict[str, int]]:
    """球员近况：最近 5 场的 TTR 变动合计与胜场数。拿不到历史时返回 None。"""
    data = api.get_ttr_history(nuid)
    if not data or not isinstance(data, dict) or not data.get("event"):
        return None

    events = data["event"][-5:]
    return {
        "delta": sum(e.get("ttr_delta", 0) for e in events),
        "wins": sum(1 for e in events if e.get("ttr_delta", 0) > 0),
        "games": len(events),
    }


def collect_team_analysis(api: MyTTApi, team_id: str, with_form: bool = False) -> List[Dict[str, Any]]:
    """收集球队阵容 + 每人实时 TTR（可选近况分析）。"""
    roster = clean_roster(api.get_team_players(team_id).get("data", []) or [])
    players: List[Dict[str, Any]] = []
    for p in roster:
        nuid = str(p.get("internal_id", "") or "")
        entry: Dict[str, Any] = {
            "rank": str(p.get("rank", "-")),
            "name": f"{p.get('lastname', '')} {p.get('firstname', '')}".strip(),
            "nuid": nuid,
            "ttr": None,
            "form": None,
        }
        if nuid:
            entry["ttr"] = api.get_ttr_player(nuid).get("ttr")
            if with_form:
                entry["form"] = player_recent_form(api, nuid)
                time.sleep(0.05)  # 频率保护
        players.append(entry)
    return players


def collect_war_room(api: MyTTApi, my_team_id: str) -> Dict[str, Any]:
    """作战室数据：锁定下一场对手并收集其阵容与近况。
    出错时返回 {'error': 提示文本}。"""
    schedule = api.get_team_schedule_api(my_team_id).get("data", [])
    if not schedule:
        return {"error": "无法获取赛程，请检查 Token 或 TeamID。"}

    today = datetime.now().strftime("%Y-%m-%d")
    target = next((s for s in schedule if (s.get("date") or "")[:10] >= today), None)
    if not target:
        return {"error": "赛季似乎已结束，没有未来的比赛记录。"}

    opp_id = str(target.get("opponent_team_id"))
    players = collect_team_analysis(api, opp_id, with_form=True)
    if not players:
        return {"error": "无法获取对手阵容。"}

    return {
        "opponent_id": opp_id,
        "opponent_name": target.get("opponent_team_name"),
        "date": (target.get("date") or "")[:10],
        "players": players,
    }


# ---------- CLI 渲染 ----------

def _form_to_status(form: Optional[Dict[str, int]]) -> tuple[str, str]:
    """把近况数据转成 (rich 状态文本, 趋势文本)。"""
    if form is None:
        return "未知", "N/A"

    delta, wins = form["delta"], form["wins"]
    if delta > 15:
        status = "[bold green]🔥 极佳[/bold green]"
    elif delta < -10:
        status = "[bold red]📉 低迷[/bold red]"
    else:
        status = "[white]平稳[/white]"

    trend = f"{'+' if delta > 0 else ''}{delta} (胜{wins}/5)"
    return status, trend


def run_team_analysis(api: MyTTApi, team_id: str) -> None:
    """球队分析：阵容 + 每人实时 TTR。"""
    with console.status("[bold green]正在获取实时 TTR..."):
        players = collect_team_analysis(api, team_id)

    if not players:
        console.print("[red]未获取到球队阵容，请检查 teamId。[/red]")
        return

    table = Table(title=f"🔍 球队分析 (TeamID: {team_id})", box=box.ROUNDED, header_style="bold magenta")
    table.add_column("排名", style="cyan", justify="right", width=6)
    table.add_column("姓名", style="bold white", width=20)
    table.add_column("NUID", style="yellow", width=12)
    table.add_column("实时TTR", justify="right", width=12)

    for p in players:
        ttr_text, ttr_style = format_ttr(p["ttr"])
        table.add_row(p["rank"], p["name"][:20], p["nuid"], f"[{ttr_style}]{ttr_text}[/{ttr_style}]")

    console.print(table)


def run_war_room(api: MyTTApi, my_team_id: str) -> None:
    """深度作战室：自动锁定下一场对手并分析其近况。"""
    console.print(f"\n[bold inverse] 🏟️  正在进入深度作战室 - 我的球队 ID: {my_team_id} [/bold inverse]")

    with console.status("[bold cyan]正在同步赛程并侦察对手..."):
        report = collect_war_room(api, my_team_id)

    if "error" in report:
        console.print(f"[red]❌ {report['error']}[/red]")
        return

    console.print(Panel(
        f"🎯 [bold yellow]下场对手锁定[/bold yellow]: [bold cyan]{report['opponent_name']}[/bold cyan] (ID: {report['opponent_id']})\n"
        f"📅 [bold white]比赛日期[/bold white]: {report['date']}",
        border_style="magenta",
    ))

    table = Table(title="⚔️ 对手战力侦察报告", box=box.DOUBLE_EDGE, header_style="bold magenta")
    table.add_column("排", justify="right", width=4)
    table.add_column("选手姓名", width=20)
    table.add_column("实时 TTR", justify="right", width=10)
    table.add_column("近期状态", justify="center", width=15)
    table.add_column("5场趋势", justify="left")

    for p in report["players"]:
        ttr_text, ttr_style = format_ttr(p["ttr"] if p["ttr"] is not None else "N/A")
        status, trend = _form_to_status(p["form"])
        table.add_row(p["rank"], p["name"][:20], f"[{ttr_style}]{ttr_text}[/{ttr_style}]", status, trend)

    console.print(table)

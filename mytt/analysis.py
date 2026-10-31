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


def current_season(now: Optional[datetime] = None) -> str:
    """当前赛季的 URL 形式，如 "26--27"。赛季 7 月开始。"""
    now = now or datetime.now()
    start = now.year if now.month >= 7 else now.year - 1
    return f"{start % 100:02d}--{(start + 1) % 100:02d}"


def team_season_matches(api: MyTTApi, association: str, group_id: str, team_id: str,
                        season: Optional[str] = None) -> Dict[str, Any]:
    """球队本赛季的全部比赛与结果。

    球队级的 spielplan 接口会 403，这里取所在小组（联赛）的完整赛程再按 team_id 过滤。
    小组赛程中 matches_won / matches_lost 是主队 / 客队的得分，需按主客场换算成本队视角。
    """
    season = season or current_season()
    data = api.get_group_schedule_loader(association, season, "x", group_id)  # 联赛 slug 不影响结果
    if not isinstance(data, dict) or not isinstance(data.get("data"), dict):
        return {"error": (data or {}).get("error") or "无法获取联赛赛程", "matches": []}

    tid = str(team_id)
    matches: List[Dict[str, Any]] = []
    team_name = ""
    for day in data["data"].get("meetings") or []:
        for m in (x for ms in day.values() for x in ms):
            home = str(m.get("team_home_id")) == tid
            if not home and str(m.get("team_away_id")) != tid:
                continue
            team_name = m.get("team_home" if home else "team_away") or team_name
            done = m.get("state") == "done"
            hs, as_ = int(m.get("matches_won") or 0), int(m.get("matches_lost") or 0)
            own, opp = (hs, as_) if home else (as_, hs)
            matches.append({
                "date": m.get("date"),
                "meeting_id": m.get("meeting_id"),
                "home": home,
                "opponent": m.get("team_away" if home else "team_home"),
                "opponent_id": m.get("team_away_id" if home else "team_home_id"),
                "state": m.get("state"),
                "own": own if done else None,
                "opp": opp if done else None,
                "result": ("W" if own > opp else "L" if own < opp else "D") if done else None,
                "location": (m.get("location") or {}).get("label"),
            })
    matches.sort(key=lambda x: x["date"] or "")

    played = [x for x in matches if x["result"]]
    head = data["data"].get("head_infos") or {}
    return {
        "season": season,
        "association": association,
        "group_id": group_id,
        "team_name": team_name,
        "league": head.get("league_name"),
        "matches": matches,
        "summary": {
            "played": len(played),
            "won": sum(x["result"] == "W" for x in played),
            "drawn": sum(x["result"] == "D" for x in played),
            "lost": sum(x["result"] == "L" for x in played),
            "remaining": len(matches) - len(played),
        },
    }


def today_matches(api: MyTTApi, teams: List[Dict[str, Any]], date: Optional[str] = None) -> Dict[str, Any]:
    """关注球队所在小组里「今天」的比赛，带实时比分。

    teams 是关注列表中的球队项，需要 extra 里的 assoc / group（早期关注的没有，只能跳过）。
    赛程按小组取（每个小组一次，走一天的本地缓存），比分再逐场查 Live 接口（该接口不缓存）。
    """
    date = date or datetime.now().strftime("%Y-%m-%d")
    mine = {str(t.get("key")) for t in teams}

    groups: Dict[tuple, None] = {}       # 去重，保持关注顺序
    skipped = 0
    for t in teams:
        ex = t.get("extra") or {}
        if ex.get("assoc") and ex.get("group"):
            groups[(ex["assoc"], str(ex["group"]), ex.get("season") or current_season())] = None
        else:
            skipped += 1

    matches: List[Dict[str, Any]] = []
    errors: List[str] = []
    for assoc, group_id, season in groups:
        data = api.get_group_schedule_loader(assoc, season, "x", group_id)
        if not isinstance(data, dict) or not isinstance(data.get("data"), dict):
            errors.append(f"{assoc}/{group_id}")
            continue
        for day in data["data"].get("meetings") or []:
            for m in (x for ms in day.values() for x in ms):
                if (m.get("date") or "")[:10] != date:
                    continue
                home_id, away_id = str(m.get("team_home_id")), str(m.get("team_away_id"))
                matches.append({
                    "meeting_id": m.get("meeting_id"),
                    "date": m.get("date"),
                    "home": m.get("team_home"), "home_id": home_id,
                    "away": m.get("team_away"), "away_id": away_id,
                    "league": m.get("league_name"),
                    "state": m.get("state"),
                    "live": bool(m.get("live")),
                    "mine_home": home_id in mine, "mine_away": away_id in mine,
                    "mine": home_id in mine or away_id in mine,
                    "location": (m.get("location") or {}).get("label"),
                    "score": None,
                })

    # 逐场取当前比分：Live 接口不走缓存，拿到的是此刻的实时状态。
    # 小组赛程缓存一天，里面的 state / live 会过期，所以状态以这里为准：
    # 打完的有 is_completed；进行中的 is_completed 为空但已经有比分（live 标志不可靠，常年是 false）。
    for m in matches:
        if not m["meeting_id"]:
            m["status"] = "done" if m["state"] == "done" else "upcoming"
            continue
        d = (api.get_meeting_live(str(m["meeting_id"])) or {}).get("data") or {}
        done = bool(d.get("is_completed")) or (not d and m["state"] == "done")
        hs, as_ = d.get("matches_home") or 0, d.get("matches_guest") or 0
        if hs or as_:
            m["score"] = {"home": hs, "away": as_}
        m["status"] = "done" if done else ("live" if (hs or as_ or d.get("live")) else "upcoming")
        m["live"] = m["status"] == "live"

    order = {"live": 0, "upcoming": 1, "done": 2}
    matches.sort(key=lambda x: (order.get(x.get("status"), 3), x["date"] or ""))
    return {"date": date, "matches": matches, "groups": len(groups),
            "skipped": skipped, "errors": errors}


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

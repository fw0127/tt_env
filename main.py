import os
import re
import time
import dotenv
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote

import requests
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table


console = Console()
ROOT = Path(__file__).resolve().parent


def _slug(value: str) -> str:
    return value.strip().replace(" ", "_")


class MyTTApi:
    """
    统一 API 封装。
    包含文档里的所有 GET 接口，并保留搜索 POST 接口便于菜单实用化。
    """

    BASE_URL = "https://www.mytischtennis.de"

    def __init__(self, cookie_token: str = "") -> None:
        self.session = requests.Session()
        # 设置全局通用 Headers
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.mytischtennis.de/",
            "X-Requested-With": "XMLHttpRequest"
        })

        if cookie_token:
            # 1. 尝试作为原始 Header 注入
            self.session.headers["Cookie"] = cookie_token
            
            # 2. 同时解析并注入到 CookieJar 中，增强兼容性
            # 假设格式为: sb-10-auth-token=base64-xxx; other_key=val
            try:
                for part in cookie_token.split(';'):
                    if '=' in part:
                        name, value = part.strip().split('=', 1)
                        self.session.cookies.set(name, value, domain="www.mytischtennis.de")
                console.print(f"[green]✔ Token 已成功加载到 Session (长度: {len(cookie_token)})[/green]")
            except Exception as e:
                console.print(f"[yellow]⚠ Token 解析微调: {e}[/yellow]")

    def _get(self, path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        url = f"{self.BASE_URL}{path}"
        try:
            # 这里的 params 会被 requests 自动 urlencode
            r = self.session.get(url, params=params, timeout=30)
            
            # 如果返回 401 或 403，说明 Token 可能失效
            if r.status_code in [401, 403]:
                return {"error": "认证失败", "status_code": r.status_code, "msg": "Token 可能已过期或无效"}
                
            return r.json()
        except Exception as e:
            # 捕获 JSON 解析错误或网络错误
            text_preview = r.text[:500] if 'r' in locals() else str(e)
            return {"error": "Request Failed", "content": text_preview}

    def _post(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.BASE_URL}{path}"
        try:
            # myTT 的搜索接口通常接收 Form Data 而非 JSON
            r = self.session.post(url, data=data, timeout=30)
            try:
                j = r.json()
            except Exception as e:
                j = {"error": "POST JSON parse failed", "status_code": r.status_code, "msg": str(e)[:120]}
            return j
        except Exception as e:
            return {"error": "POST Failed", "msg": str(e)}


    # ---- 文档中的 GET 接口 ----
    def get_andro_regions(self, as_code: str = "all", di: str = "all") -> Dict[str, Any]:
        return self._get("/api/andro-ranking/regions", {"as": as_code, "di": di})

    def get_statistics_matches(self, player_id: str, date_range: str) -> Dict[str, Any]:
        return self._get(f"/api/statistics/{player_id}/matches/{date_range}")

    def get_statistics_ttr(self, player_id: str, date_range: str) -> Dict[str, Any]:
        return self._get(f"/api/statistics/{player_id}/ttr/{date_range}")

    def get_ttr_history(self, nuid: str, clicktt_id: str | None = None) -> Dict[str, Any]:
        params = {}
        effective_clicktt_id = clicktt_id
        if not effective_clicktt_id and nuid:
            match = re.search(r'\d+', nuid)
            if match:
                effective_clicktt_id = match.group(0)

        if effective_clicktt_id:
            params["clicktt_id"] = effective_clicktt_id
        return self._get(f"/api/ttr/history/{nuid}", params)

    def get_ttr_player(self, nuid: str) -> Dict[str, Any]:
        return self._get(f"/api/ttr/player/{nuid}")

    def get_andro_ranking(self, params: Dict[str, Any]) -> Dict[str, Any]:
        q = dict(params)
        q["_data"] = "routes/$"
        return self._get("/rankings/andro-rangliste", q)

    def get_team_schedule_api(self, team_id: str, season: str = "25--26") -> Dict[str, Any]:
        return self._get("/api/ttr/team/schedule", {"teamId": team_id, "season": season})

    def get_team_players(self, team_id: str) -> Dict[str, Any]:
        return self._get("/api/ttr/team/players", {"teamId": team_id})

    def get_team_player_stats(
        self,
        association: str,
        season: str,
        league_slug: str,
        group_id: str,
        team_id: str,
        team_name: str,
        filter_: str = "gesamt",
    ) -> Dict[str, Any]:
        path = (
            f"/click-tt/{association}/{season}/ligen/{_slug(league_slug)}/gruppe/{group_id}"
            f"/mannschaft/{team_id}/{_slug(team_name)}/spielerbilanzen/{filter_}"
        )
        params = {"_data": "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/mannschaft.$teamid.$teamname+/spielerbilanzen.$filter"}
        return self._get(path, params)

    def get_team_schedule_loader(
        self, association: str, season: str, league_slug: str, group_id: str, team_id: str, team_name: str, filter_: str = "gesamt"
    ) -> Dict[str, Any]:
        path = (
            f"/click-tt/{association}/{season}/ligen/{_slug(league_slug)}/gruppe/{group_id}"
            f"/mannschaft/{team_id}/{_slug(team_name)}/spielplan/{filter_}"
        )
        params = {"_data": "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/mannschaft.$teamid.$teamname+/spielplan.$filter"}
        return self._get(path, params)

    def get_team_info_loader(
        self, association: str, season: str, league_slug: str, group_id: str, team_id: str, team_name: str
    ) -> Dict[str, Any]:
        path = (
            f"/click-tt/{association}/{season}/ligen/{_slug(league_slug)}/gruppe/{group_id}"
            f"/mannschaft/{team_id}/{_slug(team_name)}/infos"
        )
        params = {"_data": "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/mannschaft.$teamid.$teamname+/infos"}
        return self._get(path, params)

    def get_club_teams(self, club_number: str, organization: str) -> Dict[str, Any]:
        return self._get("/api/ttr/teams", {"clubNumber": club_number, "organization": organization})

    def get_club_teams_loader(self, association: str, season: str, club_id: str, club_slug: str = "x") -> Dict[str, Any]:
        path = f"/click-tt/{association}/{season}/verein/{club_id}/{_slug(club_slug)}/mannschaften"
        params = {"_data": "routes/click-tt+/$association+/$season+/verein.$clubid.$clubname+/mannschaften"}
        return self._get(path, params)

    def get_club_schedule_loader(self, association: str, season: str, club_id: str, club_slug: str = "x") -> Dict[str, Any]:
        path = f"/click-tt/{association}/{season}/verein/{club_id}/{_slug(club_slug)}/spielplan"
        params = {"_data": "routes/click-tt+/$association+/$season+/verein.$clubid.$clubname+/spielplan"}
        return self._get(path, params)

    def get_club_balance_loader(
        self, association: str, season: str, club_id: str, club_slug: str = "x", filter_: str = "gesamt"
    ) -> Dict[str, Any]:
        path = f"/click-tt/{association}/{season}/verein/{club_id}/{_slug(club_slug)}/bilanzen/{filter_}"
        params = {"_data": "routes/click-tt+/$association+/$season+/verein.$clubid.$clubname+/bilanzen.$filter"}
        return self._get(path, params)

    def get_club_info_loader(self, association: str, season: str, club_id: str, club_slug: str = "x") -> Dict[str, Any]:
        path = f"/click-tt/{association}/{season}/verein/{club_id}/{_slug(club_slug)}/info"
        params = {"_data": "routes/click-tt+/$association+/$season+/verein.$clubid.$clubname+/info"}
        return self._get(path, params)

    def get_league_table_api(self, association: str, league_id: str) -> Dict[str, Any]:
        return self._get(f"/api/league-table/{association}/{league_id}")

    def get_group_table_loader(
        self, association: str, season: str, league_slug: str, group_id: str, filter_: str = "gesamt"
    ) -> Dict[str, Any]:
        path = f"/click-tt/{association}/{season}/ligen/{_slug(league_slug)}/gruppe/{group_id}/tabelle/{filter_}"
        params = {"_data": "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/tabelle.$filter"}
        return self._get(path, params)

    def get_group_schedule_loader(
        self, association: str, season: str, league_slug: str, group_id: str, filter_: str = "gesamt"
    ) -> Dict[str, Any]:
        path = f"/click-tt/{association}/{season}/ligen/{_slug(league_slug)}/gruppe/{group_id}/spielplan/{filter_}"
        params = {"_data": "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/spielplan.$filter"}
        return self._get(path, params)

    def get_group_contacts_loader(self, association: str, season: str, league_slug: str, group_id: str) -> Dict[str, Any]:
        path = f"/click-tt/{association}/{season}/ligen/{_slug(league_slug)}/gruppe/{group_id}/kontakte"
        params = {"_data": "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/kontakte"}
        return self._get(path, params)

    def get_group_balances_loader(
        self, association: str, season: str, league_slug: str, group_id: str, filter_: str = "gesamt"
    ) -> Dict[str, Any]:
        path = f"/click-tt/{association}/{season}/ligen/{_slug(league_slug)}/gruppe/{group_id}/bilanzuebersichten/{filter_}"
        params = {"_data": "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/bilanzuebersichten.$filter"}
        return self._get(path, params)

    def get_group_team_registrations_loader(
        self, association: str, season: str, league_slug: str, group_id: str, filter_: str = "gesamt"
    ) -> Dict[str, Any]:
        path = f"/click-tt/{association}/{season}/ligen/{_slug(league_slug)}/gruppe/{group_id}/mannschaftsmeldungen/{filter_}"
        params = {"_data": "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/mannschaftsmeldungen.$filter"}
        return self._get(path, params)

    def get_group_rankings_loader(
        self, association: str, season: str, league_slug: str, group_id: str, match_type: str, filter_: str = "gesamt"
    ) -> Dict[str, Any]:
        path = f"/click-tt/{association}/{season}/ligen/{_slug(league_slug)}/gruppe/{group_id}/gruppen-ranglisten/{match_type}/{filter_}"
        params = {"_data": "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/gruppen-ranglisten.$matchtype.$filter"}
        return self._get(path, params)

    def get_group_viewer_matrix_loader(self, association: str, season: str, league_slug: str, group_id: str) -> Dict[str, Any]:
        path = f"/click-tt/{association}/{season}/ligen/{_slug(league_slug)}/gruppe/{group_id}/zuschauer-matrix"
        params = {"_data": "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/zuschauer-matrix"}
        return self._get(path, params)

    def get_region_schedule_loader(self, association: str, season: str, championship: str) -> Dict[str, Any]:
        path = f"/click-tt/{association}/{season}/regionsspielplan/{quote(championship, safe='')}"
        params = {"_data": "routes/click-tt+/$association+/$season+/regionsspielplan.$region"}
        return self._get(path, params)

    def get_league_tree_loader(self, association: str, season: str, type_: str, championship: str) -> Dict[str, Any]:
        path = f"/click-tt/{association}/{season}/{type_}/{quote(championship, safe='')}"
        params = {"_data": "routes/click-tt+/$association+/$season+/$type+/$championship"}
        return self._get(path, params)

    def get_meeting_live(self, meeting_id: str) -> Dict[str, Any]:
        return self._get(f"/api/meeting/{meeting_id}/live")

    # ---- 保留实用 POST 搜索 ----
    def search_players(self, query: str, page: int = 1, pagesize: int = 10) -> Dict[str, Any]:
        return self._post("/api/search/players", {"query": query, "page": page, "pagesize": pagesize})

    def search_clubs(self, query: str, page: int = 1, pagesize: int = 10) -> Dict[str, Any]:
        return self._post("/api/search/clubs", {"query": query, "page": page, "pagesize": pagesize})


COMMON_ACTIONS: List[Dict[str, Any]] = [
    {"key": "1", "label": "搜索球员", "params": [("query", "球员姓名，例如 Dang Qiu")], "func": "search_players"},
    {"key": "2", "label": "搜索俱乐部", "params": [("query", "俱乐部名称，例如 Borussia")], "func": "search_clubs"},
    {"key": "3", "label": "获取球员实时 TTR", "params": [("nuid", "球员 NUID / personId，例如 NU7535")], "func": "get_ttr_player"},
    {"key": "4", "label": "获取球员完整 TTR 历史", "params": [("nuid", "球员 NUID / personId")], "func": "get_ttr_history"},
    {"key": "5", "label": "获取球队阵容", "params": [("team_id", "Team ID，例如 2953148")], "func": "get_team_players"},
    {"key": "6", "label": "球队分析（阵容 + 每人实时TTR）", "params": [("team_id", "Team ID，例如 2953148")], "func": "team_analysis"},
    {"key": "7", "label": "球队赛程（API）", "params": [("team_id", "Team ID"), ("season", "赛季，默认 25--26")], "func": "get_team_schedule_api"},
    {"key": "8", "label": "俱乐部所有球队", "params": [("club_number", "clubNumber，例如 13118"), ("organization", "协会简称，例如 WTTV")], "func": "get_club_teams"},
    {"key": "9", "label": "联赛排名表（API）", "params": [("association", "协会简称"), ("league_id", "league/group id，例如 493079")], "func": "get_league_table_api"},
    {"key": "10", "label": "比赛 Live 状态", "params": [("meeting_id", "比赛 ID，例如 15348642")], "func": "get_meeting_live"},
    {"key": "w", "label": "⚔️ 作战室 (下一场对手深度分析)", "params": [("my_team_id", "我的 Team ID，例如 2958811")], "func": "run_war_room"},
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


def prompt_param(name: str, hint: str, allow_empty: bool = False) -> str:
    while True:
        value = Prompt.ask(f"[bold cyan]{name}[/bold cyan] ({hint})", default="" if allow_empty else None).strip()
        if value or allow_empty:
            return value
        console.print("[red]该参数不能为空。[/red]")


def show_json(data: Any, title: str = "Result Data") -> None:
    if isinstance(data, dict) and len(data) < 10 and not any(isinstance(v, (dict, list)) for v in data.values()):
        table = Table(title=title, box=box.ROUNDED, show_header=False)
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="white")
        for k, v in data.items():
            table.add_row(str(k), str(v))
        console.print(table)
    else:
        console.print(Panel(title, border_style="blue"))
        console.print_json(data=data if isinstance(data, (dict, list)) else {"data": str(data)})


def run_team_analysis(api: MyTTApi, team_id: str) -> None:
    roster = api.get_team_players(team_id).get("data", [])
    if not roster:
        console.print("[red]未获取到球队阵容，请检查 teamId。[/red]")
        return

    table = Table(title=f"🔍 球队分析 (TeamID: {team_id})", box=box.ROUNDED, header_style="bold magenta")
    table.add_column("排名", style="cyan", justify="right", width=6)
    table.add_column("姓名", style="bold white", width=20)
    table.add_column("NUID", style="yellow", width=12)
    table.add_column("实时TTR", justify="right", width=12)

    with console.status("[bold green]正在获取实时 TTR..."):
        for p in roster:
            rank = str(p.get("rank", "-"))
            first = p.get("firstname", "")
            last = p.get("lastname", "")
            nuid = str(p.get("internal_id", ""))
            ttr_resp = api.get_ttr_player(nuid) if nuid else {}
            ttr_val = ttr_resp.get("ttr")
            ttr_text, ttr_style = _format_ttr(ttr_val)
            table.add_row(rank, f"{last} {first}".strip()[:20], nuid, f"[{ttr_style}]{ttr_text}[/{ttr_style}]")

    console.print(table)


def _analyze_player_status(api: MyTTApi, nuid: str) -> tuple[str, str]:
    """分析球员近况 (整合自 war_room.py)"""
    data = api.get_ttr_history(nuid)
    if not data or not isinstance(data, dict) or not data.get("event"):
        return "未知", "N/A"

    events = data["event"][-5:]  # 取最近 5 场
    total_delta = sum(e.get("ttr_delta", 0) for e in events)
    wins = sum(1 for e in events if e.get("ttr_delta", 0) > 0)

    if total_delta > 15:
        status = "[bold green]🔥 极佳[/bold green]"
    elif total_delta < -10:
        status = "[bold red]📉 低迷[/bold red]"
    else:
        status = "[white]平稳[/white]"

    trend = f"{'+' if total_delta > 0 else ''}{total_delta} (胜{wins}/5)"
    return status, trend


def run_war_room(api: MyTTApi, my_team_id: str) -> None:
    """深度作战室：自动锁定下一场对手并分析其近况"""
    console.print(f"\n[bold inverse] 🏟️  正在进入深度作战室 - 我的球队 ID: {my_team_id} [/bold inverse]")

    # 1. 获取赛程并寻找下一场对手
    with console.status("[bold cyan]正在同步赛程..."):
        schedule_resp = api.get_team_schedule_api(my_team_id)
        schedule = schedule_resp.get("data", [])

    if not schedule:
        console.print("[red]❌ 无法获取赛程，请检查 Token 或 TeamID。[/red]")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    target = next((s for s in schedule if (s.get("date") or "")[:10] >= today), None)

    if not target:
        console.print("[yellow]📅 赛季似乎已结束，没有未来的比赛记录。[/yellow]")
        return

    opp_id = str(target.get("opponent_team_id"))
    opp_name = target.get("opponent_team_name")
    match_date = (target.get("date") or "")[:10]

    console.print(Panel(
        f"🎯 [bold yellow]下场对手锁定[/bold yellow]: [bold cyan]{opp_name}[/bold cyan] (ID: {opp_id})\n"
        f"📅 [bold white]比赛日期[/bold white]: {match_date}",
        border_style="magenta"
    ))

    # 2. 获取对手阵容
    with console.status(f"[bold green]正在侦察对手 ({opp_name}) 阵容..."):
        roster_resp = api.get_team_players(opp_id)
        roster = roster_resp.get("data", [])

    if not roster:
        console.print("[red]❌ 无法获取对手阵容。[/red]")
        return

    table = Table(title=f"⚔️ 对手战力侦察报告", box=box.DOUBLE_EDGE, header_style="bold magenta")
    table.add_column("排", justify="right", width=4)
    table.add_column("选手姓名", width=20)
    table.add_column("实时 TTR", justify="right", width=10)
    table.add_column("近期状态", justify="center", width=15)
    table.add_column("5场趋势", justify="left")

    with console.status("[bold green]正在分析对手每一位成员的状态..."):
        for p in roster:
            name = f"{p.get('lastname')} {p.get('firstname')}"
            nuid = str(p.get("internal_id", ""))
            
            # 获取实时 TTR
            p_info = api.get_ttr_player(nuid) if nuid else {}
            ttr_val = p_info.get("ttr", "N/A")
            ttr_text, ttr_style = _format_ttr(ttr_val)
            
            # 深度分析
            status, trend = _analyze_player_status(api, nuid) if nuid else ("未知", "N/A")
            
            table.add_row(
                str(p.get("rank", "-")),
                name[:20],
                f"[{ttr_style}]{ttr_text}[/{ttr_style}]",
                status,
                trend
            )
            time.sleep(0.05)  # 频率保护

    console.print(table)


def render_ttr_history(api: MyTTApi, nuid: str, clicktt_id: str | None = None) -> None:
    data = api.get_ttr_history(nuid, clicktt_id=clicktt_id)
    if not isinstance(data, dict) or "event" not in data:
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict) and err.get("code") == "PT403":
            console.print(f"[bold red]❌ 未授权: {err.get('message', 'Not authorized')}[/bold red]")
            console.print("[yellow]💡 该接口需要登录。请在启动时输入有效的 Cookie Token（含 sb-10-auth-token）。[/yellow]")
        else:
            show_json(data, title="TTR History Raw")
        return

    events = list(reversed(data.get("event", [])))
    recent_events = events[:15]

    person_name = data.get("person_name", "N/A")
    current_ttr = data.get("ttr", "N/A")
    
    console.print(f"\n[bold magenta]📈 球员: {person_name} | 当前 TTR: {current_ttr}[/bold magenta]")
    
    table = Table(title=f"最近 {len(recent_events)} 场比赛变动", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("日期", width=12, justify="left")
    table.add_column("变动", width=8, justify="right")
    table.add_column("赛后", width=8, justify="right")
    table.add_column("比分", width=8, justify="center")
    table.add_column("对手 (TTR)", width=25, justify="left")
    table.add_column("赛事", width=30, justify="left")

    for ev in recent_events:
        date = (ev.get("event_date_time", "N/A") or "N/A")[:10]
        delta = ev.get("ttr_delta", 0)
        after = ev.get("ttr_after", "N/A")
        e_name = ev.get("event_name", "N/A")

        delta_text = f"+{delta}" if delta > 0 else str(delta)
        delta_style = "green" if delta > 0 else ("red" if delta < 0 else "white")

        matches = ev.get("match", [])
        if matches:
            for m in matches:
                opp_name = m.get("other_person_name", "未知")
                opp_ttr = m.get("other_ttr", "?")
                own_s = m.get("own_sets", 0)
                oth_s = m.get("other_sets", 0)
                score_raw = f"{own_s}:{oth_s}"
                score_style = "green" if own_s > oth_s else "red"
                opp_info = f"{opp_name}({opp_ttr})"
                short_e = e_name.split("|")[-1].strip() if "|" in str(e_name) else e_name
                table.add_row(
                    date,
                    f"[{delta_style}]{delta_text}[/{delta_style}]",
                    str(after),
                    f"[{score_style}]{score_raw}[/{score_style}]",
                    opp_info[:25],
                    short_e[:30],
                )
        else:
            vs_info = e_name.split("|")[-1].strip() if "|" in str(e_name) else "汇总"
            table.add_row(
                date,
                f"[{delta_style}]{delta_text}[/{delta_style}]",
                str(after),
                "-",
                vs_info[:25],
                str(e_name)[:30],
            )

    console.print(table)


def _format_ttr(value: Any) -> tuple[str, str]:
    if value is None: return ("N/A", "red")
    s = str(value).strip()
    if s == "" or s.lower() in {"none", "null", "n/a"}: return ("N/A", "red")
    if any(k in s for k in ["需登录", "不可见", "ERR", "Not authorized"]): return (s, "yellow")
    if re.fullmatch(r"-?\d+", s): return (s, "green")
    return (s, "white")


def render_search_players(api: MyTTApi, query: str) -> None:
    result = api.search_players(query)
    data = result if isinstance(result, dict) else {}
    items = data.get("results", []) or []
    total = data.get("total_count", 0)

    if not items:
        console.print(f"[yellow]未能找到与 '{query}' 相关的球员。[/yellow]")
        if "error" in data:
            console.print(f"[red]API 错误: {data.get('error')} - {data.get('msg')}[/red]")
        return
    
    table = Table(title=f"🔍 球员搜索: {query} (共 {total} 条)", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("姓名", width=20)
    table.add_column("俱乐部", width=25)
    table.add_column("实时TTR", width=10, justify="right")
    table.add_column("NUID/ID", width=25)
    table.add_column("DTTB ID", width=10)

    with console.status("[bold green]正在获取球员实时 TTR..."):
        for item in items[:20]: # Limit to 20 for performance
            name = f"{item.get('lastname', '')} {item.get('firstname', '')}".strip()
            club = item.get("club_name", "-") or "-"
            
            # Prioritize internal_id, fallback to person_id for TTR lookup
            player_id_for_ttr = item.get('internal_id') or item.get('person_id')
            ttr_val = None
            if player_id_for_ttr:
                ttr_resp = api.get_ttr_player(str(player_id_for_ttr))
                ttr_val = ttr_resp.get("ttr")
            
            ttr_text, ttr_style = _format_ttr(ttr_val or "需登录可见")
            
            nuid_id = str(player_id_for_ttr or "-")
            dttb_id = str(item.get("dttb_player_id", "-"))
            
            table.add_row(
                name[:20],
                club[:25],
                f"[{ttr_style}]{ttr_text}[/{ttr_style}]",
                nuid_id, # Removed truncation
                dttb_id[:10],
            )

    console.print(table)

    while True:
        selected_player_id_input = Prompt.ask("[bold blue]请输入要查看详情的球员 NUID/ID (或输入 'b' 返回):[/bold blue]").strip().lower()
        if selected_player_id_input == "b":
            return
        selected_player = None
        for item in items:
            player_id_check = str(item.get('internal_id') or item.get('person_id') or "-")
            if player_id_check.upper().strip() == selected_player_id_input.upper().strip():
                selected_player = item
                break

        if not selected_player:
            console.print("[red]无效的 NUID/ID，请重新输入。[/red]")
            continue

        while True:
            console.print(Panel(f"[bold white]已选择球员: {selected_player.get('lastname', '')} {selected_player.get('firstname', '')}[/bold white]", title="球员详情操作", border_style="green"))
            sub_choice = Prompt.ask("[bold blue]请选择操作: 1.显示TTR历史 2.显示俱乐部队伍信息 (b返回):[/bold blue]").strip().lower()

            if sub_choice == "b":
                break

            if sub_choice == "1":
                nuid = str(selected_player.get('internal_id') or "")
                clicktt_id = str(selected_player.get('person_id') or "")
                if not nuid:
                    console.print("[red]错误: 找不到该球员的 NUID (internal_id)，无法获取历史记录。[/red]")
                    continue
                render_ttr_history(api, nuid, clicktt_id=clicktt_id)
            elif sub_choice == "2":
                club_name = selected_player.get('club_name')
                if not club_name or club_name == "-":
                    console.print("[yellow]该球员没有俱乐部信息，无法查询队伍。[/yellow]")
                else:
                    club_search_results = api.search_clubs(club_name)
                    club_items = club_search_results.get("results", [])
                    if club_items:
                        target_club = club_items[0]
                        club_number = str(target_club.get('clubnr'))
                        organization = target_club.get('organization_short')
                        if club_number and organization:
                            render_club_teams(api, club_number, organization)
                        else:
                            console.print(f"[yellow]未找到俱乐部 \'{club_name}\' 的完整信息 (clubnr/organization_short)。[/yellow]")
                    else:
                        console.print(f"[yellow]未找到俱乐部 \'{club_name}\' 的详细信息。[/yellow]")
            else:
                console.print("[red]无效选择，请重新输入。[/red]")


def render_search_clubs(api: MyTTApi, query: str) -> None:
    result = api.search_clubs(query)
    data = result if isinstance(result, dict) else {}
    items = data.get("results", []) or []
    
    table = Table(title=f"🔍 俱乐部搜索: {query}", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("俱乐部名称", width=30)
    table.add_column("Club Nr", width=10)
    table.add_column("协会", width=10)
    table.add_column("External ID", width=12)

    for item in items:
        table.add_row(item.get("clubname", "-")[:30], str(item.get("clubnr", "-")), item.get("organization_short", "-"), str(item.get("external_id", "-")))

    console.print(table)


def render_ttr_player(api: MyTTApi, nuid: str) -> None:
    data = api.get_ttr_player(nuid)
    ttr_val = data.get("ttr")
    ttr_text, ttr_style = _format_ttr(ttr_val)
    
    table = Table(title=f"👤 球员信息: {nuid}", box=box.ROUNDED, show_header=False)
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    table.add_row("NUID", nuid)
    table.add_row("实时 TTR", f"[{ttr_style}]{ttr_text}[/{ttr_style}]")
    if data.get("error"):
        table.add_row("Error", f"[red]{data['error']}[/red]")
    console.print(table)


def render_team_players(api: MyTTApi, team_id: str) -> None:
    data = api.get_team_players(team_id)
    roster = data.get("data", []) or []
    
    table = Table(title=f"📋 球队阵容 (TeamID: {team_id})", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("排名", justify="right", width=6)
    table.add_column("姓名", width=25)
    table.add_column("Internal ID", width=15)

    for p in roster:
        name = f"{p.get('lastname', '')} {p.get('firstname', '')}".strip()
        table.add_row(str(p.get("rank", "-")), name[:25], str(p.get("internal_id", "-")))

    console.print(table)


def render_team_schedule_api(api: MyTTApi, team_id: str, season: str = "25--26") -> None:
    data = api.get_team_schedule_api(team_id, season)
    matches = data.get("data", []) or []
    
    table = Table(title=f"📅 球队赛程 (TeamID: {team_id}, {season})", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("日期", width=12)
    table.add_column("对手名称", width=30)
    table.add_column("对手 TeamID", width=15)

    for m in matches:
        date = (m.get("date", "-") or "-")[:10]
        table.add_row(date, m.get("opponent_team_name", "-")[:30], str(m.get("opponent_team_id", "-")))

    console.print(table)


def render_club_teams(api: MyTTApi, club_number: str, organization: str) -> None:
    data = api.get_club_teams(club_number, organization)
    teams = data.get("data", []) or []
    
    table = Table(title=f"🏢 俱乐部球队 (Club: {club_number}, {organization})", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("球队名称", width=25)
    table.add_column("联赛名称", width=30)
    table.add_column("Team ID", justify="right")
    table.add_column("Group ID", justify="right")

    for t in teams:
        table.add_row(t.get("team_name", "-")[:25], t.get("league_name", "-")[:30], str(t.get("team_id", "-")), str(t.get("group_id", "-")))

    console.print(table)


def render_league_table_api(api: MyTTApi, association: str, league_id: str) -> None:
    data = api.get_league_table_api(association, league_id)
    # 假设返回结构中包含 entries 或类似的列表
    # 实际上可能是直接的一个列表或者在 data['table'] 里
    table_data = data.get("data", [])
    if isinstance(table_data, dict):
        table_data = table_data.get("table", [])
    
    table = Table(title=f"🏆 联赛排名表 (League: {league_id})", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("排", justify="right", width=4)
    table.add_column("球队", width=25)
    table.add_column("场", justify="right", width=4)
    table.add_column("胜-平-负", justify="center", width=10)
    table.add_column("球数", justify="center", width=10)
    table.add_column("积分", justify="right", width=6, style="bold green")

    for entry in table_data:
        rank = str(entry.get("rank", "-"))
        name = entry.get("team_name", "-")
        matches = str(entry.get("matches_played", "-"))
        wld = f"{entry.get('matches_won','0')}-{entry.get('matches_draw','0')}-{entry.get('matches_lost','0')}"
        sets = f"{entry.get('games_won','0')}:{entry.get('games_lost','0')}"
        points = str(entry.get("points", "-"))
        table.add_row(rank, name[:25], matches, wld, sets, points)

    console.print(table)


def render_meeting_live(api: MyTTApi, meeting_id: str) -> None:
    data = api.get_meeting_live(meeting_id)
    # Live 接口通常返回当前比分、正在进行的场次等
    # 结构示例: {"data": {"team_home": "...", "team_away": "...", "matches": [...]}}
    live_data = data.get("data", {})
    home = live_data.get("team_home", "Home")
    away = live_data.get("team_away", "Away")
    score = f"{live_data.get('matches_won_home', 0)} : {live_data.get('matches_won_away', 0)}"

    console.print(Panel(f"[bold white]{home}[/bold white]  [yellow]{score}[/yellow]  [bold white]{away}[/bold white]", title="Live Score", border_style="green"))

    matches = live_data.get("matches", [])
    if matches:
        table = Table(box=box.ROUNDED, header_style="bold cyan")
        table.add_column("场次", width=6)
        table.add_column("对阵", width=40)
        table.add_column("状态", width=10)
        table.add_column("比分", width=10, justify="center")
        
        for m in matches:
            idx = str(m.get("match_order", "-"))
            p1 = f"{m.get('player_home_name_1', '')} {m.get('player_home_name_2', '')}".strip()
            p2 = f"{m.get('player_away_name_1', '')} {m.get('player_away_name_2', '')}".strip()
            state = m.get("state", "-")
            m_score = f"{m.get('sets_won_home', 0)}:{m.get('sets_won_away', 0)}"
            table.add_row(idx, f"{p1} vs {p2}"[:40], state, m_score)
        console.print(table)
    else:
        console.print("[yellow]暂无详细场次数据。[/yellow]")


def show_common_menu() -> None:
    table = Table(title="🚀 MyTT CLI 常用功能", box=box.ROUNDED, header_style="bold blue")
    table.add_column("编号", style="cyan", width=6, justify="center")
    table.add_column("功能", style="bold white")
    table.add_column("输入参数说明", style="magenta")
    for a in COMMON_ACTIONS:
        hint = ", ".join([p[0] for p in a["params"]])
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
        table.add_row(str(i), item["name"], ", ".join([p[0] for p in item["params"]]))
    table.add_row("b", "返回主菜单", "-")
    console.print(table)


def run_all_get_menu(api: MyTTApi) -> None:
    while True:
        show_all_get_menu()
        choice = Prompt.ask("选择接口编号").strip().lower()
        if choice == "b": return
        if not choice.isdigit():
            console.print("[red]无效输入。[/red]")
            continue
        idx = int(choice)
        if 1 <= idx <= len(ALL_GET_ACTIONS):
            item = ALL_GET_ACTIONS[idx - 1]
            kwargs = {}
            for p_name, p_hint in item["params"]:
                if p_name == "params":
                    import json
                    raw = prompt_param("params", p_hint)
                    try: kwargs[p_name] = json.loads(raw)
                    except: kwargs[p_name] = {}
                else:
                    kwargs[p_name] = prompt_param(p_name, p_hint, allow_empty=True)
            
            res = getattr(api, item["name"])(**kwargs)
            show_json(res, title=f"Result: {item['name']}")
        else:
            console.print("[red]编号超出范围。[/red]")

load_dotenv(dotenv_path=ROOT / ".env", override=True)

def main() -> None:
    token_default = os.getenv("MYTT_COOKIE", "")
    token = Prompt.ask("🔑 Cookie Token (可选)", default=token_default).strip()
    api = MyTTApi(cookie_token=token)

    console.print(Panel.fit("[bold blue]myTischtennis 助手[/bold blue]\n[dim]支持球员搜索、TTR历史、球队分析等[/dim]", border_style="blue", title="MyTT CLI v1.0"))
    
    while True:
        show_common_menu()
        choice = Prompt.ask("👉 请选择").strip().lower()
        if choice == "q": break
        if choice == "a":
            run_all_get_menu(api)
            continue

        selected = next((a for a in COMMON_ACTIONS if a["key"] == choice), None)
        if not selected:
            console.print("[red]无效选择。[/red]")
            continue

        kwargs = {}
        for p_name, p_hint in selected["params"]:
            val = prompt_param(p_name, p_hint, allow_empty=(p_name == "season"))
            if p_name == "season" and not val: val = "25--26"
            kwargs[p_name] = val

        # 路由到对应的渲染函数
        f = selected["func"]
        if f == "search_players": render_search_players(api, kwargs["query"])
        elif f == "search_clubs": render_search_clubs(api, kwargs["query"])
        elif f == "get_ttr_player": render_ttr_player(api, kwargs["nuid"])
        elif f == "get_ttr_history": render_ttr_history(api, kwargs["nuid"])
        elif f == "get_team_players": render_team_players(api, kwargs["team_id"])
        elif f == "team_analysis": run_team_analysis(api, kwargs["team_id"])
        elif f == "get_team_schedule_api": render_team_schedule_api(api, kwargs["team_id"], kwargs.get("season", "25--26"))
        elif f == "get_club_teams": render_club_teams(api, kwargs["club_number"], kwargs["organization"])
        elif f == "get_league_table_api": render_league_table_api(api, kwargs["association"], kwargs["league_id"])
        elif f == "get_meeting_live": render_meeting_live(api, kwargs["meeting_id"])
        elif f == "run_war_room": run_war_room(api, kwargs["my_team_id"])
        else:
            res = getattr(api, f)(**kwargs)
            show_json(res, title=f"Result: {f}")


if __name__ == "__main__":
    main()

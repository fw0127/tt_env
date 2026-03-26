import os
import re
import dotenv
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

    def get_ttr_history(self, nuid: str) -> Dict[str, Any]:
        return self._get(f"/api/ttr/history/{nuid}")

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


def show_json(data: Any) -> None:
    console.print_json(data=data if isinstance(data, (dict, list)) else {"data": str(data)})


def run_team_analysis(api: MyTTApi, team_id: str) -> None:
    """
    集成 get_mannschafts_aufstellung.py 的核心逻辑：
    先取 team players，再逐人调用 ttr/player 获取实时 TTR。
    """
    roster = api.get_team_players(team_id).get("data", [])
    if not roster:
        console.print("[red]未获取到球队阵容，请检查 teamId。[/red]")
        return

    table = Table(title=f"球队分析 TeamID={team_id}", box=box.ROUNDED)
    table.add_column("排名", style="cyan", justify="right")
    table.add_column("姓名", style="bold white")
    table.add_column("NUID", style="yellow")
    table.add_column("实时TTR", style="green", justify="right")

    for p in roster:
        rank = str(p.get("rank", "-"))
        first = p.get("firstname", "")
        last = p.get("lastname", "")
        nuid = str(p.get("internal_id", ""))
        ttr_resp = api.get_ttr_player(nuid) if nuid else {}
        ttr_value = ttr_resp.get("ttr", "N/A")
        ttr_text = str(ttr_value) if ttr_value is not None else "需登录/不可见"
        table.add_row(rank, f"{last} {first}".strip(), nuid, ttr_text)

    console.print(table)


def render_ttr_history(api: MyTTApi, nuid: str) -> None:
    """
    输出格式对齐你现有的 `get_ttr_history.py`：
    倒序、取最近 15 场、delta/比分颜色、无 match 时输出汇总行。
    """
    data = api.get_ttr_history(nuid)
    if not isinstance(data, dict) or "event" not in data:
        show_json(data)
        return

    events = list(reversed(data.get("event", [])))
    recent_events = events[:15]

    person_name = data.get("person_name", "N/A")
    current_ttr = data.get("ttr", "N/A")
    console.print(f"\n[bold magenta]📈 球员: {person_name} | 当前 TTR: {current_ttr}[/bold magenta]")
    console.print(f"📋 分析范围: 最近 {len(recent_events)} 场比赛")
    console.print("=" * 110)

    table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE_HEAVY)
    table.add_column("日期", width=12, justify="left")
    table.add_column("变动", width=6, justify="right")
    table.add_column("赛后", width=6, justify="right")
    table.add_column("比分", width=8, justify="left")
    table.add_column("对手 (TTR)", width=25, justify="left")
    table.add_column("赛事", width=30, justify="left")

    for ev in recent_events:
        date = (ev.get("event_date_time", "N/A") or "N/A")[:10]
        delta = ev.get("ttr_delta", 0)
        after = ev.get("ttr_after", "N/A")
        e_name = ev.get("event_name", "N/A")

        if delta > 0:
            delta_text = f"+{delta}"
            delta_style = "green"
        elif delta < 0:
            delta_text = str(delta)
            delta_style = "red"
        else:
            delta_text = str(delta)
            delta_style = None

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
                if len(opp_info) > 24:
                    opp_info = opp_info[:22] + ".."

                short_e = e_name.split("|")[-1].strip() if "|" in str(e_name) else e_name
                table.add_row(
                    date,
                    f"[{delta_style}]{delta_text}[/{delta_style}]" if delta_style else delta_text,
                    str(after),
                    f"[{score_style}]{score_raw}[/{score_style}]",
                    opp_info,
                    short_e[:30],
                )
        else:
            vs_info = e_name.split("|")[-1].strip() if "|" in str(e_name) else "汇总"
            event_tail = f"{e_name[:30]}..." if len(str(e_name)) > 30 else str(e_name)
            table.add_row(
                date,
                f"[{delta_style}]{delta_text}[/{delta_style}]" if delta_style else delta_text,
                str(after),
                "-",
                vs_info,
                event_tail,
            )

    console.print(table)


def _table(box_style=box.SIMPLE_HEAVY) -> Table:
    t = Table(show_header=True, header_style="bold cyan", box=box_style)
    return t


def _format_ttr(value: Any) -> tuple[str | None, str | None]:
    """
    返回 (text, style) 用于 ttr 展示。
    """
    if value is None:
        return ("N/A", "red")
    if isinstance(value, (int, float)):
        return (str(value), "green")
    s = str(value).strip()
    if s == "" or s.lower() in {"none", "null", "n/a"}:
        return ("N/A", "red")
    # 常见：需登录可见、需登录/不可见、ERR 等
    if any(k in s for k in ["需登录", "不可见", "ERR", "Not authorized", "需 登录", "需 登录"]):
        return (s, "yellow")
    # 如果是纯数字，认为是正常 ttr
    if re.fullmatch(r"-?\d+", s):
        return (s, "green")
    return (s, "yellow")


def render_search_players(api: MyTTApi, query: str) -> None:
    result = api.search_players(query)
    data = result if isinstance(result, dict) else {}
    items = data.get("results", []) or []
    total = data.get("total_count", 0)
    pages_count = data.get("pages_count", 1) or 1
    page = data.get("page", 1) or 1
    pagesize = data.get("pagesize", 10) or 10

    # 如果接口返回多页，则自动拉取所有页后再渲染
    try:
        pages_count_int = int(pages_count)
    except Exception:
        pages_count_int = 1
    MAX_ITEMS = 200
    if pages_count_int > 1 and len(items) < min(MAX_ITEMS, int(total or 0) if str(total).isdigit() else MAX_ITEMS):
        all_items = list(items)
        for p in range(int(page) + 1, pages_count_int + 1):
            resp = api.search_players(query, page=p, pagesize=pagesize)
            resp_data = resp if isinstance(resp, dict) else {}
            chunk = resp_data.get("results", []) or []
            all_items.extend(chunk)
            if len(all_items) >= MAX_ITEMS:
                break
        items = all_items[:MAX_ITEMS]

    console.print(f"\n[bold blue]🔍 球员搜索:[/bold blue] [bold]{query}[/bold] | 共 {total} 条")

    table = _table()
    table.add_column("姓名", width=20, justify="left")
    table.add_column("俱乐部", width=26, justify="left")
    table.add_column("TTR", width=12, justify="right")
    table.add_column("Person ID", width=14, justify="left")
    table.add_column("DTTB ID", width=10, justify="left")

    if not items:
        table.add_row("-", "-", "-", "-", "-")
        console.print(table)
        return

    for item in items:
        fname = item.get("firstname", "") or ""
        lname = item.get("lastname", "") or ""
        name = f"{lname} {fname}".strip() or "-"
        club = item.get("club_name", "无俱乐部/未公开") or "-"
        ttr_text, ttr_style = _format_ttr(item.get("ttr", "需登录可见"))
        p_id = item.get("person_id", "N/A") or "N/A"
        dttb_id = item.get("dttb_player_id", "N/A") or "N/A"
        table.add_row(
            name[:20],
            club[:26],
            f"[{ttr_style}]{ttr_text}[/{ttr_style}]" if ttr_style else ttr_text,
            str(p_id)[:14],
            str(dttb_id)[:10],
        )

    console.print(table)


def render_search_clubs(api: MyTTApi, query: str) -> None:
    result = api.search_clubs(query)
    data = result if isinstance(result, dict) else {}
    items = data.get("results", []) or []
    total = data.get("total_count", 0)
    pages_count = data.get("pages_count", 1) or 1
    page = data.get("page", 1) or 1
    pagesize = data.get("pagesize", 10) or 10

    try:
        pages_count_int = int(pages_count)
    except Exception:
        pages_count_int = 1
    MAX_ITEMS = 200
    if pages_count_int > 1 and len(items) < min(MAX_ITEMS, int(total or 0) if str(total).isdigit() else MAX_ITEMS):
        all_items = list(items)
        for p in range(int(page) + 1, pages_count_int + 1):
            resp = api.search_clubs(query, page=p, pagesize=pagesize)
            resp_data = resp if isinstance(resp, dict) else {}
            chunk = resp_data.get("results", []) or []
            all_items.extend(chunk)
            if len(all_items) >= MAX_ITEMS:
                break
        items = all_items[:MAX_ITEMS]

    console.print(f"\n[bold blue]🔍 俱乐部搜索:[/bold blue] [bold]{query}[/bold] | 共 {total} 条")

    table = _table(box_style=box.SIMPLE_HEAVY)
    table.add_column("俱乐部", width=26, justify="left")
    table.add_column("clubnr", width=10, justify="right")
    table.add_column("组织(短)", width=14, justify="left")
    table.add_column("external_id", width=14, justify="left")

    if not items:
        table.add_row("-", "-", "-", "-")
        console.print(table)
        return

    for item in items:
        name = item.get("clubname", "N/A") or "N/A"
        nr = str(item.get("clubnr", "N/A") or "N/A")
        org = item.get("organization_short", "N/A") or "N/A"
        ext_id = str(item.get("external_id", "N/A") or "N/A")
        table.add_row(name[:26], nr[-10:], org[:14], ext_id[:14])

    console.print(table)


def render_ttr_player(api: MyTTApi, nuid: str) -> None:
    data = api.get_ttr_player(nuid)
    if not isinstance(data, dict):
        show_json(data)
        return

    ttr_text, ttr_style = _format_ttr(data.get("ttr"))
    err = data.get("error")

    table = _table()
    table.add_column("字段", width=12, justify="left")
    table.add_column("值", width=40, justify="left")
    table.add_row("NUID", nuid)
    table.add_row("TTR", f"[{ttr_style}]{ttr_text}[/{ttr_style}]" if ttr_style else ttr_text)
    if err:
        table.add_row("错误", str(err)[:60])
    console.print(table)


def render_team_players(api: MyTTApi, team_id: str) -> None:
    data = api.get_team_players(team_id)
    if not isinstance(data, dict):
        show_json(data)
        return
    roster = data.get("data", []) or []

    console.print(f"\n[bold blue]📋 球队阵容:[/bold blue] TeamID={team_id} | 共 {len(roster)} 人")

    table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE_HEAVY)
    table.add_column("排名", width=6, justify="right")
    table.add_column("姓名", width=22, justify="left")
    table.add_column("NUID", width=14, justify="left")

    if not roster:
        table.add_row("-", "-", "-")
        console.print(table)
        return

    for p in roster:
        rank = str(p.get("rank", "-"))
        fname = p.get("firstname", "") or ""
        lname = p.get("lastname", "") or ""
        nuid = str(p.get("internal_id", "") or "")
        table.add_row(rank, f"{lname} {fname}".strip()[:22], nuid[:14])

    console.print(table)


def show_common_menu() -> None:
    table = Table(title="常用功能", box=box.ROUNDED)
    table.add_column("编号", style="cyan", width=6)
    table.add_column("功能", style="bold white")
    table.add_column("说明", style="magenta")
    for a in COMMON_ACTIONS:
        hint = ", ".join([p[0] for p in a["params"]])
        table.add_row(a["key"], a["label"], hint)
    table.add_row("a", "全量 GET 接口菜单", "覆盖文档中全部 GET 接口")
    table.add_row("q", "退出", "-")
    console.print(table)


def show_all_get_menu() -> None:
    table = Table(title="全量 GET 接口（文档映射）", box=box.SIMPLE_HEAVY)
    table.add_column("编号", style="cyan", width=6)
    table.add_column("方法名", style="bold white")
    table.add_column("参数", style="magenta")
    for i, item in enumerate(ALL_GET_ACTIONS, start=1):
        table.add_row(str(i), item["name"], ", ".join([p[0] for p in item["params"]]))
    table.add_row("b", "返回", "-")
    console.print(table)


def run_all_get_menu(api: MyTTApi) -> None:
    while True:
        show_all_get_menu()
        choice = Prompt.ask("选择接口编号（b返回）").strip().lower()
        if choice == "b":
            return
        if not choice.isdigit():
            console.print("[red]请输入有效编号。[/red]")
            continue
        idx = int(choice)
        if idx < 1 or idx > len(ALL_GET_ACTIONS):
            console.print("[red]编号超出范围。[/red]")
            continue

        item = ALL_GET_ACTIONS[idx - 1]
        kwargs: Dict[str, Any] = {}
        for p_name, p_hint in item["params"]:
            if p_name == "params":
                raw = prompt_param("params", p_hint)
                try:
                    import json
                    kwargs[p_name] = json.loads(raw)
                except Exception:
                    console.print("[red]JSON 解析失败。示例: {\"continent\":\"Europa\"}[/red]")
                    kwargs[p_name] = {}
            else:
                allow_empty = p_name in {"season", "filter_", "club_slug", "as_code", "di"}
                val = prompt_param(p_name, p_hint, allow_empty=allow_empty)
                kwargs[p_name] = val

        func = getattr(api, item["name"])
        result = func(**kwargs)
        show_json(result)

load_dotenv(dotenv_path=ROOT / ".env", override=True)

def main() -> None:
    token_default = os.getenv("MYTT_COOKIE", "")
    token = Prompt.ask("可选：输入 Cookie Token（回车则匿名）", default=token_default).strip()
    api = MyTTApi(cookie_token=token)

    console.print(Panel.fit("myTischtennis 统一菜单入口", border_style="blue", title="MyTT CLI"))
    while True:
        show_common_menu()
        choice = Prompt.ask("请选择功能").strip().lower()
        if choice == "q":
            console.print("[cyan]已退出。[/cyan]")
            break
        if choice == "a":
            run_all_get_menu(api)
            continue

        selected = next((a for a in COMMON_ACTIONS if a["key"] == choice), None)
        if not selected:
            console.print("[red]无效选择。[/red]")
            continue

        kwargs: Dict[str, Any] = {}
        for p_name, p_hint in selected["params"]:
            allow_empty = p_name in {"season"}
            value = prompt_param(p_name, p_hint, allow_empty=allow_empty)
            if p_name == "season" and not value:
                value = "25--26"
            kwargs[p_name] = value

        if selected["func"] == "team_analysis":
            run_team_analysis(api, kwargs["team_id"])
        elif selected["func"] == "get_ttr_history":
            render_ttr_history(api, kwargs["nuid"])
        elif selected["func"] == "search_players":
            render_search_players(api, kwargs["query"])
        elif selected["func"] == "search_clubs":
            render_search_clubs(api, kwargs["query"])
        elif selected["func"] == "get_ttr_player":
            render_ttr_player(api, kwargs["nuid"])
        elif selected["func"] == "get_team_players":
            render_team_players(api, kwargs["team_id"])
        else:
            result = getattr(api, selected["func"])(**kwargs)
            show_json(result)


if __name__ == "__main__":
    main()

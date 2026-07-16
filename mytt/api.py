"""myTischtennis API 封装与数据整理工具。"""
import hashlib
import re
from typing import Any, Dict, List
from urllib.parse import quote

import requests

from . import cache
from .ui import console


def _slug(value: str) -> str:
    return value.strip().replace(" ", "_")


def clean_roster(raw_roster: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """清洗球队阵容：按 internal_id 去重（保留最后一条，即下半赛季 RR 数据）、
    只保留本赛季有数字排名的队员、按排名排序。"""
    roster_map: Dict[Any, Dict[str, Any]] = {}
    for p in raw_roster:
        nuid = p.get("internal_id")
        if nuid:
            roster_map[nuid] = p

    roster = [p for p in roster_map.values() if p.get("rank") and str(p.get("rank"))[0].isdigit()]

    try:
        roster.sort(key=lambda x: float(re.findall(r"\d+\.?\d*", str(x.get("rank", "999")))[0]))
    except Exception:
        pass
    return roster


class MyTTApi:
    """
    统一 API 封装。
    包含文档里的所有 GET 接口，并保留搜索 POST 接口便于菜单实用化。
    """

    BASE_URL = "https://www.mytischtennis.de"

    def __init__(self, cookie_token: str = "") -> None:
        # 缓存按 Token 隔离：换 Token 后不会读到旧身份下的缓存数据
        self._cache_scope = hashlib.sha1(cookie_token.encode()).hexdigest()[:8] if cookie_token else "anon"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.mytischtennis.de/",
            "X-Requested-With": "XMLHttpRequest",
        })

        if cookie_token:
            # 1. 作为原始 Header 注入
            self.session.headers["Cookie"] = cookie_token

            # 2. 同时解析并注入 CookieJar，增强兼容性
            # 假设格式为: sb-10-auth-token=base64-xxx; other_key=val
            try:
                for part in cookie_token.split(";"):
                    if "=" in part:
                        name, value = part.strip().split("=", 1)
                        self.session.cookies.set(name, value, domain="www.mytischtennis.de")
                console.print(f"[green]✔ Token 已成功加载到 Session (长度: {len(cookie_token)})[/green]")
            except Exception as e:
                console.print(f"[yellow]⚠ Token 解析微调: {e}[/yellow]")

    # ---- 基础请求 ----
    @staticmethod
    def _cacheable(result: Any) -> bool:
        """只缓存成功响应，错误结果不落盘。"""
        return not (isinstance(result, dict) and "error" in result)

    def _get(self, path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        key = cache.make_key(self._cache_scope, "GET", path, params)
        cached = cache.get(key, path)
        if cached is not None:
            return cached

        url = f"{self.BASE_URL}{path}"
        try:
            r = self.session.get(url, params=params, timeout=30)

            # 401/403 说明 Token 可能失效
            if r.status_code in [401, 403]:
                return {"error": "认证失败", "status_code": r.status_code, "msg": "Token 可能已过期或无效"}

            result = r.json()
        except Exception as e:
            text_preview = r.text[:500] if "r" in locals() else str(e)
            return {"error": "Request Failed", "content": text_preview}

        if self._cacheable(result):
            cache.put(key, path, result)
        return result

    def _post(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        key = cache.make_key(self._cache_scope, "POST", path, data)
        cached = cache.get(key, path)
        if cached is not None:
            return cached

        url = f"{self.BASE_URL}{path}"
        try:
            # myTT 的搜索接口通常接收 Form Data 而非 JSON
            r = self.session.post(url, data=data, timeout=30)
            try:
                result = r.json()
            except Exception as e:
                return {"error": "POST JSON parse failed", "status_code": r.status_code, "msg": str(e)[:120]}
        except Exception as e:
            return {"error": "POST Failed", "msg": str(e)}

        if self._cacheable(result):
            cache.put(key, path, result)
        return result

    def _loader(self, path: str, route: str) -> Dict[str, Any]:
        """请求 Remix loader 接口（带 _data 路由参数的页面数据接口）。"""
        return self._get(path, {"_data": route})

    @staticmethod
    def _group_path(association: str, season: str, league_slug: str, group_id: str) -> str:
        return f"/click-tt/{association}/{season}/ligen/{_slug(league_slug)}/gruppe/{group_id}"

    @staticmethod
    def _club_path(association: str, season: str, club_id: str, club_slug: str) -> str:
        return f"/click-tt/{association}/{season}/verein/{club_id}/{_slug(club_slug)}"

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
            match = re.search(r"\d+", nuid)
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
        self, association: str, season: str, league_slug: str, group_id: str,
        team_id: str, team_name: str, filter_: str = "gesamt",
    ) -> Dict[str, Any]:
        return self._loader(
            f"{self._group_path(association, season, league_slug, group_id)}/mannschaft/{team_id}/{_slug(team_name)}/spielerbilanzen/{filter_}",
            "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/mannschaft.$teamid.$teamname+/spielerbilanzen.$filter",
        )

    def get_team_schedule_loader(
        self, association: str, season: str, league_slug: str, group_id: str,
        team_id: str, team_name: str, filter_: str = "gesamt",
    ) -> Dict[str, Any]:
        return self._loader(
            f"{self._group_path(association, season, league_slug, group_id)}/mannschaft/{team_id}/{_slug(team_name)}/spielplan/{filter_}",
            "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/mannschaft.$teamid.$teamname+/spielplan.$filter",
        )

    def get_team_info_loader(
        self, association: str, season: str, league_slug: str, group_id: str, team_id: str, team_name: str
    ) -> Dict[str, Any]:
        return self._loader(
            f"{self._group_path(association, season, league_slug, group_id)}/mannschaft/{team_id}/{_slug(team_name)}/infos",
            "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/mannschaft.$teamid.$teamname+/infos",
        )

    def get_club_teams(self, club_number: str, organization: str) -> Dict[str, Any]:
        return self._get("/api/ttr/teams", {"clubNumber": club_number, "organization": organization})

    def get_club_teams_loader(self, association: str, season: str, club_id: str, club_slug: str = "x") -> Dict[str, Any]:
        return self._loader(
            f"{self._club_path(association, season, club_id, club_slug)}/mannschaften",
            "routes/click-tt+/$association+/$season+/verein.$clubid.$clubname+/mannschaften",
        )

    def get_club_schedule_loader(self, association: str, season: str, club_id: str, club_slug: str = "x") -> Dict[str, Any]:
        return self._loader(
            f"{self._club_path(association, season, club_id, club_slug)}/spielplan",
            "routes/click-tt+/$association+/$season+/verein.$clubid.$clubname+/spielplan",
        )

    def get_club_balance_loader(
        self, association: str, season: str, club_id: str, club_slug: str = "x", filter_: str = "gesamt"
    ) -> Dict[str, Any]:
        return self._loader(
            f"{self._club_path(association, season, club_id, club_slug)}/bilanzen/{filter_}",
            "routes/click-tt+/$association+/$season+/verein.$clubid.$clubname+/bilanzen.$filter",
        )

    def get_club_info_loader(self, association: str, season: str, club_id: str, club_slug: str = "x") -> Dict[str, Any]:
        return self._loader(
            f"{self._club_path(association, season, club_id, club_slug)}/info",
            "routes/click-tt+/$association+/$season+/verein.$clubid.$clubname+/info",
        )

    def get_league_table_api(self, association: str, league_id: str) -> Dict[str, Any]:
        return self._get(f"/api/league-table/{association}/{league_id}")

    def get_group_table_loader(
        self, association: str, season: str, league_slug: str, group_id: str, filter_: str = "gesamt"
    ) -> Dict[str, Any]:
        return self._loader(
            f"{self._group_path(association, season, league_slug, group_id)}/tabelle/{filter_}",
            "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/tabelle.$filter",
        )

    def get_group_schedule_loader(
        self, association: str, season: str, league_slug: str, group_id: str, filter_: str = "gesamt"
    ) -> Dict[str, Any]:
        return self._loader(
            f"{self._group_path(association, season, league_slug, group_id)}/spielplan/{filter_}",
            "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/spielplan.$filter",
        )

    def get_group_contacts_loader(self, association: str, season: str, league_slug: str, group_id: str) -> Dict[str, Any]:
        return self._loader(
            f"{self._group_path(association, season, league_slug, group_id)}/kontakte",
            "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/kontakte",
        )

    def get_group_balances_loader(
        self, association: str, season: str, league_slug: str, group_id: str, filter_: str = "gesamt"
    ) -> Dict[str, Any]:
        return self._loader(
            f"{self._group_path(association, season, league_slug, group_id)}/bilanzuebersichten/{filter_}",
            "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/bilanzuebersichten.$filter",
        )

    def get_group_team_registrations_loader(
        self, association: str, season: str, league_slug: str, group_id: str, filter_: str = "gesamt"
    ) -> Dict[str, Any]:
        return self._loader(
            f"{self._group_path(association, season, league_slug, group_id)}/mannschaftsmeldungen/{filter_}",
            "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/mannschaftsmeldungen.$filter",
        )

    def get_group_rankings_loader(
        self, association: str, season: str, league_slug: str, group_id: str, match_type: str, filter_: str = "gesamt"
    ) -> Dict[str, Any]:
        return self._loader(
            f"{self._group_path(association, season, league_slug, group_id)}/gruppen-ranglisten/{match_type}/{filter_}",
            "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/gruppen-ranglisten.$matchtype.$filter",
        )

    def get_group_viewer_matrix_loader(self, association: str, season: str, league_slug: str, group_id: str) -> Dict[str, Any]:
        return self._loader(
            f"{self._group_path(association, season, league_slug, group_id)}/zuschauer-matrix",
            "routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/zuschauer-matrix",
        )

    def get_region_schedule_loader(self, association: str, season: str, championship: str) -> Dict[str, Any]:
        return self._loader(
            f"/click-tt/{association}/{season}/regionsspielplan/{quote(championship, safe='')}",
            "routes/click-tt+/$association+/$season+/regionsspielplan.$region",
        )

    def get_league_tree_loader(self, association: str, season: str, type_: str, championship: str) -> Dict[str, Any]:
        return self._loader(
            f"/click-tt/{association}/{season}/{type_}/{quote(championship, safe='')}",
            "routes/click-tt+/$association+/$season+/$type+/$championship",
        )

    def get_meeting_live(self, meeting_id: str) -> Dict[str, Any]:
        return self._get(f"/api/meeting/{meeting_id}/live")

    # ---- 保留实用 POST 搜索 ----
    def search_players(self, query: str, page: int = 1, pagesize: int = 10) -> Dict[str, Any]:
        return self._post("/api/search/players", {"query": query, "page": page, "pagesize": pagesize})

    def search_clubs(self, query: str, page: int = 1, pagesize: int = 10) -> Dict[str, Any]:
        return self._post("/api/search/clubs", {"query": query, "page": page, "pagesize": pagesize})

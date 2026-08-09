"""FastAPI Web 界面：复用 mytt 包逻辑，提供 JSON API 并托管静态前端。

启动: python web.py  （或 uvicorn mytt.web:app）
"""
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import dotenv_values, load_dotenv
from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import auth, cache, favorites, review
from .analysis import collect_team_analysis, collect_war_room
from .api import MyTTApi, clean_roster

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"

load_dotenv(dotenv_path=ROOT / ".env", override=True)

# 当前 Token 状态（_set_current 统一维护）
_api: MyTTApi
_token: str = ""
_token_exp: Optional[int] = None
_last_refresh_try: float = 0.0


def _set_current(cookie: str) -> None:
    global _api, _token, _token_exp
    _token = cookie or ""
    _token_exp = auth.session_expires_at(_token) if _token else None
    _api = MyTTApi(cookie_token=_token)


# 启动时：尝试静默续期（不读浏览器，避免无故弹钥匙串授权）
_startup_cookie, _startup_status = auth.ensure_fresh(os.getenv("MYTT_COOKIE", ""), allow_browser=False)
_set_current(_startup_cookie or "")


async def _cache_control(refresh: bool = False):
    """所有接口通用的 ?refresh=1 参数：本次请求跳过本地缓存，强制上网获取。"""
    token = cache.bypass.set(refresh)
    try:
        yield
    finally:
        cache.bypass.reset(token)


def _token_keeper():
    """请求前维护 Token：
    1) 自愈：内存中无 Token 或即将过期时，从 .env 重新读取更新的 Token
       （CLI 或上次浏览器导入可能已写入更 fresh 的 Token，无需重启服务）。
    2) 快过期时尝试站点自动续期并写回 .env（60 秒冷却防止反复尝试）。"""
    global _last_refresh_try
    now = time.time()

    # 1) 从 .env 自愈（读文件而非 os.getenv，后者是启动时的旧值）
    if not _token or (_token_exp and _token_exp - now < 60):
        try:
            env_cookie = dotenv_values(ROOT / ".env").get("MYTT_COOKIE", "") or ""
        except Exception:
            env_cookie = ""
        env_exp = auth.session_expires_at(env_cookie) if env_cookie else None
        if env_exp and env_exp - now > 60 and env_cookie != _token:
            _set_current(env_cookie)
            return

    # 2) 快过期时站点续期
    if _token and _token_exp and _token_exp - now < 120 and now - _last_refresh_try > 60:
        _last_refresh_try = now
        new, status = auth.ensure_fresh(_token, allow_browser=False)
        if status == "refreshed" and new:
            _set_current(new)


app = FastAPI(title="MyTT Web", docs_url="/docs", dependencies=[Depends(_cache_control), Depends(_token_keeper)])


class TokenBody(BaseModel):
    token: str = ""


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# ---------- 配置 ----------

@app.get("/api/config")
def get_config() -> Dict[str, Any]:
    return {"has_token": bool(_token), "expires_at": _token_exp}


@app.post("/api/config/token")
def set_token(body: TokenBody) -> Dict[str, Any]:
    token = body.token.strip()
    _set_current(token)
    if token:
        auth.save_token(token)
    return {"ok": True, "has_token": bool(token), "expires_at": _token_exp}


@app.post("/api/config/token/auto")
def auto_token() -> Dict[str, Any]:
    """自动获取 Token：先尝试续期现有 Token，失败则从本机浏览器导入。"""
    cookie, status = auth.ensure_fresh(_token, allow_browser=True)
    if cookie and status != "manual_required":
        _set_current(cookie)
    return {"status": status, "has_token": bool(_token), "expires_at": _token_exp}


# ---------- 缓存管理 ----------

@app.get("/api/cache/stats")
def cache_stats() -> Dict[str, Any]:
    return cache.stats()


@app.post("/api/cache/clear")
def cache_clear() -> Dict[str, Any]:
    return {"cleared": cache.clear()}


# ---------- 搜索 ----------

@app.get("/api/search/players")
def search_players(q: str) -> Dict[str, Any]:
    return _api.search_players(q)


@app.get("/api/search/clubs")
def search_clubs(q: str) -> Dict[str, Any]:
    return _api.search_clubs(q)


# ---------- 球员 ----------

@app.get("/api/player/{nuid}/ttr")
def player_ttr(nuid: str) -> Dict[str, Any]:
    return _api.get_ttr_player(nuid)


@app.get("/api/player/{nuid}/history")
def player_history(nuid: str, clicktt_id: str | None = None) -> Dict[str, Any]:
    return _api.get_ttr_history(nuid, clicktt_id=clicktt_id)


# ---------- 球队 ----------

@app.get("/api/team/{team_id}/players")
def team_players(team_id: str) -> Dict[str, Any]:
    return {"players": clean_roster(_api.get_team_players(team_id).get("data", []) or [])}


@app.get("/api/team/{team_id}/analysis")
def team_analysis(team_id: str) -> Dict[str, Any]:
    return {"players": collect_team_analysis(_api, team_id)}


@app.get("/api/team/{team_id}/schedule")
def team_schedule(team_id: str, season: str = "25--26") -> Dict[str, Any]:
    return _api.get_team_schedule_api(team_id, season)


@app.get("/api/team/{team_id}/warroom")
def war_room(team_id: str) -> Dict[str, Any]:
    return collect_war_room(_api, team_id)


# ---------- 俱乐部 / 联赛 / 比赛 ----------

@app.get("/api/club/teams")
def club_teams(club_number: str, organization: str) -> Dict[str, Any]:
    return _api.get_club_teams(club_number, organization)


@app.get("/api/league/{association}/{league_id}/table")
def league_table(association: str, league_id: str) -> Dict[str, Any]:
    return _api.get_league_table_api(association, league_id)


@app.get("/api/meeting/{meeting_id}/live")
def meeting_live(meeting_id: str) -> Dict[str, Any]:
    return _api.get_meeting_live(meeting_id)


# ---------- 赛后复盘 ----------

class NoteBody(BaseModel):
    key: str
    text: str = ""


@app.get("/api/h2h")
def head_to_head(nuid: str, opponent: str) -> Dict[str, Any]:
    """两名球员的全部交手记录（从 TTR 历史聚合）。"""
    return review.head_to_head(_api, nuid, opponent)


@app.get("/api/notes")
def get_note(key: str) -> Dict[str, Any]:
    return review.get_note(key)


@app.get("/api/notes/all")
def list_notes() -> Dict[str, Any]:
    return {"notes": review.list_notes()}


@app.post("/api/notes")
def save_note(body: NoteBody) -> Dict[str, Any]:
    return review.save_note(body.key.strip(), body.text)


# ---------- 关注列表 ----------

class FavBody(BaseModel):
    kind: str
    key: str
    name: str = ""
    extra: Optional[Dict[str, Any]] = None


@app.get("/api/favorites")
def favorites_list(kind: str | None = None) -> Dict[str, Any]:
    return {"favorites": favorites.list_favorites(kind)}


@app.post("/api/favorites")
def favorites_add(body: FavBody) -> Dict[str, Any]:
    return favorites.add(body.kind, body.key, body.name, body.extra)


@app.delete("/api/favorites")
def favorites_remove(kind: str, key: str) -> Dict[str, Any]:
    return favorites.remove(kind, key)


@app.get("/api/favorites/overview")
def favorites_overview() -> Dict[str, Any]:
    """关注面板：球员实时 TTR 与近况、球队下场比赛、俱乐部球队数。"""
    return favorites.overview(_api)

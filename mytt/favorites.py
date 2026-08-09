"""关注列表：球员 / 球队 / 俱乐部。

收藏项与复盘笔记共用同一个本机数据库（mytt_notes.db，已 gitignore），
存在 favorites 表里；overview() 在收藏项之上聚合实时数据，构成「关注面板」。

俱乐部的 key 用 "clubnr:协会简称"（查球队列表两者都需要）。
"""
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .analysis import player_recent_form
from .api import MyTTApi

DATA_DB = Path(__file__).resolve().parent.parent / "mytt_notes.db"
KINDS = ("player", "team", "club")


# ---------- 存储 ----------

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DATA_DB, timeout=10)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS favorites (
             kind TEXT NOT NULL, key TEXT NOT NULL, name TEXT, extra TEXT, added REAL,
             PRIMARY KEY (kind, key))"""
    )
    return conn


def _row(r) -> Dict[str, Any]:
    kind, key, name, extra, added = r
    try:
        ex = json.loads(extra) if extra else {}
    except Exception:
        ex = {}
    return {"kind": kind, "key": key, "name": name or key, "extra": ex, "added": added}


def list_favorites(kind: Optional[str] = None) -> List[Dict[str, Any]]:
    """全部关注项，按加入时间先后排列。"""
    sql = "SELECT kind, key, name, extra, added FROM favorites"
    try:
        with _conn() as conn:
            rows = (conn.execute(sql + " WHERE kind = ? ORDER BY added", (kind,))
                    if kind else conn.execute(sql + " ORDER BY kind, added")).fetchall()
        return [_row(r) for r in rows]
    except Exception:
        return []


def add(kind: str, key: str, name: str = "", extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if kind not in KINDS:
        return {"ok": False, "error": f"unknown kind: {kind}"}
    key = str(key or "").strip()
    if not key:
        return {"ok": False, "error": "empty key"}
    try:
        with _conn() as conn:
            # 重复关注只更新名称/附加信息，保留最初的加入时间（顺序不跳动）
            conn.execute(
                """INSERT OR REPLACE INTO favorites (kind, key, name, extra, added)
                   VALUES (?, ?, ?, ?, COALESCE(
                     (SELECT added FROM favorites WHERE kind = ? AND key = ?), ?))""",
                (kind, key, name or key, json.dumps(extra or {}, ensure_ascii=False), kind, key, time.time()),
            )
        return {"ok": True, "kind": kind, "key": key}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def remove(kind: str, key: str) -> Dict[str, Any]:
    try:
        with _conn() as conn:
            cur = conn.execute("DELETE FROM favorites WHERE kind = ? AND key = ?", (kind, str(key)))
        return {"ok": True, "removed": cur.rowcount}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


# ---------- 关注面板 ----------

def _player_entry(api: MyTTApi, f: Dict[str, Any]) -> Dict[str, Any]:
    """球员：实时 TTR + 近 5 场状态。"""
    entry = {**f, "ttr": None, "form": None}
    try:
        entry["ttr"] = api.get_ttr_player(f["key"]).get("ttr")
        entry["form"] = player_recent_form(api, f["key"])
    except Exception as e:
        entry["error"] = str(e)[:120]
    return entry


def _team_entry(api: MyTTApi, f: Dict[str, Any]) -> Dict[str, Any]:
    """球队：赛程里的下一场比赛。"""
    entry = {**f, "next": None}
    try:
        schedule = api.get_team_schedule_api(f["key"]).get("data") or []
        today = time.strftime("%Y-%m-%d")
        nxt = next((s for s in schedule if (s.get("date") or "")[:10] >= today), None)
        if nxt:
            entry["next"] = {
                "date": (nxt.get("date") or "")[:10],
                "opponent": nxt.get("opponent_team_name"),
                "opponent_id": nxt.get("opponent_team_id"),
            }
        entry["matches"] = len(schedule)
    except Exception as e:
        entry["error"] = str(e)[:120]
    return entry


def _club_entry(api: MyTTApi, f: Dict[str, Any]) -> Dict[str, Any]:
    """俱乐部：旗下球队数量与名单。"""
    clubnr, _, org = str(f["key"]).partition(":")
    org = org or (f.get("extra") or {}).get("org", "")
    entry = {**f, "clubnr": clubnr, "org": org, "teams": None}
    try:
        teams = (api.get_club_teams(clubnr, org).get("data") or []) if org else []
        entry["teams"] = len(teams)
        entry["team_list"] = [
            {"name": x.get("team_name"), "id": x.get("team_id"), "league": x.get("league_name")}
            for x in teams
        ]
    except Exception as e:
        entry["error"] = str(e)[:120]
    return entry


def overview(api: MyTTApi) -> Dict[str, Any]:
    """关注面板：为每个关注项附上当前数据（走本地缓存，重复打开很快）。"""
    out: Dict[str, List[Dict[str, Any]]] = {"players": [], "teams": [], "clubs": []}
    for f in list_favorites():
        if f["kind"] == "player":
            out["players"].append(_player_entry(api, f))
            time.sleep(0.05)  # 频率保护
        elif f["kind"] == "team":
            out["teams"].append(_team_entry(api, f))
        elif f["kind"] == "club":
            out["clubs"].append(_club_entry(api, f))
    return out

"""赛后复盘：交手记录（H2H）聚合 + 个人复盘笔记存储。

交手记录从球员的 TTR 历史中聚合，不依赖额外接口。
笔记存放在独立的 SQLite 文件（与请求缓存分开，清缓存不会丢笔记）。
"""
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .api import MyTTApi

NOTES_DB = Path(__file__).resolve().parent.parent / "mytt_notes.db"


# ---------- 交手记录 ----------

def _games(m: Dict[str, Any]) -> List[str]:
    """各局比分，跳过未打的 0:0 局。"""
    out = []
    for i in range(1, 8):
        a, b = m.get(f"own_set{i}") or 0, m.get(f"other_set{i}") or 0
        if a or b:
            out.append(f"{a}:{b}")
    return out


def head_to_head(api: MyTTApi, nuid: str, opponent: str) -> Dict[str, Any]:
    """聚合 nuid 与 opponent 的全部交手记录。

    返回 {player_name, opponent_name, encounters[], summary{}}；
    历史不可用时返回 {'error': ...}。
    """
    data = api.get_ttr_history(nuid)
    if not isinstance(data, dict) or "event" not in data:
        err = data.get("error") if isinstance(data, dict) else None
        return {"error": err or "无法获取 TTR 历史（可能需要登录）"}

    encounters: List[Dict[str, Any]] = []
    opponent_name = ""

    for ev in data.get("event") or []:
        for m in ev.get("match") or []:
            if str(m.get("other_person_id") or "") != opponent:
                continue
            opponent_name = m.get("other_person_name") or opponent_name
            own, other = m.get("own_sets") or 0, m.get("other_sets") or 0
            try:
                expected = float(str(m.get("expected_result", "")).replace(",", "."))
            except (TypeError, ValueError):
                expected = None
            encounters.append({
                "date": (ev.get("event_date_time") or "")[:10],
                "event": ev.get("event_name") or "",
                "own_sets": own,
                "other_sets": other,
                "win": own > other,
                "games": _games(m),
                "opponent_ttr": m.get("other_ttr"),
                "expected": expected,          # 赛前胜率预期 0~1
                "ttr_delta": ev.get("ttr_delta"),   # 注意：整场比赛（event）级别，非单场
                "own_team": m.get("own_team_name"),
                "other_team": m.get("other_team_name"),
            })

    encounters.sort(key=lambda e: e["date"], reverse=True)

    wins = sum(1 for e in encounters if e["win"])
    sets_won = sum(e["own_sets"] for e in encounters)
    sets_lost = sum(e["other_sets"] for e in encounters)
    games_won = games_lost = 0
    for e in encounters:
        for g in e["games"]:
            a, b = (int(x) for x in g.split(":"))
            games_won += a
            games_lost += b

    return {
        "player_name": data.get("person_name") or nuid,
        "player_ttr": data.get("ttr"),
        "opponent_name": opponent_name or opponent,
        "encounters": encounters,
        "summary": {
            "played": len(encounters),
            "wins": wins,
            "losses": len(encounters) - wins,
            "sets_won": sets_won,
            "sets_lost": sets_lost,
            "games_won": games_won,
            "games_lost": games_lost,
        },
    }


# ---------- 复盘笔记 ----------

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(NOTES_DB, timeout=10)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS notes (key TEXT PRIMARY KEY, text TEXT, updated REAL)"
    )
    return conn


def get_note(key: str) -> Dict[str, Any]:
    try:
        with _conn() as conn:
            row = conn.execute("SELECT text, updated FROM notes WHERE key = ?", (key,)).fetchone()
        if row:
            return {"key": key, "text": row[0], "updated": row[1]}
    except Exception:
        pass
    return {"key": key, "text": "", "updated": None}


def save_note(key: str, text: str) -> Dict[str, Any]:
    now = time.time()
    try:
        with _conn() as conn:
            if text.strip():
                conn.execute(
                    "INSERT OR REPLACE INTO notes (key, text, updated) VALUES (?, ?, ?)",
                    (key, text, now),
                )
            else:
                conn.execute("DELETE FROM notes WHERE key = ?", (key,))  # 清空即删除
        return {"ok": True, "updated": now if text.strip() else None}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def list_notes() -> List[Dict[str, Any]]:
    """全部笔记，最近更新在前。"""
    try:
        with _conn() as conn:
            rows = conn.execute(
                "SELECT key, text, updated FROM notes ORDER BY updated DESC"
            ).fetchall()
        return [{"key": k, "text": txt, "updated": u} for k, txt, u in rows]
    except Exception:
        return []

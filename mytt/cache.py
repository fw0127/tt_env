"""本地请求缓存：SQLite 存储，按接口类型设置不同 TTL。

命中缓存时不再发起网络请求。设置环境变量 MYTT_NO_CACHE=1 可整体停用；
单次请求可通过 bypass 上下文变量跳过（Web 端对应 ?refresh=1）。
"""
import contextvars
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "mytt_cache.db"

# 请求级旁路开关：True 时读写均跳过缓存中的"读"，仍会把新结果写入
bypass = contextvars.ContextVar("mytt_cache_bypass", default=False)

# (路径片段, TTL 秒)，按顺序匹配；TTL <= 0 表示该类接口不缓存
TTL_RULES = [
    ("/live", 0),               # 比赛 Live 比分：永不缓存
    ("/api/ttr/player/", 3600),         # 实时 TTR：1 小时
    ("/api/ttr/history/", 6 * 3600),    # TTR 历史：6 小时
    ("/api/search/", 30 * 86400),       # 搜索结果：30 天
]
DEFAULT_TTL = 86400  # 其余（阵容/赛程/排名/loader 等）：1 天


def enabled() -> bool:
    return os.getenv("MYTT_NO_CACHE", "") not in ("1", "true", "yes")


def ttl_for(path: str) -> int:
    for fragment, ttl in TTL_RULES:
        if fragment in path:
            return ttl
    return DEFAULT_TTL


def make_key(scope: str, method: str, path: str, params: Optional[Dict[str, Any]]) -> str:
    payload = f"{scope}|{method}|{path}|{json.dumps(params or {}, sort_keys=True, ensure_ascii=False)}"
    return hashlib.sha1(payload.encode()).hexdigest()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, path TEXT, ts REAL, data TEXT)"
    )
    return conn


def get(key: str, path: str) -> Optional[Any]:
    """命中且未过期时返回缓存数据，否则返回 None。"""
    ttl = ttl_for(path)
    if ttl <= 0 or not enabled() or bypass.get():
        return None
    try:
        with _conn() as conn:
            row = conn.execute("SELECT ts, data FROM cache WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        ts, data = row
        if time.time() - ts > ttl:
            return None
        return json.loads(data)
    except Exception:
        return None


def put(key: str, path: str, data: Any) -> None:
    if ttl_for(path) <= 0 or not enabled():
        return
    try:
        with _conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, path, ts, data) VALUES (?, ?, ?, ?)",
                (key, path, time.time(), json.dumps(data, ensure_ascii=False)),
            )
    except Exception:
        pass


def clear() -> int:
    """清空全部缓存，返回删除的条目数。"""
    try:
        with _conn() as conn:
            n = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            conn.execute("DELETE FROM cache")
        return n
    except Exception:
        return 0


def stats() -> Dict[str, Any]:
    try:
        with _conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            oldest = conn.execute("SELECT MIN(ts) FROM cache").fetchone()[0]
        size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
        return {"enabled": enabled(), "count": count, "size_bytes": size, "oldest_ts": oldest}
    except Exception:
        return {"enabled": enabled(), "count": 0, "size_bytes": 0, "oldest_ts": None}

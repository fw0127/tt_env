"""Token 自动获取与续期。

mytischtennis.de 的登录态是 Supabase 会话 Cookie（sb-10-auth-token，base64 JSON，
含 access_token / refresh_token / expires_at）。两条自动化路径：

1. refresh_via_site: 带旧 Cookie 访问站点，服务端会用 refresh_token 自动续期，
   并通过 Set-Cookie 返回新 Token（refresh_token 失效时会返回清空指令）。
2. import_from_browser: 从本机浏览器（Chrome/Safari/Firefox/Edge）读取已登录的
   Cookie 作为初始引导。Chrome 加密 Cookie 需要 macOS 钥匙串授权（系统会弹窗）。

密码登录接口带验证码，无法自动化；请先在浏览器里正常登录一次。
"""
import base64
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
SITE = "https://www.mytischtennis.de"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

TOKEN_RE = re.compile(r"sb-10-auth-token=([^;]+)")


# ---------- 解析 ----------

def parse_session(cookie: str) -> Optional[Dict[str, Any]]:
    """从 Cookie 串中解出 Supabase 会话 JSON。"""
    m = TOKEN_RE.search(cookie or "")
    if not m:
        return None
    raw = m.group(1)
    if raw.startswith("base64-"):
        raw = raw[len("base64-"):]
    try:
        raw += "=" * (-len(raw) % 4)
        return json.loads(base64.urlsafe_b64decode(raw))
    except Exception:
        return None


def session_expires_at(cookie: str) -> Optional[int]:
    sess = parse_session(cookie)
    return sess.get("expires_at") if sess else None


def _merge_token(cookie: str, new_token_value: str) -> str:
    """把新的 sb-10-auth-token 值合并进原 Cookie 串。"""
    if TOKEN_RE.search(cookie or ""):
        return TOKEN_RE.sub(f"sb-10-auth-token={new_token_value}", cookie)
    prefix = f"{cookie.rstrip('; ')}; " if cookie else ""
    return f"{prefix}sb-10-auth-token={new_token_value}"


# ---------- 途径一：站点自动续期 ----------

def refresh_via_site(cookie: str) -> Optional[str]:
    """带旧 Cookie 访问站点，捕获服务端续期后的新 Token。
    返回合并后的新 Cookie；无法续期（refresh_token 已失效等）返回 None。"""
    try:
        r = requests.get(
            SITE + "/",
            headers={"User-Agent": UA, "Cookie": cookie},
            timeout=20,
            allow_redirects=False,
        )
    except Exception:
        return None

    try:
        set_cookies = r.raw.headers.getlist("Set-Cookie")
    except Exception:
        set_cookies = r.headers.get("Set-Cookie") and [r.headers["Set-Cookie"]] or []

    for sc in set_cookies:
        m = re.match(r"sb-10-auth-token=([^;]*)", sc)
        if not m:
            continue
        value = m.group(1)
        if not value or "Max-Age=0" in sc:
            return None  # 服务端判定会话已死，清空了 Cookie
        return _merge_token(cookie, value)
    return None


# ---------- 途径二：从本机浏览器导入 ----------

def import_from_browser() -> Optional[str]:
    """从本机浏览器读取 mytischtennis.de 的登录 Cookie。
    需要用户先在浏览器里登录过；Chrome 会触发一次钥匙串授权弹窗。"""
    try:
        import browser_cookie3
    except ImportError:
        return None

    for loader in ("chrome", "safari", "firefox", "edge", "arc", "brave"):
        fn = getattr(browser_cookie3, loader, None)
        if fn is None:
            continue
        try:
            jar = fn(domain_name="mytischtennis.de")
        except Exception:
            continue
        pairs = {c.name: c.value for c in jar}
        if "sb-10-auth-token" in pairs:
            return "; ".join(f"{k}={v}" for k, v in pairs.items())
    return None


# ---------- 持久化 ----------

def save_token(cookie: str) -> None:
    """把新 Cookie 写回 .env 的 MYTT_COOKIE（保留其他行）。"""
    line = f"MYTT_COOKIE='{cookie}'"
    try:
        text = ENV_PATH.read_text() if ENV_PATH.exists() else ""
        lines = text.splitlines()
        for i, l in enumerate(lines):
            if l.startswith("MYTT_COOKIE="):
                lines[i] = line
                break
        else:
            lines.append(line)
        ENV_PATH.write_text("\n".join(lines) + "\n")
    except Exception:
        pass


# ---------- 编排 ----------

def ensure_fresh(cookie: str = "", allow_browser: bool = False, margin: int = 300) -> Tuple[Optional[str], str]:
    """确保拿到未过期的 Token。

    返回 (cookie, 状态)。状态：
      valid            现有 Token 仍有效
      refreshed        已通过站点自动续期
      browser          已从本机浏览器导入
      browser_refreshed 浏览器导入的 Token 已顺带续期
      manual_required  自动获取失败，需要先在浏览器登录
    """
    now = time.time()

    if cookie:
        exp = session_expires_at(cookie)
        if exp and exp - now > margin:
            return cookie, "valid"
        new = refresh_via_site(cookie)
        if new:
            save_token(new)
            return new, "refreshed"

    if allow_browser:
        imported = import_from_browser()
        if imported:
            exp = session_expires_at(imported)
            if exp and exp - now > margin:
                save_token(imported)
                return imported, "browser"
            new = refresh_via_site(imported)
            if new:
                save_token(new)
                return new, "browser_refreshed"

    return (cookie or None), "manual_required"

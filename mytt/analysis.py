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
        "team_id": str(team_id),
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


# 六人 Paarkreuz 的固定出场顺序（已对照真实比赛数据核实）：
# 3 场双打 → 交叉单打 1-2/2-1/3-4/4-3/5-6/6-5 → 对位单打 1-1…6-6 → 最后一场双打，先到 9 分结束。
SINGLES_ORDER = [(0, 1), (1, 0), (2, 3), (3, 2), (4, 5), (5, 4),
                 (0, 0), (1, 1), (2, 2), (3, 3), (4, 4), (5, 5)]
DOUBLES_NAMES = ["D1-D2", "D2-D1", "D3-D3"]
FINAL_DOUBLE = "D1-D1"


def win_probability(own_ttr: float, opp_ttr: float) -> float:
    """德国 TTR 的单场胜率预期（与站点的 expected_result 一致）。"""
    return 1 / (1 + 10 ** ((opp_ttr - own_ttr) / 150))


def _score_distribution(probs: List[float], target: int,
                        start: tuple = (0, 0)) -> Dict[tuple, float]:
    """按出场顺序逐场推概率，一方先到 target 分即结束。返回 {(主分, 客分): 概率}。

    start 是已经拿到的分数 —— 必须作为 DP 起点，不能算完再加：
    比赛可能已经结束（比分到 9），后面的场次根本不会打。
    """
    dist: Dict[tuple, float] = {start: 1.0}
    for p in probs:
        nxt: Dict[tuple, float] = {}
        for (h, a), w in dist.items():
            if h >= target or a >= target:       # 已经结束，比分不再变
                nxt[(h, a)] = nxt.get((h, a), 0) + w
                continue
            nxt[(h + 1, a)] = nxt.get((h + 1, a), 0) + w * p
            nxt[(h, a + 1)] = nxt.get((h, a + 1), 0) + w * (1 - p)
        dist = nxt
    return dist


def predict_meeting(api: MyTTApi, home_team_id: str, away_team_id: str) -> Dict[str, Any]:
    """按双方阵容的实时 TTR 预测一场团体赛。

    单打按 Paarkreuz 的固定对位逐场算胜率；双打无法预知配对（真实比赛里 D1 可能由
    2 号和 6 号组成），统一用两队前六名的平均 TTR 估一个胜率，四场双打共用。
    """
    home = [p for p in collect_team_analysis(api, home_team_id) if p.get("ttr")][:6]
    away = [p for p in collect_team_analysis(api, away_team_id) if p.get("ttr")][:6]
    if not home or not away:
        return {"error": "无法获取双方阵容的 TTR"}

    n = min(len(home), len(away))
    avg = lambda ps: sum(int(p["ttr"]) for p in ps) / len(ps)
    p_double = win_probability(avg(home), avg(away))

    fixtures: List[Dict[str, Any]] = []
    for name in DOUBLES_NAMES:
        fixtures.append({"name": name, "type": "double", "home": None, "away": None, "p": p_double})
    for hi, ai in SINGLES_ORDER:
        if hi >= n or ai >= n:
            continue
        h, a = home[hi], away[ai]
        fixtures.append({
            "name": f"{hi + 1}-{ai + 1}", "type": "single",
            "home": {"name": h["name"], "nuid": h["nuid"], "ttr": h["ttr"]},
            "away": {"name": a["name"], "nuid": a["nuid"], "ttr": a["ttr"]},
            "p": win_probability(int(h["ttr"]), int(a["ttr"])),
        })
    fixtures.append({"name": FINAL_DOUBLE, "type": "double", "home": None, "away": None, "p": p_double})

    target = len(fixtures) // 2 + 1            # 16 场 → 先到 9 分
    dist = _score_distribution([f["p"] for f in fixtures], target)
    home_win = sum(w for (h, a), w in dist.items() if h > a)
    draw = sum(w for (h, a), w in dist.items() if h == a)
    top = sorted(dist.items(), key=lambda kv: -kv[1])[:5]

    return {
        "home_team_id": str(home_team_id), "away_team_id": str(away_team_id),
        "home_players": home[:n], "away_players": away[:n],
        "home_avg": round(avg(home[:n])), "away_avg": round(avg(away[:n])),
        "fixtures": fixtures,
        "target": target,
        "probabilities": {"home": home_win, "draw": draw, "away": 1 - home_win - draw},
        "expected": {
            "home": sum(h * w for (h, a), w in dist.items()),
            "away": sum(a * w for (h, a), w in dist.items()),
        },
        "likely_scores": [{"home": h, "away": a, "p": w} for (h, a), w in top],
        "roster_size": n,
        "doubles_note": True,
    }


# 16 场的完整顺序（名称与站点一致）
FIXTURE_ORDER = (DOUBLES_NAMES
                 + [f"{h + 1}-{a + 1}" for h, a in SINGLES_ORDER]
                 + [FINAL_DOUBLE])


def _bo5(g: float, h: int = 0, a: int = 0) -> float:
    """单局胜率 g 时，从 h:a 开始先赢 3 局的概率（五局三胜）。"""
    if h >= 3:
        return 1.0
    if a >= 3:
        return 0.0
    return g * _bo5(g, h + 1, a) + (1 - g) * _bo5(g, h, a + 1)


def _game_prob(match_p: float) -> float:
    """由单场胜率反推单局胜率（二分）。用于把已打的局分折进概率。"""
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if _bo5(mid) < match_p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def predict_live(api: MyTTApi, meeting_id: str) -> Dict[str, Any]:
    """进行中的团体赛：按已出结果 + 当前局分，推算剩余场次与最终比分。

    比赛开始后出场名单和双打配对都能从 Live 数据里读到，比赛前的估算要准；
    还没登场的位置（常见是 5、6 号）回退到队内排名。
    """
    d = (api.get_meeting_live(str(meeting_id)) or {}).get("data") or {}
    if not d:
        return {"error": "无法获取该场比赛"}
    rows = {m.get("match_name"): m for m in (d.get("match") or [])}

    ttr_cache: Dict[str, Optional[int]] = {}

    def ttr_of(nuid: Optional[str]) -> Optional[int]:
        if not nuid:
            return None
        if nuid not in ttr_cache:
            v = api.get_ttr_player(nuid).get("ttr")
            ttr_cache[nuid] = int(v) if str(v or "").lstrip("-").isdigit() else None
        return ttr_cache[nuid]

    def person(row: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
        p = row.get(key) or {}
        if not p.get("person_id"):
            return None
        return {"name": f"{p.get('lastname', '')}, {p.get('firstname', '')}".strip(", "),
                "nuid": p.get("person_id")}

    # 从已登场的场次还原双方的出场位置与双打配对
    singles_home: Dict[int, Dict[str, Any]] = {}
    singles_away: Dict[int, Dict[str, Any]] = {}
    doubles_home: Dict[str, List[Dict[str, Any]]] = {}
    doubles_away: Dict[str, List[Dict[str, Any]]] = {}
    for name, row in rows.items():
        if row.get("game_type") == "double":
            h_no, a_no = name.replace("D", "").split("-")
            pair_h = [x for x in (person(row, "mm_player11"), person(row, "mm_player12")) if x]
            pair_a = [x for x in (person(row, "mm_player21"), person(row, "mm_player22")) if x]
            if pair_h:
                doubles_home.setdefault(h_no, pair_h)
            if pair_a:
                doubles_away.setdefault(a_no, pair_a)
        else:
            h_no, a_no = name.split("-")
            if (ph := person(row, "mm_player11")):
                singles_home.setdefault(int(h_no), ph)
            if (pa := person(row, "mm_player21")):
                singles_away.setdefault(int(a_no), pa)

    # 还没登场的位置用队内排名补齐
    def fill_lineup(team_id: Optional[str], known: Dict[int, Dict[str, Any]],
                    present: List[Dict[str, Any]]) -> None:
        """补上还没登场的单打位置，标记 assumed 让界面注明。

        六人 Paarkreuz 的三场双打正好用满六名队员 —— 没打双打的人不会再打单打。
        所以空位只能从双打登场的这六人里取（他们未必在队内名单上，可能是从别的
        队借调的）。三场双打还没全部录入时，才回退到队内排名。
        """
        missing = [i for i in range(1, 7) if i not in known]
        if not missing:
            return
        used = {p.get("nuid") for p in known.values()}
        pool = [p for p in present if p.get("nuid") not in used]
        pool.sort(key=lambda p: -(ttr_of(p.get("nuid")) or 0))   # 强的排前面当 5 号
        certain = {p["nuid"] for p in pool}       # 来自双打的六人，人选是确定的

        if len(pool) < len(missing) and team_id:
            seen = used | certain
            roster = [p for p in collect_team_analysis(api, str(team_id))
                      if p.get("ttr") and p["nuid"] not in seen]
            rank_of = lambda p: int(p["rank"]) if str(p.get("rank", "")).isdigit() else 99
            for p in sorted(roster, key=rank_of, reverse=True):   # 由弱到强补
                pool.append({"name": p["name"], "nuid": p["nuid"]})
                if p["nuid"] not in ttr_cache:
                    ttr_cache[p["nuid"]] = int(p["ttr"])

        for i, p in zip(missing, pool):
            # 只剩一个空位、且人选来自双打六人时就不是猜的了，唯一解
            sure = len(missing) == 1 and p["nuid"] in certain
            known[i] = {"name": p["name"], "nuid": p["nuid"],
                        **({} if sure else {"assumed": True})}

    present_home = [p for pair in doubles_home.values() for p in pair]
    present_away = [p for pair in doubles_away.values() for p in pair]
    fill_lineup(d.get("team_home_id"), singles_home, present_home)
    fill_lineup(d.get("team_guest_id"), singles_away, present_away)

    def side_ttr(players: List[Dict[str, Any]]) -> Optional[float]:
        vals = [v for v in (ttr_of(p.get("nuid")) for p in players) if v]
        return sum(vals) / len(vals) if vals else None

    def doubles_side(pairs: Dict[str, List[Dict[str, Any]]], no: str, singles: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
        # 没登场过的双打：用该号次对应的两名队员近似（D1→1、2 号，D2→3、4 号，D3→5、6 号）
        if no in pairs:
            return pairs[no]
        base = (int(no) - 1) * 2 + 1
        return [p for p in (singles.get(base), singles.get(base + 1)) if p]

    decided_home = decided_away = 0
    fixtures: List[Dict[str, Any]] = []
    for name in FIXTURE_ORDER:
        row = rows.get(name)
        hs, gs = (row.get("sets_home") or 0, row.get("sets_guest") or 0) if row else (0, 0)
        done = bool(row) and (max(hs, gs) >= 3 or row.get("home_wo") or row.get("guest_wo"))
        is_double = name.startswith("D")
        if is_double:
            h_no, a_no = name.replace("D", "").split("-")
            home_players = doubles_side(doubles_home, h_no, singles_home)
            away_players = doubles_side(doubles_away, a_no, singles_away)
        else:
            h_no, a_no = name.split("-")
            home_players = [x for x in [singles_home.get(int(h_no))] if x]
            away_players = [x for x in [singles_away.get(int(a_no))] if x]

        entry: Dict[str, Any] = {
            "name": name, "type": "double" if is_double else "single",
            "home": [{**p, "ttr": ttr_of(p["nuid"])} for p in home_players],
            "away": [{**p, "ttr": ttr_of(p["nuid"])} for p in away_players],
            "sets": [hs, gs],
        }
        if done:
            decided_home += hs > gs
            decided_away += gs > hs
            entry["status"] = "done"
            entry["p"] = 1.0 if hs > gs else 0.0
        else:
            h_ttr, a_ttr = side_ttr(home_players), side_ttr(away_players)
            p = win_probability(h_ttr, a_ttr) if (h_ttr and a_ttr) else 0.5
            if hs or gs:                       # 正在打：把已打的局分折进去
                entry["status"] = "running"
                p = _bo5(_game_prob(p), hs, gs)
            else:
                entry["status"] = "pending"
            entry["p"] = p
        fixtures.append(entry)

    target = len(fixtures) // 2 + 1
    remaining = [f["p"] for f in fixtures if f["status"] != "done"]
    dist = _score_distribution(remaining, target, (decided_home, decided_away))

    home_win = sum(w for (h, a), w in dist.items() if h > a)
    draw = sum(w for (h, a), w in dist.items() if h == a)
    return {
        "meeting_id": str(meeting_id),
        "home_team": d.get("team_home"), "away_team": d.get("team_guest"),
        "home_team_id": d.get("team_home_id"), "away_team_id": d.get("team_guest_id"),
        "current": {"home": decided_home, "away": decided_away},
        "completed": bool(d.get("is_completed")),
        "fixtures": fixtures,
        "target": target,
        "probabilities": {"home": home_win, "draw": draw, "away": 1 - home_win - draw},
        "expected": {"home": sum(h * w for (h, a), w in dist.items()),
                     "away": sum(a * w for (h, a), w in dist.items())},
        "likely_scores": [{"home": h, "away": a, "p": w}
                          for (h, a), w in sorted(dist.items(), key=lambda kv: -kv[1])[:5]],
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

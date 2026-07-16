"""各功能的终端渲染视图：搜索、TTR、阵容、赛程、排名、Live。"""
from typing import Any

from rich import box
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .api import MyTTApi, clean_roster
from .ui import console, format_ttr, show_json


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
        for item in items[:20]:  # 最多展示 20 条，避免请求过多
            name = f"{item.get('lastname', '')} {item.get('firstname', '')}".strip()
            club = item.get("club_name", "-") or "-"

            # 优先 internal_id，退回 person_id 查询 TTR
            player_id_for_ttr = item.get("internal_id") or item.get("person_id")
            ttr_val = None
            if player_id_for_ttr:
                ttr_resp = api.get_ttr_player(str(player_id_for_ttr))
                ttr_val = ttr_resp.get("ttr")

            ttr_text, ttr_style = format_ttr(ttr_val or "需登录可见")

            table.add_row(
                name[:20],
                club[:25],
                f"[{ttr_style}]{ttr_text}[/{ttr_style}]",
                str(player_id_for_ttr or "-"),
                str(item.get("dttb_player_id", "-"))[:10],
            )

    console.print(table)
    _player_detail_loop(api, items)


def _player_detail_loop(api: MyTTApi, items: list[dict[str, Any]]) -> None:
    """搜索结果后的交互：选择球员并查看详情。"""
    while True:
        selected_input = Prompt.ask("[bold blue]请输入要查看详情的球员 NUID/ID (或输入 'b' 返回):[/bold blue]").strip().lower()
        if selected_input == "b":
            return

        selected_player = None
        for item in items:
            player_id_check = str(item.get("internal_id") or item.get("person_id") or "-")
            if player_id_check.upper().strip() == selected_input.upper().strip():
                selected_player = item
                break

        if not selected_player:
            console.print("[red]无效的 NUID/ID，请重新输入。[/red]")
            continue

        _player_detail_menu(api, selected_player)


def _player_detail_menu(api: MyTTApi, player: dict[str, Any]) -> None:
    while True:
        console.print(Panel(
            f"[bold white]已选择球员: {player.get('lastname', '')} {player.get('firstname', '')}[/bold white]",
            title="球员详情操作", border_style="green",
        ))
        sub_choice = Prompt.ask("[bold blue]请选择操作: 1.显示TTR历史 2.显示俱乐部队伍信息 (b返回):[/bold blue]").strip().lower()

        if sub_choice == "b":
            return

        if sub_choice == "1":
            nuid = str(player.get("internal_id") or "")
            clicktt_id = str(player.get("person_id") or "")
            if not nuid:
                console.print("[red]错误: 找不到该球员的 NUID (internal_id)，无法获取历史记录。[/red]")
                continue
            render_ttr_history(api, nuid, clicktt_id=clicktt_id)
        elif sub_choice == "2":
            club_name = player.get("club_name")
            if not club_name or club_name == "-":
                console.print("[yellow]该球员没有俱乐部信息，无法查询队伍。[/yellow]")
                continue
            club_items = api.search_clubs(club_name).get("results", [])
            if not club_items:
                console.print(f"[yellow]未找到俱乐部 '{club_name}' 的详细信息。[/yellow]")
                continue
            target_club = club_items[0]
            club_number = str(target_club.get("clubnr"))
            organization = target_club.get("organization_short")
            if club_number and organization:
                render_club_teams(api, club_number, organization)
            else:
                console.print(f"[yellow]未找到俱乐部 '{club_name}' 的完整信息 (clubnr/organization_short)。[/yellow]")
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
        table.add_row(
            item.get("clubname", "-")[:30],
            str(item.get("clubnr", "-")),
            item.get("organization_short", "-"),
            str(item.get("external_id", "-")),
        )

    console.print(table)


def render_ttr_player(api: MyTTApi, nuid: str) -> None:
    data = api.get_ttr_player(nuid)
    ttr_text, ttr_style = format_ttr(data.get("ttr"))

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
    roster = clean_roster(data.get("data", []) or [])

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
        table.add_row(
            t.get("team_name", "-")[:25],
            t.get("league_name", "-")[:30],
            str(t.get("team_id", "-")),
            str(t.get("group_id", "-")),
        )

    console.print(table)


def render_league_table_api(api: MyTTApi, association: str, league_id: str) -> None:
    data = api.get_league_table_api(association, league_id)
    # 返回结构可能是列表，也可能嵌在 data['table'] 里
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
        wld = f"{entry.get('matches_won', '0')}-{entry.get('matches_draw', '0')}-{entry.get('matches_lost', '0')}"
        sets = f"{entry.get('games_won', '0')}:{entry.get('games_lost', '0')}"
        points = str(entry.get("points", "-"))
        table.add_row(rank, name[:25], matches, wld, sets, points)

    console.print(table)


def render_meeting_live(api: MyTTApi, meeting_id: str) -> None:
    data = api.get_meeting_live(meeting_id)
    # Live 接口返回当前比分、正在进行的场次等
    live_data = data.get("data", {})
    home = live_data.get("team_home", "Home")
    away = live_data.get("team_away", "Away")
    score = f"{live_data.get('matches_won_home', 0)} : {live_data.get('matches_won_away', 0)}"

    console.print(Panel(
        f"[bold white]{home}[/bold white]  [yellow]{score}[/yellow]  [bold white]{away}[/bold white]",
        title="Live Score", border_style="green",
    ))

    matches = live_data.get("matches", [])
    if not matches:
        console.print("[yellow]暂无详细场次数据。[/yellow]")
        return

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

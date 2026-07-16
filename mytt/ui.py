"""通用终端 UI 工具：控制台实例、TTR 着色、JSON 展示、参数输入。"""
import re
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

console = Console()


def format_ttr(value: Any) -> tuple[str, str]:
    """把 TTR 值格式化为 (文本, rich 样式)。"""
    if value is None:
        return ("N/A", "red")
    s = str(value).strip()
    if s == "" or s.lower() in {"none", "null", "n/a"}:
        return ("N/A", "red")
    if any(k in s for k in ["需登录", "不可见", "ERR", "Not authorized"]):
        return (s, "yellow")
    if re.fullmatch(r"-?\d+", s):
        return (s, "green")
    return (s, "white")


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

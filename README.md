# 🏓 MyTT 助手

[mytischtennis.de](https://www.mytischtennis.de) 的数据查询与赛前分析工具，提供**终端 CLI** 和 **Web 界面**两种用法：
搜球员、查 TTR 历史、分析球队阵容、赛前「作战室」对手分析、赛后复盘，以及关注列表。

## 功能

| 功能 | 说明 |
| --- | --- |
| 🔍 搜索 | 按姓名搜球员、按名称搜俱乐部 |
| 👤 球员 | 实时 TTR、完整 TTR 历史、生涯最高分与 TTR 曲线 |
| 📋 球队 | 阵容、每人实时 TTR 与近期状态、赛程、俱乐部下所有球队、联赛排名 |
| ⚔️ 作战室 | 自动找到下一场对手并做深度分析 |
| 📝 复盘 | 交手记录（H2H，从 TTR 历史聚合）+ 个人复盘笔记 |
| ⭐ 关注 | 关注球员 / 球队 / 俱乐部，汇总成关注面板 |
| 🏆 更多 | 比赛 Live 比分（悬停显示各局局分）等 |

Web 界面支持中文 / 德语 / 英语。

## 安装

需要 Python 3.10+。

```bash
python3 -m venv venv
source venv/bin/activate
pip install requests rich python-dotenv fastapi uvicorn browser-cookie3
```

`browser-cookie3` 只用于「从浏览器一键导入 Token」，不需要可以不装。

## 登录态（Token）

大部分接口需要 mytischtennis.de 的登录 Cookie。在项目根目录建 `.env`：

```ini
MYTT_COOKIE="sb-10-auth-token=base64-..."
```

获取方式（任选其一）：

- **一键导入**：先在本机浏览器（Chrome / Safari / Firefox / Edge）正常登录 mytischtennis.de，然后在 Web 界面的 Token 设置里点「🪄 自动获取」。Chrome 会弹出 macOS 钥匙串授权。
- **手动复制**：浏览器开发者工具里复制 `sb-10-auth-token` Cookie，粘贴到 Web 界面或 `.env`。

Token 快过期时会自动通过站点续期并写回 `.env`。只有 refresh token 也失效时，才需要重新在浏览器登录一次（登录接口带验证码，无法自动化）。

> ⚠️ `.env` 包含你的登录态，已在 `.gitignore` 中，切勿提交或分享。

## 使用

### Web 界面

```bash
python web.py
```

打开 <http://127.0.0.1:8000>。API 文档在 `/docs`。

```bash
python web.py 8080          # 换端口
python web.py --lan         # 局域网可访问（监听 0.0.0.0）
python web.py --host 0.0.0.0
```

端口优先级：命令行参数 > `PORT` > `MYTT_PORT` > 8000。

**对外监听时务必设置访问口令**，否则同网段的人都能直接使用你的登录态：

```ini
MYTT_WEB_PASSWORD=你的口令
```

开启后浏览器会弹出 HTTP Basic 认证框，用户名随意填。HTTP 为明文传输，只适合局域网或隧道内使用。

### 终端 CLI

```bash
python main.py
```

交互式菜单，包含常用功能（1–10、`w` 作战室），`a` 进入全量 GET 接口浏览器，可直接调用 `MyTTApi` 的所有方法并查看原始 JSON。

### 作战室独立入口

```bash
python war_room.py <my_team_id>
```

## 配置项（`.env`）

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `MYTT_COOKIE` | mytischtennis.de 登录 Cookie | — |
| `MYTT_HOST` | Web 监听地址 | `127.0.0.1` |
| `MYTT_PORT` | Web 端口 | `8000` |
| `MYTT_WEB_PASSWORD` | Web 访问口令，留空则不启用 | 空 |
| `MYTT_NO_CACHE` | 设为 `1` 关闭本地缓存 | 空 |

## 本地数据

| 文件 | 内容 |
| --- | --- |
| `mytt_cache.db` | 请求缓存。Live 比分不缓存，实时 TTR 1 小时，TTR 历史 6 小时，搜索 30 天，其余 1 天。Web 端任意接口加 `?refresh=1` 可跳过缓存，也可在界面里清空 |
| `mytt_notes.db` | 复盘笔记与关注列表。与缓存分开存放，清缓存不会丢失 |

两者都已 gitignore。

## 项目结构

```
main.py            CLI 入口
web.py             Web 入口（uvicorn 启动参数）
war_room.py        作战室独立入口
mytt/
  api.py           MyTTApi：mytischtennis.de 接口封装、阵容清洗
  auth.py          Token 解析、站点续期、浏览器导入
  cache.py         SQLite 请求缓存
  analysis.py      球队分析、作战室
  review.py        H2H 聚合、复盘笔记
  favorites.py     关注列表与关注面板
  render.py        CLI 表格渲染
  ui.py            终端 UI 工具（rich）
  cli.py           CLI 菜单与主循环
  web.py           FastAPI 应用与 REST 接口
  static/index.html  Web 前端（单文件）
```

## 说明

本项目为个人使用的非官方工具，与 mytischtennis.de 无关。请合理控制请求频率。

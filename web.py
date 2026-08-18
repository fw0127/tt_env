"""MyTT Web 界面入口。

用法:
  python web.py                  仅本机可访问（默认 127.0.0.1:8000）
  python web.py 8080             换端口
  python web.py --lan            监听 0.0.0.0，同一局域网的设备用 IP 就能访问
  python web.py --host 0.0.0.0   同上，显式指定网卡

也可以写进 .env：MYTT_HOST=0.0.0.0 / MYTT_PORT=8000
（环境变量 PORT 若存在则优先于 MYTT_PORT，方便外部工具分配空闲端口）

⚠️ 本服务没有内建登录：一旦对外监听，能连到这个端口的人就能用你的
mytischtennis.de 登录态。设置 MYTT_WEB_PASSWORD 可开启一道 HTTP Basic
口令（见 mytt/web.py）。
"""
import argparse
import os
import socket
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(dotenv_path=ROOT / ".env", override=True)


def lan_ip() -> str:
    """本机在局域网里的地址。UDP connect 不会真的发包，只是让内核挑一张网卡。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="MyTT Web 界面")
    # 端口优先级：命令行参数 > PORT（由外部工具分配，如编辑器内置预览）> .env 的 MYTT_PORT > 8000
    default_port = int(os.environ.get("PORT") or os.getenv("MYTT_PORT") or 8000)
    p.add_argument("port", nargs="?", type=int, default=default_port)
    p.add_argument("--host", default=os.getenv("MYTT_HOST", "127.0.0.1"),
                   help="监听地址，默认 127.0.0.1（仅本机）")
    p.add_argument("--lan", action="store_true", help="等同 --host 0.0.0.0（局域网可访问）")
    args = p.parse_args()

    host = "0.0.0.0" if args.lan else args.host
    exposed = host not in ("127.0.0.1", "localhost", "::1")

    print(f"  本机  : http://127.0.0.1:{args.port}")
    if exposed:
        print(f"  局域网: http://{lan_ip()}:{args.port}")
        if not os.getenv("MYTT_WEB_PASSWORD"):
            print("  ⚠️  未设置 MYTT_WEB_PASSWORD：同网段的任何人都能直接使用你的登录态")
        else:
            print("  🔒 已启用访问口令（HTTP Basic，用户名随意）")

    uvicorn.run("mytt.web:app", host=host, port=args.port)

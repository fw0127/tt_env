"""MyTT Web 界面入口。

用法: python web.py [port]   （默认 8000，仅监听本机）
"""
import sys

import uvicorn

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run("mytt.web:app", host="127.0.0.1", port=port)

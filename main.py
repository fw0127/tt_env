"""MyTT CLI 入口。实际逻辑在 mytt 包中：

- mytt/api.py       API 封装 (MyTTApi) 与阵容清洗
- mytt/ui.py        终端 UI 工具（console、TTR 着色、JSON 展示）
- mytt/render.py    各功能的表格渲染视图
- mytt/analysis.py  球队分析、作战室
- mytt/cli.py       菜单定义与主循环
"""
from mytt.cli import main

if __name__ == "__main__":
    main()

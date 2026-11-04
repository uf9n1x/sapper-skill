#!/usr/bin/env python3
"""prism 控制面唯一 CLI 入口（P1 骨架：schema / pack / verify-pack）。

运行方式：python -X utf8 scripts/prism.py <command> ...
不实现 Agent 自动循环；宿主主 Agent 按协议调用。
"""

from __future__ import annotations

from prism.cli import app

if __name__ == "__main__":
    app()

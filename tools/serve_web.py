"""
以 Web 模式启动 ok-gf2（无 Qt 窗口），同时开放 HTTP API 供 tools/okctl.py 远程控制。

    .venv\\Scripts\\python.exe tools\\serve_web.py            # 默认 127.0.0.1:8765
    .venv\\Scripts\\python.exe tools\\serve_web.py --port 8800

浏览器打开 http://127.0.0.1:8765 能看到和桌面版一样的界面。
Web 模式和桌面版（main.py）不能同时运行。
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    os.chdir(ROOT)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from ok import run_web

    from src.config import config

    run_web(config, host=args.host, port=args.port, open_browser=False)


if __name__ == "__main__":
    main()

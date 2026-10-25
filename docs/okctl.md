# okctl：命令行控制 ok-gf2

ok-script 自带 Web 模式（FastAPI + 浏览器界面），`tools/serve_web.py` 用它代替 Qt 桌面窗口启动，`tools/okctl.py` 通过它的 HTTP API 控制程序。两者只用标准库 + 项目已有依赖（需 `pip install fastapi uvicorn`）。

## 启动服务

```
cd <ok-gf2 仓库目录>
.venv\Scripts\python.exe tools\serve_web.py          # 监听 127.0.0.1:8765
```

浏览器打开 http://127.0.0.1:8765 就是原来的操作界面。Web 模式与桌面版 `main.py` 不能同时运行。
游戏抓图需要交互式桌面会话，远程（ssh）启动时要用计划任务以当前登录用户运行。

## 常用命令

```
python tools\okctl.py status                        # 执行器状态
python tools\okctl.py tasks -v                      # 任务列表及配置
python tools\okctl.py start 推图                    # 启动任务
python tools\okctl.py stop                          # 停止当前任务
python tools\okctl.py config 推图                   # 看配置
python tools\okctl.py config 推图 推完继续下一章 false # 改配置（JSON 值）
python tools\okctl.py logs --tail 50 --query 助战   # 过滤日志
python tools\okctl.py shot now.png                  # 抓一帧
python tools\okctl.py run 推图 --timeout 900        # 启动并等待结束，打印最近日志
```

`--url` 或环境变量 `OKCTL_URL` 可指向其他地址。

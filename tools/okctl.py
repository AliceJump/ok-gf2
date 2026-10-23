"""
ok-gf2 命令行控制台：通过 Web 模式的 HTTP API 启停任务、改配置、看日志、截图。
只依赖标准库，Windows 本机或经 ssh 远程都能用。

    python tools/okctl.py status                      # 执行器状态、当前任务
    python tools/okctl.py tasks                       # 列出任务和配置
    python tools/okctl.py start 推图                  # 启动任务（任务名或类名，支持模糊匹配）
    python tools/okctl.py stop                        # 停止当前任务
    python tools/okctl.py config 推图 借好友助战 true   # 改任务配置（值按 JSON 解析，解析不了当字符串）
    python tools/okctl.py logs --tail 50 --query 助战 # 看日志
    python tools/okctl.py shot out.png                # 让程序抓一帧并保存
    python tools/okctl.py wait --timeout 600          # 等当前任务结束
    python tools/okctl.py run 推图 --timeout 900      # start + wait + 最近日志

服务端先用 tools/serve_web.py 启动；地址可用 --url 或环境变量 OKCTL_URL 指定，默认 http://127.0.0.1:8765
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_URL = os.environ.get("OKCTL_URL", "http://127.0.0.1:8765")


class Client:
    def __init__(self, base):
        self.base = base.rstrip("/")

    def _call(self, method, path, body=None, raw=False, timeout=30):
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = resp.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            raise SystemExit(f"HTTP {e.code} {path}: {detail}") from None
        except urllib.error.URLError as e:
            raise SystemExit(f"连不上 {self.base}：{e.reason}。先用 tools/serve_web.py 启动 Web 模式") from None
        if raw:
            return payload
        return json.loads(payload.decode("utf-8")) if payload else None

    def get(self, path, **kw):
        return self._call("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self._call("POST", path, body, **kw)


def quote(name):
    return urllib.parse.quote(name, safe="")


def parse_value(text):
    try:
        return json.loads(text)
    except ValueError:
        return text


def print_json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def task_brief(t):
    flags = []
    if t.get("running"):
        flags.append("running")
    if t.get("paused"):
        flags.append("paused")
    if t.get("trigger"):
        flags.append("trigger")
    return f"{t['name']} ({t['class_name']}) {' '.join(flags)}".rstrip()


def cmd_status(c, a):
    print_json(c.get("/api/status"))


def cmd_tasks(c, a):
    for t in c.get("/api/tasks"):
        print(task_brief(t))
        if a.verbose:
            for f in t.get("config") or []:
                if isinstance(f, dict):
                    print(f"    {f.get('key', f.get('name'))} = {f.get('value')!r}")
                else:
                    print(f"    {f!r}")


def cmd_start(c, a):
    t = c.post(f"/api/tasks/{quote(a.task)}/start")
    print("started:", task_brief(t))


def cmd_stop(c, a):
    print_json(c.post("/api/executor/stop-task"))


def cmd_pause(c, a):
    print_json(c.post("/api/executor/pause"))


def cmd_resume(c, a):
    print_json(c.post("/api/executor/resume"))


def cmd_config(c, a):
    if a.value is None:
        for t in c.get("/api/tasks"):
            if a.task.lower() in (t["name"].lower(), t["class_name"].lower()):
                print_json(t.get("config"))
                return
        raise SystemExit(f"没有叫 {a.task} 的任务")
    t = c.post(f"/api/tasks/{quote(a.task)}/config", {"key": a.key, "value": parse_value(a.value)})
    print("ok:", task_brief(t))
    for f in t.get("config") or []:
        if isinstance(f, dict) and f.get("key", f.get("name")) == a.key:
            print(f"    {a.key} = {f.get('value')!r}")


def _log_lines(payload):
    if isinstance(payload, dict):
        for key in ("lines", "logs", "items", "entries"):
            if key in payload:
                payload = payload[key]
                break
    if isinstance(payload, str):
        return payload.splitlines()
    out = []
    for item in payload or []:
        if isinstance(item, dict):
            out.append(
                " ".join(str(item.get(k)) for k in ("time", "level", "message") if item.get(k) is not None)
                or json.dumps(item, ensure_ascii=False)
            )
        else:
            out.append(str(item))
    return out


def cmd_logs(c, a):
    q = urllib.parse.urlencode({"level": a.level, "query": a.query})
    lines = _log_lines(c.get(f"/api/logs?{q}"))
    for line in lines[-a.tail :]:
        print(line)


def cmd_shot(c, a):
    r = c.post("/api/tools/capture")
    img = c.get("/api/capture/image", raw=True)
    with open(a.out, "wb") as f:
        f.write(img)
    print(f"saved {a.out} ({len(img)} bytes): {r.get('message') if isinstance(r, dict) else r}")


def wait_idle(c, timeout, interval=3):
    start = time.time()
    last = None
    while time.time() - start < timeout:
        st = c.get("/api/status")
        cur = st.get("current_task")
        if cur != last:
            print(f"[{int(time.time() - start)}s] current_task={cur}")
            last = cur
        if not cur and not st.get("starting"):
            return True
        time.sleep(interval)
    print("timeout")
    return False


def cmd_wait(c, a):
    sys.exit(0 if wait_idle(c, a.timeout) else 1)


def cmd_run(c, a):
    t = c.post(f"/api/tasks/{quote(a.task)}/start")
    print("started:", task_brief(t))
    time.sleep(2)
    ok = wait_idle(c, a.timeout)
    lines = _log_lines(c.get("/api/logs?level=ALL&query="))
    print("---- 最近日志 ----")
    for line in lines[-a.tail :]:
        print(line)
    sys.exit(0 if ok else 1)


def build_parser():
    p = argparse.ArgumentParser(prog="okctl", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default=DEFAULT_URL)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(func=cmd_status)
    s = sub.add_parser("tasks")
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(func=cmd_tasks)
    s = sub.add_parser("start")
    s.add_argument("task")
    s.set_defaults(func=cmd_start)
    sub.add_parser("stop").set_defaults(func=cmd_stop)
    sub.add_parser("pause").set_defaults(func=cmd_pause)
    sub.add_parser("resume").set_defaults(func=cmd_resume)
    s = sub.add_parser("config")
    s.add_argument("task")
    s.add_argument("key", nargs="?")
    s.add_argument("value", nargs="?")
    s.set_defaults(func=cmd_config)
    s = sub.add_parser("logs")
    s.add_argument("--level", default="ALL")
    s.add_argument("--query", default="")
    s.add_argument("--tail", type=int, default=80)
    s.set_defaults(func=cmd_logs)
    s = sub.add_parser("shot")
    s.add_argument("out", nargs="?", default="okctl_shot.png")
    s.set_defaults(func=cmd_shot)
    s = sub.add_parser("wait")
    s.add_argument("--timeout", type=int, default=1800)
    s.set_defaults(func=cmd_wait)
    s = sub.add_parser("run")
    s.add_argument("task")
    s.add_argument("--timeout", type=int, default=1800)
    s.add_argument("--tail", type=int, default=60)
    s.set_defaults(func=cmd_run)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    a.func(Client(a.url), a)


if __name__ == "__main__":
    main()

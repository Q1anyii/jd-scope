"""桌面入口：启动本地服务，然后用原生 WebView2 窗口打开。

启动优先级：
1. pywebview（WebView2 原生窗口，无地址栏，最像客户端）
2. Edge / Chrome 的 --app 模式（无地址栏独立窗口）
3. 系统默认浏览器

打包成 exe 后双击即用，不弹命令行窗口。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

from .config import APP_NAME, APP_VERSION, ensure_dirs
from .api import make_server


def _pick_port() -> int:
    for port in (8765, 8766, 8767, 0):
        try:
            httpd = make_server(port)
            actual = httpd.server_address[1]
            httpd.server_close()
            return actual
        except OSError:
            continue
    return 0


def _find_browser() -> str | None:
    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def _bind_server(port: int):
    """优先用指定端口；被占用则退回系统分配的临时端口，避免静默启动失败。"""
    try:
        return make_server(port)
    except OSError:
        return make_server(0)


def _say(obj: dict) -> None:
    """窗口模式下 sys.stdout 可能为 None，写不出去就静默跳过。"""
    if sys.stdout is None:
        return
    try:
        print(json.dumps(obj, ensure_ascii=False))
    except Exception:
        pass


class _Bridge:
    """暴露给前端的原生能力。只有 pywebview 窗口里才有，浏览器回退模式会缺失。"""

    def choose_folder(self, current: str = "") -> str:
        try:
            import webview  # type: ignore
            from webview import FileDialog  # type: ignore
        except Exception:
            return ""
        try:
            window = webview.windows[0] if webview.windows else None
            if window is None:
                return ""
            result = window.create_file_dialog(
                FileDialog.FOLDER, directory=current or "", allow_multiple=False
            )
            if not result:
                return ""
            return result[0] if isinstance(result, (list, tuple)) else str(result)
        except Exception:
            return ""


def _run_webview(url: str) -> bool:
    try:
        import webview  # type: ignore
    except Exception:
        return False
    try:
        webview.create_window(
            f"{APP_NAME} · 岗位 JD 透视",
            url,
            width=1360,
            height=900,
            min_size=(1080, 720),
            text_select=True,
            js_api=_Bridge(),
        )
        webview.start()
        return True
    except Exception:
        return False


def _run_browser_app(url: str) -> bool:
    exe = _find_browser()
    if not exe:
        return False
    profile = Path(tempfile.gettempdir()) / "jdscope-window"
    profile.mkdir(parents=True, exist_ok=True)
    args = [
        exe,
        f"--app={url}",
        f"--user-data-dir={profile}",
        "--window-size=1360,900",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate",
    ]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc.wait()
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_NAME, description="岗位 JD 透视 · 本地客户端")
    parser.add_argument("--serve-only", action="store_true", help="只启动 HTTP 服务（自测用）")
    parser.add_argument("--port", type=int, default=0, help="指定端口，0 表示自动")
    parser.add_argument("--no-window", action="store_true", help="不打开窗口，仅启动服务并打印地址")
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass

    ensure_dirs()
    httpd = _bind_server(args.port)
    port = httpd.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    if args.serve_only or args.no_window:
        _say({"ok": True, "app": APP_NAME, "version": APP_VERSION, "port": port, "url": url})
        try:
            while True:
                time.sleep(0.6)
        except KeyboardInterrupt:
            httpd.shutdown()
            return 0

    opened = _run_webview(url)
    if not opened:
        opened = _run_browser_app(url)
    if not opened:
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    httpd.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

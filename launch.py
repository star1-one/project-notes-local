#!/usr/bin/env python3
"""Double-click launcher; reopens an existing instance, otherwise serves locally."""
import json
import os
from pathlib import Path
import socket
import threading
import urllib.request
import webbrowser

from server import Application, make_server


def existing(port):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/api/bootstrap", timeout=1) as response:
            return response.headers.get("Server", "").startswith("ProjectDesk/") and json.load(response).get("version") == "1.0.0"
    except Exception:
        return False


def main():
    os.umask(0o077)
    root = Path(__file__).resolve().parent
    os.chdir(root)
    port = None
    for candidate in range(8766, 8787):
        if existing(candidate):
            webbrowser.open(f"http://127.0.0.1:{candidate}")
            print("이미 실행 중인 과제 도우미를 열었습니다.")
            return
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", candidate))
                port = candidate
                break
            except OSError:
                continue
    if port is None:
        raise SystemExit("사용 가능한 로컬 포트를 찾지 못했습니다.")
    app = Application(root / "data")
    server = make_server(app, port)
    address = f"http://127.0.0.1:{port}"
    print(f"\n과제 도우미  ·  {address}\n자료 저장: {app.store.directory}\n", flush=True)
    print("이 창을 열어둔 채 앱을 사용하세요. 종료하려면 Control+C를 누르세요.\n", flush=True)
    threading.Timer(.6, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료했습니다. 자료와 대화는 다음 실행 때 그대로 이어집니다.")
    finally:
        server.server_close()
        app.close()


if __name__ == "__main__":
    main()

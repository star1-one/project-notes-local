"""Optional: synthetic end-to-end smoke; consumes one Codex subscription request.

Run explicitly with: python3 tests/live_smoke.py
No real user documents are accessed; the temporary workspace is removed.
"""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import build_opener, ProxyHandler, Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Application, make_server


def main():
    with tempfile.TemporaryDirectory(prefix="project-desk-live-") as directory:
        app = Application(directory)
        httpd = make_server(app, 0)
        serving = threading.Thread(target=httpd.serve_forever, daemon=True)
        serving.start()
        opener = build_opener(ProxyHandler({}))
        address = f"http://127.0.0.1:{httpd.server_port}"
        csrf = ""

        def request(path, body=None, method="GET", headers=None, expect=200):
            h = {"X-CSRF-Token": csrf, **(headers or {})}
            encoded = None
            if body is not None:
                h["Content-Type"] = "application/json"
                encoded = json.dumps(body, ensure_ascii=False).encode()
            req = Request(address + path, encoded, h, method=method)
            try:
                response = opener.open(req, timeout=15)
            except HTTPError as exc:
                response = exc
            with response:
                result = json.load(response)
                assert response.status == expect, (response.status, result)
                return result

        try:
            bootstrap = request("/api/bootstrap")
            csrf = bootstrap["csrf_token"]
            assert bootstrap["connection"]["method"] == "chatgpt", bootstrap["connection"]
            request("/api/projects/project-1", {}, "PATCH", {"X-CSRF-Token": "wrong"}, 403)
            request("/api/bootstrap", headers={"Origin": "https://foreign.example"}, expect=403)
            request("/api/bootstrap", headers={"Host": "foreign.example"}, expect=403)
            first = request("/api/projects/project-1/sources", {"title": "테스트 일정 확인 메일", "kind": "email", "date": "2026-10-30", "content": "합성 테스트 자료입니다. 보고서 제출 예정일은 2026년 11월 12일이며, 최종 승인은 아직 대기 중입니다."}, "POST", expect=201)["source"]
            request("/api/projects/project-2/sources", {"title": "다른 과제의 합성 자료", "kind": "note", "content": "다른 과제의 비공개 검증표식은 프로젝트둘전용카나리아입니다."}, "POST", expect=201)
            request(f"/api/projects/project-2/sources/{first['id']}", expect=404)
            request("/api/projects/project-1", {"context": "메일 답장은 공손하고 간결하게 작성한다. 승인 여부는 추정하지 않는다."}, "PATCH")
            accepted = request("/api/projects/project-1/ask", {"mode": "reply", "message": "받은 메일: 보고서 제출 예정일과 승인 여부를 알려주세요. 자료를 참고해 회신 초안을 작성해주세요."}, "POST", expect=202)
            deadline = time.monotonic() + 250
            job = None
            while time.monotonic() < deadline:
                job = request(f"/api/jobs/{accepted['job_id']}")
                if job["status"] in {"failed", "completed"}:
                    break
                time.sleep(.5)
            assert job["status"] == "completed", job
            answer = job["result"]["message"]["content"]
            assert "11월 12일" in answer or "11월12일" in answer or "2026-11-12" in answer, answer
            assert "승인" in answer and ("대기" in answer or "확정" in answer or "아직" in answer), answer
            assert "프로젝트둘전용카나리아" not in answer
            conversation = request(f"/api/projects/project-1/conversations/{accepted['conversation_id']}")
            assert [m["role"] for m in conversation["messages"]] == ["user", "assistant"]
            assert conversation["messages"][-1]["references"][0]["id"] == first["id"]
            assert "coverage" in conversation["messages"][-1]
            backup = request("/api/projects/project-1/export")
            assert len(backup["sources"]) == 1 and len(backup["conversations"]) == 1
            assert "프로젝트둘전용카나리아" not in json.dumps(backup, ensure_ascii=False)
            print(json.dumps({"live_pro_reply": "passed", "csrf_origin_host": "passed", "project_isolation": "passed", "conversation_and_evidence_persistence": "passed", "project_backup": "passed", "answer_excerpt": answer[:900]}, ensure_ascii=False), flush=True)
        finally:
            httpd.shutdown()
            httpd.server_close()
            app.close()


if __name__ == "__main__":
    main()

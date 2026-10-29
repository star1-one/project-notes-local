import base64
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import ai_bridge
from server import Application, Handler, Store, UserError


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)

    def source(self, pid="project-1", content="협약에 따른 제출일은 11월 3일입니다.", title="협약"):
        return self.store.add_source(pid, {"title": title, "content": content, "kind": "document", "date": "2026-10-30"})["source"]

    def test_sources_and_conversations_are_scoped_to_project(self):
        source = self.source()
        conversation = self.store.create_conversation("project-1")["conversation"]
        self.assertEqual(self.store.overview("project-2")["sources"], [])
        for action in (lambda: self.store.source("project-2", source["id"]),
                       lambda: self.store.delete_source("project-2", source["id"]),
                       lambda: self.store.conversation("project-2", conversation["id"])):
            with self.assertRaises(UserError):
                action()
        prompt, refs, _ = self.store.prompt("project-2", "제출일은?")
        self.assertNotIn("11월 3일", prompt)
        self.assertEqual(refs, [])

    def test_memory_source_original_and_conversation_survive_reopen(self):
        content = "회의 결과: 제안은 검토 중이며 승인되지 않았습니다."
        source = self.store.add_source("project-1", {"title": "회의", "kind": "note", "filename": "회의.txt", "file_base64": base64.b64encode(content.encode()).decode()})["source"]
        self.store.update_project("project-1", {"context": "승인 대기. 실제 발송 기록 없음."})
        cid = self.store.create_conversation("project-1")["conversation"]["id"]
        self.store.message(cid, "assistant", "답장 초안", [{"id": source["id"]}])
        reopened = Store(self.temp.name)
        self.assertIn("승인 대기", reopened.project("project-1")["context"])
        self.assertEqual(reopened.source("project-1", source["id"], original=True)["original"], content.encode())
        exported = reopened.export("project-1")
        self.assertEqual(exported["conversations"][0]["messages"][0]["content"], "답장 초안")
        self.assertEqual(base64.b64decode(exported["sources"][0]["file_base64"]), content.encode())

    def test_duplicate_is_only_blocked_inside_same_project(self):
        self.source()
        with self.assertRaises(UserError) as raised:
            self.source()
        self.assertEqual(raised.exception.status, 409)
        self.source("project-2")

    def test_invalid_kind_date_base64_and_empty_material_are_rejected(self):
        for payload in ({"content": "본문", "kind": "other"}, {"content": "본문", "date": "2026-02-30"},
                        {"filename": "a.txt", "file_base64": "not base64"}, {"content": " "}):
            with self.assertRaises(UserError):
                self.store.add_source("project-1", payload)
        self.assertEqual(self.store.project("project-1")["source_count"], 0)

    def test_unspecified_source_date_is_not_fabricated(self):
        source = self.store.add_source("project-1", {"title": "날짜 없는 챗", "kind": "chat", "content": "검토하고 연락드리겠습니다."})["source"]
        self.assertEqual(source["date"], "")
        self.assertTrue(source["created_at"])

    def test_delete_removes_search_chunks_and_never_returns_removed_material(self):
        source = self.source(content="비밀 장비승인 마감일 11월 20일")
        self.store.delete_source("project-1", source["id"])
        evidence, refs, _ = self.store.evidence("project-1", "장비승인")
        self.assertEqual((evidence, refs), ([], []))

    def test_followup_keeps_previous_topic_for_large_document_search(self):
        for index in range(32):
            self.source(content=(f"일반 기술 문서 {index} " * 300), title=f"참고 {index}")
        target = self.source(content="개요 " * 1800 + "\n장비검수확정일은 2026년 11월 27일입니다.\n" + "보충 " * 800, title="장비 검토")
        cid = self.store.create_conversation("project-1")["conversation"]["id"]
        self.store.message(cid, "user", "장비검수확정일을 확인해 주세요")
        self.store.message(cid, "assistant", "관련 일정을 살펴보겠습니다.")
        self.store.message(cid, "user", "그 일정으로 답장을 작성해줘")
        prompt, refs, coverage = self.store.prompt("project-1", "그 일정으로 답장을 작성해줘", cid)
        self.assertTrue(coverage["partial"])
        self.assertIn("2026년 11월 27일", prompt)
        self.assertIn(target["id"], [r["id"] for r in refs])
        evidence, _, _ = self.store.evidence("project-1", "장비검수확정일")
        self.assertLessEqual(sum(len(e["text"]) for e in evidence), 42_000)

    def test_relevant_old_conversation_is_recalled_across_sessions(self):
        old = self.store.create_conversation("project-1", "이전 회의")["conversation"]["id"]
        self.store.message(old, "user", "미세분광기 검수는 외부기관 검토 후 진행한다고 들었습니다.")
        for index in range(15):
            cid = self.store.create_conversation("project-1", f"최근 대화 {index}")["conversation"]["id"]
            self.store.message(cid, "user", f"일상 업무 질문 {index}")
        prompt, _, _ = self.store.prompt("project-1", "미세분광기 검수는 어떤 상태야?")
        self.assertIn("외부기관 검토", prompt)


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = Application(self.temp.name)
        self.addCleanup(self.app.close)
        self.status = patch("ai_bridge.connection_status", return_value={"available": True, "authenticated": True, "method": "chatgpt", "message": "connected"})
        self.status.start()
        self.addCleanup(self.status.stop)

    def await_job(self, jid):
        for _ in range(100):
            job = self.app.store.job(jid)
            if job["status"] in {"failed", "completed"}:
                return job
            time.sleep(.01)
        self.fail("job did not finish")

    def test_duplicate_instance_does_not_corrupt_running_job(self):
        jid = self.app.store.new_job("project-1", "ask")
        self.app.store.set_job(jid, "running")
        with self.assertRaises(UserError):
            Application(self.temp.name)
        self.assertEqual(self.app.store.job(jid)["status"], "running")
        Store(self.temp.name)
        self.assertEqual(self.app.store.job(jid)["status"], "running")

    def test_success_persists_answer_with_scoped_evidence(self):
        self.app.store.add_source("project-1", {"title": "일정", "content": "제출은 11월 3일"})
        self.app.store.add_source("project-2", {"title": "다른 과제", "content": "다른과제만의비밀"})
        with patch("ai_bridge.generate", return_value={"text": "안녕하세요. 일정 확인 후 회신드리겠습니다."}) as generate:
            accepted = self.app.ask("project-1", {"message": "제출 일정 확인 요청에 답장해줘"})
            job = self.await_job(accepted["job_id"])
        self.assertEqual(job["status"], "completed")
        self.assertNotIn("다른과제만의비밀", generate.call_args.args[0])
        messages = self.app.store.conversation("project-1", accepted["conversation_id"])["messages"]
        self.assertEqual([m["role"] for m in messages], ["user", "assistant"])
        self.assertEqual(messages[-1]["references"][0]["title"], "일정")

    def test_failed_ai_does_not_persist_fake_answer(self):
        with patch("ai_bridge.generate", side_effect=ai_bridge.BridgeError("연결 실패")):
            accepted = self.app.ask("project-1", {"message": "답장 써줘"})
            job = self.await_job(accepted["job_id"])
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error"], "연결 실패")
        messages = self.app.store.conversation("project-1", accepted["conversation_id"])["messages"]
        self.assertEqual([m["role"] for m in messages], ["user"])

    def test_summary_is_suggestion_until_explicit_apply(self):
        self.app.store.update_project("project-1", {"context": "기존 확인된 맥락"})
        with patch("ai_bridge.generate", return_value={"text": "새 맥락 제안"}):
            accepted = self.app.ask("project-1", {}, summarize=True)
            job = self.await_job(accepted["job_id"])
        self.assertEqual(job["result"]["context"], "새 맥락 제안")
        self.assertEqual(self.app.store.project("project-1")["context"], "기존 확인된 맥락")

    def test_api_authentication_blocks_generation_before_persisting(self):
        self.app._connection = {"authenticated": False, "method": "api", "message": "API 로그인 차단"}
        self.app._checked = time.monotonic()
        with patch("ai_bridge.generate") as generate:
            with self.assertRaises(UserError):
                self.app.ask("project-1", {"message": "답장"})
            generate.assert_not_called()
        self.assertEqual(self.app.store.project("project-1")["conversation_count"], 0)


class RequestBoundaryTests(unittest.TestCase):
    def handler(self, headers, method="GET"):
        handler = Handler.__new__(Handler)
        handler.server = SimpleNamespace(server_port=8766, app=SimpleNamespace(csrf="test-session-token"))
        handler.headers = headers
        handler.command = method
        return handler

    def test_dns_rebinding_and_cross_origin_requests_rejected(self):
        for headers in ({"Host": "attacker.example:8766"},
                        {"Host": "127.0.0.1:8766", "Origin": "https://attacker.example"},
                        {"Host": "127.0.0.1:8766", "Sec-Fetch-Site": "cross-site"}):
            with self.assertRaises(UserError) as caught:
                self.handler(headers).validate_request()
            self.assertEqual(caught.exception.status, 403)

    def test_write_requires_session_token(self):
        for method in ("POST", "PATCH", "DELETE"):
            with self.assertRaises(UserError):
                self.handler({"Host": "127.0.0.1:8766"}, method).validate_request()
            self.handler({"Host": "127.0.0.1:8766", "X-CSRF-Token": "test-session-token", "Origin": "http://127.0.0.1:8766"}, method).validate_request()


if __name__ == "__main__":
    unittest.main()

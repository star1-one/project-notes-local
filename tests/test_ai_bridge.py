import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_bridge


def events(*items):
    return "\n".join(json.dumps(item, ensure_ascii=False) for item in items)


class BridgeTests(unittest.TestCase):
    def test_completed_answer_and_numeric_usage(self):
        output = events(
            {"type": "item.completed", "item": {"type": "agent_message", "phase": "commentary", "text": "검토 중"}},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "답장 초안입니다."}},
            {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 4, "private": "excluded"}},
        )
        result = ai_bridge._parse_output(output, "", 0)
        self.assertEqual(result["text"], "답장 초안입니다.")
        self.assertEqual(result["usage"], {"input_tokens": 10, "output_tokens": 4})

    def test_partial_message_is_not_success(self):
        output = events({"type": "item.completed", "item": {"type": "agent_message", "text": "미완성"}})
        with self.assertRaises(ai_bridge.BridgeError):
            ai_bridge._parse_output(output, "", 0)

    def test_error_does_not_expose_sensitive_stderr(self):
        output = events({"type": "turn.failed", "error": {"message": "429 secret-token"}})
        with self.assertRaises(ai_bridge.BridgeError) as error:
            ai_bridge._parse_output(output, "Authorization: Bearer private", 1)
        self.assertIn("사용 한도", str(error.exception))
        self.assertNotIn("private", str(error.exception))
        self.assertNotIn("secret", str(error.exception))

    def test_empty_success_is_rejected(self):
        with self.assertRaises(ai_bridge.BridgeError):
            ai_bridge._parse_output(events({"type": "turn.completed"}), "", 0)

    def test_unexpected_tool_use_fails_closed(self):
        output = events(
            {"type": "item.completed", "item": {"type": "command_execution", "command": "whoami"}},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "answer"}},
            {"type": "turn.completed"},
        )
        with self.assertRaises(ai_bridge.BridgeError):
            ai_bridge._parse_output(output, "", 0)

    @patch("ai_bridge._binary", return_value="/safe/codex")
    @patch("ai_bridge.subprocess.run")
    def test_chatgpt_status(self, run, _binary):
        run.return_value = subprocess.CompletedProcess([], 0, "", "Logged in using ChatGPT")
        status = ai_bridge.connection_status()
        self.assertTrue(status["authenticated"])
        self.assertEqual(status["method"], "chatgpt")
        self.assertNotIn("forced_login_method", " ".join(run.call_args.args[0]))

    @patch("ai_bridge._binary", return_value="/safe/codex")
    @patch("ai_bridge.subprocess.run")
    def test_api_status_refused_without_logout(self, run, _binary):
        run.return_value = subprocess.CompletedProcess([], 0, "", "Logged in using an API key")
        status = ai_bridge.connection_status()
        self.assertFalse(status["authenticated"])
        self.assertEqual(status["method"], "api")
        self.assertEqual(run.call_args.args[0], ["/safe/codex", "login", "status"])

    @patch("ai_bridge.connection_status", return_value={"authenticated": False, "method": "api", "message": "API 거절"})
    @patch("ai_bridge.subprocess.Popen")
    def test_generation_rejects_api_before_launch(self, popen, _status):
        with self.assertRaisesRegex(ai_bridge.BridgeError, "API 거절"):
            ai_bridge.generate("hello", Path("/tmp"))
        popen.assert_not_called()

    def test_no_api_keys_or_inherited_sessions_in_environment(self):
        with patch.dict(os.environ, {
            "HOME": "/safe/home", "OPENAI_API_KEY": "secret", "CODEX_API_KEY": "secret2",
            "CODEX_ACCESS_TOKEN": "secret3", "CODEX_THREAD_ID": "parent-session",
            "OPENAI_BASE_URL": "https://bad.example", "ANTHROPIC_API_KEY": "secret4",
        }, clear=True):
            env = ai_bridge._environment()
        self.assertEqual(env["HOME"], "/safe/home")
        self.assertFalse(any("secret" in value for value in env.values()))
        self.assertNotIn("CODEX_THREAD_ID", env)
        self.assertNotIn("OPENAI_BASE_URL", env)

    @patch("ai_bridge.connection_status", return_value={"authenticated": True, "method": "chatgpt"})
    @patch("ai_bridge._binary", return_value="/safe/codex")
    @patch("ai_bridge.subprocess.Popen")
    def test_generate_uses_stdin_isolation_and_disabled_tools(self, popen, _binary, _status):
        process = MagicMock()
        process.returncode = 0
        process.communicate.return_value = (events(
            {"type": "item.completed", "item": {"type": "agent_message", "text": "연결됐습니다."}},
            {"type": "turn.completed"},
        ), "")
        popen.return_value = process
        with tempfile.TemporaryDirectory() as base:
            result = ai_bridge.generate("private document", Path(base))
            command = popen.call_args.args[0]
            self.assertNotIn("private document", command)
            self.assertIn('forced_login_method="chatgpt"', command)
            self.assertIn('features.shell_tool=false', command)
            self.assertIn('features.apps=false', command)
            self.assertIn('features.hooks=false', command)
            self.assertIn('web_search="disabled"', command)
            self.assertIn("--ignore-user-config", command)
            self.assertIn("--ephemeral", command)
            self.assertIn("read-only", command)
            self.assertEqual(command[-1], "-")
            self.assertEqual(list(Path(base).iterdir()), [])
        self.assertEqual(result["text"], "연결됐습니다.")
        self.assertFalse(popen.call_args.kwargs["shell"])
        self.assertEqual(process.communicate.call_args.kwargs["input"], "private document")

    @patch("ai_bridge.connection_status", return_value={"authenticated": True, "method": "chatgpt"})
    @patch("ai_bridge._binary", return_value="/safe/codex")
    @patch("ai_bridge.os.killpg")
    @patch("ai_bridge.subprocess.Popen")
    def test_timeout_kills_subprocess_group(self, popen, killpg, _binary, _status):
        process = MagicMock(pid=12345)
        process.communicate.side_effect = [subprocess.TimeoutExpired("codex", 1), ("", "")]
        popen.return_value = process
        with tempfile.TemporaryDirectory() as base:
            with self.assertRaisesRegex(ai_bridge.BridgeError, "시간이 초과"):
                ai_bridge.generate("hello", Path(base), timeout=1)
        killpg.assert_called_once()


if __name__ == "__main__":
    unittest.main()

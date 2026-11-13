# -*- coding: utf-8 -*-
import json
import threading
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from taskdock import analyzer


class AnalyzerTest(unittest.TestCase):
    def test_local_chinese_email_extracts_action(self):
        email = {
            "subject": "请于11月20日18:00前提交年度预算表",
            "body": "林夏，请提交年度预算表，负责人：林夏。\n请同步更新供应商合同金额。",
            "sender": "财务部",
            "date": "2026-11-03T10:00:00",
        }
        now = datetime(2026, 11, 3, 12, 0)
        result = analyzer.analyze_email(email, [], at=now)
        self.assertEqual(result["intent"], "new")
        self.assertIn("预算", result["title"])
        self.assertEqual(result["owner"], "林夏")
        self.assertIsNotNone(result["due"])
        self.assertTrue(result["actionable"])
        self.assertIn("预算", result["requirement"])

    def test_ai_split_projects_with_existing_target(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                self.rfile.read(length)
                content = json.dumps({
                    "email_summary": "一封邮件涉及两个项目",
                    "projects": [
                        {
                            "title": "年度预算编制", "summary": "补充预算表",
                            "requirement": "提交预算表", "due": "2026-11-20T18:00:00",
                            "owner": "林夏", "action_items": ["提交预算表"],
                            "relation": "update", "target_task_id": "t1",
                            "match_reason": "与预算任务同名", "confidence": 0.9,
                        },
                        {
                            "title": "供应商续签", "summary": "合同续签",
                            "requirement": "准备合同", "due": None,
                            "owner": "", "action_items": ["准备合同"],
                            "relation": "new", "target_task_id": None,
                            "match_reason": "新项目", "confidence": 0.8,
                        },
                    ],
                }, ensure_ascii=False)
                raw = json.dumps({"choices": [{"message": {"content": content}}]},
                                 ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            result = analyzer.analyze_email_ai(
                {"subject": "两个项目", "body": "年度预算和供应商续签"},
                {"endpoint": "http://127.0.0.1:%d/v1/chat/completions" % server.server_address[1],
                 "key": "k", "model": "m"},
                tasks=[{"id": "t1", "title": "年度预算编制", "owner": "林夏"}],
            )
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(len(result["projects"]), 2)
        self.assertEqual(result["projects"][0]["relation"], "update")
        self.assertEqual(result["projects"][0]["target_task_id"], "t1")
        self.assertEqual(result["projects"][1]["relation"], "new")
        self.assertIsNone(result["projects"][1]["target_task_id"])

    def test_ai_project_keeps_background_progress_situation(self):
        project = analyzer._normalize_ai_project({
            "title": "杭千高速运维",
            "summary": "已签约实施",
            "background": "2026-2028 运维项目，合同 28W/年，陈宇、李子懿驻场。",
            "progress": "本周已签订合同，人员已进场。",
            "situation": "移动准备走招投标，需要关注验收节点。",
            "requirement": "提交本期服务计划。",
            "deliverable": "服务计划、人员排班表。",
            "action_items": ["提交服务计划"],
            "status": "已签约",
        }, "周报", "正文", set())
        self.assertIn("【背景】", project["requirement"])
        self.assertIn("【当前进展】", project["requirement"])
        self.assertIn("【当前情况】", project["requirement"])
        self.assertIn("【交付标准】", project["requirement"])
        self.assertIn("28W/年", project["requirement"])

    def test_glm53_requests_low_reasoning(self):
        captured = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                captured["payload"] = json.loads(self.rfile.read(length).decode("utf-8"))
                content = json.dumps({
                    "email_summary": "测试",
                    "projects": [{"title": "测试项目", "requirement": "完成测试"}],
                }, ensure_ascii=False)
                raw = json.dumps({"choices": [{"message": {"content": content},
                                               "finish_reason": "stop"}]},
                                 ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            analyzer.analyze_email_ai(
                {"subject": "测试", "body": "测试"},
                {"endpoint": "http://127.0.0.1:%d/bigmodel.cn/v1/chat/completions"
                             % server.server_address[1],
                 "key": "k", "model": "glm-5.3-flash"},
                tasks=[], timeout=5,
            )
        finally:
            server.shutdown()
            server.server_close()
        payload = captured["payload"]
        self.assertEqual(payload.get("thinking"), {"type": "enabled"})
        self.assertEqual(payload.get("reasoning_effort"), "low")
        self.assertEqual(payload.get("max_tokens"), 12000)

    def test_ai_timeout_message_is_friendly(self):
        import time

        class SlowHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                self.rfile.read(length)
                time.sleep(0.8)
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), SlowHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(analyzer.AnalyzerError) as ctx:
                analyzer.analyze_email_ai(
                    {"subject": "测试", "body": "测试"},
                    {"endpoint": "http://127.0.0.1:%d/v1/chat/completions" % server.server_address[1],
                     "key": "k", "model": "m"},
                    timeout=0.15,
                )
        finally:
            server.shutdown()
            server.server_close()
        self.assertIn("超时", str(ctx.exception))

    def test_ai_chat_completions_draft(self):
        captured = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                captured["body"] = json.loads(self.rfile.read(length).decode("utf-8"))
                captured["auth"] = self.headers.get("Authorization")
                content = json.dumps({
                    "title": "提交年度预算",
                    "requirement": "整理预算表并提交财务",
                    "due": "2026-11-20T18:00:00",
                    "owner": "林夏",
                    "action_items": ["整理预算", "发送财务"],
                    "confidence": 0.88,
                }, ensure_ascii=False)
                payload = {"choices": [{"message": {"content": content}}]}
                raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = analyzer.analyze_email_ai(
                {"subject": "预算", "body": "请提交预算", "sender": "财务"},
                {
                    "endpoint": "http://127.0.0.1:%d/v1/chat/completions" % server.server_address[1],
                    "key": "test-key",
                    "model": "test-model",
                },
            )
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(result["title"], "提交年度预算")
        self.assertEqual(result["owner"], "林夏")
        self.assertTrue(result["ai"])
        self.assertEqual(result["confidence"], 0.88)
        self.assertEqual(captured["auth"], "Bearer test-key")
        self.assertEqual(captured["body"]["model"], "test-model")
        self.assertIn("messages", captured["body"])


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import format_datetime

from taskdock import analyzer, demo, mailer, model
from taskdock.store import Store


def make_task(title="测试任务", subs=(), progress=0, start=-1, due=2):
    base = datetime(2026, 11, 2, 12, 0)
    task = model.create_task(
        title=title,
        start=base + timedelta(days=start),
        due=base + timedelta(days=due),
    )
    for text_, done in subs:
        model.add_subtask(task, text_)
        if done:
            task["subtasks"][-1]["done"] = True
    model.set_progress(task, progress)
    return task


class ModelRulesTest(unittest.TestCase):
    def test_completion_gate(self):
        task = make_task(subs=[("A", True), ("B", False)])
        with self.assertRaises(model.CompletionBlocked) as ctx:
            model.mark_complete(task)
        self.assertEqual(ctx.exception.pending, 1)
        self.assertFalse(task["completed"])
        model.toggle_subtask(task, task["subtasks"][1]["id"])
        model.mark_complete(task)
        self.assertTrue(task["completed"])
        self.assertEqual(task["progress"], 100)
        self.assertTrue(model.all_subtasks_done(task))

    def test_progress_caps_at_99_when_subtasks_pending(self):
        task = make_task(subs=[("A", True), ("B", False)])
        value = model.set_progress(task, 100)
        self.assertEqual(value, 99)
        self.assertFalse(task["completed"])
        model.toggle_subtask(task, task["subtasks"][1]["id"])
        value = model.set_progress(task, 100)
        self.assertEqual(value, 100)
        self.assertTrue(task["completed"])

    def test_no_subtasks_can_complete(self):
        task = make_task()
        model.set_progress(task, 100)
        self.assertTrue(task["completed"])
        model.set_progress(task, 40)
        self.assertFalse(task["completed"])

    def test_unchecking_subtask_reopens_completed_task(self):
        task = make_task(subs=[("A", True), ("B", True)])
        model.mark_complete(task)
        self.assertTrue(task["completed"])
        model.toggle_subtask(task, task["subtasks"][0]["id"])
        self.assertFalse(task["completed"])
        self.assertIsNone(task["completed_at"])
        self.assertLessEqual(task["progress"], 95)

    def test_add_subtask_reopens_completed_task(self):
        task = make_task(subs=[("A", True)])
        model.mark_complete(task)
        model.add_subtask(task, "B")
        self.assertFalse(task["completed"])

    def test_dates_and_status(self):
        base = datetime(2026, 11, 2, 12, 0)
        task = model.create_task("x", start=base - timedelta(days=1),
                                 due=base + timedelta(days=1))
        self.assertEqual(model.status_of(task, base), "doing")
        future = model.create_task("y", start=base + timedelta(days=1),
                                   due=base + timedelta(days=3))
        self.assertEqual(model.status_of(future, base), "upcoming")
        late = model.create_task("z", start=base - timedelta(days=4),
                                 due=base - timedelta(days=1))
        self.assertEqual(model.status_of(late, base), "overdue")
        self.assertEqual(model.parse_dt("2026-11-05T18:00:00"),
                         datetime(2026, 11, 5, 18, 0))
        self.assertEqual(model.parse_dt("11月5日").hour, 18)
        self.assertEqual(model.parse_dt("2026/11/05 09:30"),
                         datetime(2026, 11, 5, 9, 30))
        self.assertIsNone(model.parse_dt("不是时间"))

    def test_counts(self):
        tasks = demo.seed_data()["tasks"]
        data = model.counts(tasks)
        self.assertEqual(data["total"], 5)
        self.assertEqual(data["done"], 1)
        self.assertEqual(data["overdue"], 1)
        self.assertEqual(data["percent"], 20)

    def test_normalize_rejects_stale_completed(self):
        task = make_task(subs=[("A", False)])
        task["completed"] = True
        task["progress"] = 100
        model.normalize_task(task)
        self.assertFalse(task["completed"])
        self.assertLessEqual(task["progress"], 95)


class AnalyzerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = demo.seed_data()
        cls.tasks = cls.data["tasks"]
        cls.analyses = [analyzer.analyze_email(e, cls.tasks) for e in cls.data["emails"]]

    def test_demo_emails(self):
        first, second, third, fourth = self.analyses
        self.assertEqual(first["intent"], "update")
        expected_due = (model.now() + timedelta(days=3)).replace(
            hour=18, minute=0, second=0, microsecond=0
        )
        self.assertEqual(first["due"], model.iso(expected_due))
        self.assertEqual(first["owner"], "林夏")
        self.assertEqual(first["progress"], 70)
        self.assertEqual(second["intent"], "new")
        self.assertEqual(second["owner"], "周然")
        self.assertEqual(third["intent"], "update")
        self.assertEqual(third["owner"], "周然")
        self.assertEqual(fourth["intent"], "info")

    def test_deadline_variants(self):
        at = datetime(2026, 11, 2, 12, 0)
        due, _ = analyzer.extract_due("请于2026年12月8日下午3点前提交", at)
        self.assertEqual(due, datetime(2026, 12, 8, 15, 0))
        due, _ = analyzer.extract_due("请在明天 9:00 前反馈", at)
        self.assertEqual(due, datetime(2026, 11, 3, 9, 0))
        due, _ = analyzer.extract_due("deadline: 2026-11-20", at)
        self.assertEqual(due, datetime(2026, 11, 20, 18, 0))

    def test_owner_variants(self):
        self.assertEqual(analyzer.extract_owner("负责人：林夏"), "林夏")
        self.assertEqual(analyzer.extract_owner("周然，你好：\n请确认"), "周然")
        self.assertEqual(analyzer.extract_owner("周然，\n\n合同需要确认"), "周然")

    def test_action_lines_clean_greeting(self):
        lines = analyzer.action_lines("周然，你好：\n请于11月5日前提交材料。")
        self.assertTrue(lines)
        self.assertNotIn("你好", lines[0])
        self.assertIn("提交材料", lines[0])

    def test_match_existing(self):
        matches = analyzer.match_tasks("回复: 供应商合同续签", "请确认条款", self.tasks)
        self.assertTrue(matches)
        self.assertEqual(matches[0]["title"], "供应商合同续签")

    def test_done_hint(self):
        self.assertTrue(analyzer.done_hint("该事项已完成。"))
        self.assertFalse(analyzer.done_hint("尚未完成，请继续跟进。"))

    def test_ai_project_keeps_week_diff_and_subtask_choice(self):
        project = analyzer._normalize_ai_project({
            "title": "周报项目",
            "relation": "update",
            "changes": ["新增验收材料", "完成时间推迟"],
            "suggest_subtask": True,
            "subtask_title": "补充验收材料",
        }, "本周周报", "", set())
        self.assertEqual(project["changes"], ["新增验收材料", "完成时间推迟"])
        self.assertTrue(project["suggest_subtask"])
        self.assertEqual(project["subtask_title"], "补充验收材料")


class MailParsingTest(unittest.TestCase):
    def test_mime_parse(self):
        message = MIMEMultipart("alternative")
        message["Subject"] = "测试邮件：请于11月8日前提交"
        message["From"] = "林夏 <linxia@example.com>"
        message["To"] = "me@example.com"
        message["Date"] = format_datetime(datetime(2026, 11, 2, 9, 30))
        message.attach(MIMEText("你好，\n请于11月8日18:00前提交材料。\n负责人：林夏。", "plain", "utf-8"))
        message.attach(MIMEText("<p>你好，请提交材料。</p>", "html", "utf-8"))
        parsed = mailer.parse_email_bytes(message.as_bytes(), uid="42", account="me@example.com")
        self.assertIn("测试邮件", parsed["subject"])
        self.assertEqual(parsed["sender"], "林夏")
        self.assertIn("提交材料", parsed["body"])
        self.assertEqual(parsed["uid"], "42")
        self.assertTrue(parsed["id"].startswith("m_"))

    def test_html_only_parse(self):
        message = MIMEText("<div>请在 <b>明天</b> 前反馈。</div>", "html", "utf-8")
        message["Subject"] = "HTML"
        message["From"] = "a@b.com"
        parsed = mailer.parse_email_bytes(message.as_bytes(), uid="43")
        self.assertIn("明天", parsed["body"])
        self.assertNotIn("<div>", parsed["body"])

    def test_eml_import(self):
        message = MIMEText("请于11月9日前完成。", "plain", "utf-8")
        message["Subject"] = "导入测试"
        message["From"] = "a@b.com"
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "test.eml")
            with open(path, "wb") as handle:
                handle.write(message.as_bytes())
            parsed = mailer.import_eml(path)
            self.assertIn("导入测试", parsed["subject"])
            self.assertEqual(parsed["folder"], "LOCAL")


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp.cleanup()

    def test_roundtrip_and_password(self):
        store = Store(self.temp.name, seed=True)
        store.load()
        self.assertEqual(len(store.tasks), 5)
        self.assertEqual(store.settings()["imap_host"], "imap.em.dingtalk.com")
        store.set_setting("account", "me@example.com")
        store.set_password("secret-token")
        self.assertEqual(store.password(), "secret-token")
        second = Store(self.temp.name, seed=False)
        second.load()
        self.assertEqual(second.settings()["account"], "me@example.com")
        self.assertEqual(second.password(), "secret-token")
        self.assertEqual(len(second.tasks), 5)

    def test_changed_email_is_reanalyzed_and_link_survives(self):
        store = Store(self.temp.name, seed=True)
        store.load()
        analyzer.ensure_analyses(store)
        email = store.emails[0]
        task = store.tasks[0]
        store.link_email(email["id"], task["id"])
        incoming = dict(email)
        incoming["body"] = incoming["body"] + "\n补充：进度更新为 85%。"
        store.merge_emails([incoming])
        self.assertIsNone(store.email(email["id"])["analysis"])
        analyzer.ensure_analyses(store)
        refreshed = store.email(email["id"])
        self.assertEqual(refreshed["analysis"]["linked_task_id"], task["id"])

    def test_task_persistence(self):
        store = Store(self.temp.name, seed=True)
        store.load()
        task = store.tasks[0]
        task["progress"] = 77
        store.save()
        second = Store(self.temp.name, seed=False)
        second.load()
        self.assertEqual(second.task(task["id"])["progress"], 77)

    def test_export_import(self):
        store = Store(self.temp.name, seed=True)
        store.load()
        payload = store.export_payload()
        self.assertNotIn("mail_password", payload["settings"])
        target = os.path.join(self.temp.name, "backup.json")
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        another = Store(os.path.join(self.temp.name, "another"), seed=False)
        another.load()
        count_tasks, count_emails = another.import_payload(payload)
        self.assertEqual(count_tasks, 5)
        self.assertEqual(count_emails, 4)

    def test_clear_demo(self):
        store = Store(self.temp.name, seed=True)
        store.load()
        store.clear_demo()
        self.assertEqual(len(store.tasks), 0)
        self.assertEqual(len(store.emails), 0)

    def test_no_demo(self):
        store = Store(os.path.join(self.temp.name, "empty"), seed=False)
        store.load()
        self.assertEqual(store.tasks, [])
        self.assertEqual(store.emails, [])

    def test_default_store_is_empty(self):
        store = Store(os.path.join(self.temp.name, "empty-default"))
        store.load()
        self.assertEqual(store.tasks, [])
        self.assertEqual(store.emails, [])

    def test_purge_demo_once(self):
        store = Store(self.temp.name, seed=True)
        store.load()
        self.assertEqual(len(store.tasks), 5)
        self.assertGreater(store.purge_demo_once(), 0)
        self.assertEqual(len(store.tasks), 0)
        self.assertEqual(len(store.emails), 0)
        self.assertEqual(store.purge_demo_once(), 0)

    def test_delete_tasks_and_all(self):
        store = Store(self.temp.name, seed=True)
        store.load()
        first, second = store.tasks[0], store.tasks[1]
        store.delete_tasks([first["id"], second["id"]])
        self.assertIsNone(store.task(first["id"]))
        self.assertIsNone(store.task(second["id"]))
        self.assertEqual(len(store.tasks), 3)
        store.delete_all_tasks()
        self.assertEqual(store.tasks, [])
        self.assertEqual(len(store.emails), 4)


if __name__ == "__main__":
    unittest.main()

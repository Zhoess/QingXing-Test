# -*- coding: utf-8 -*-
import os
import tempfile
import time
import unittest
from datetime import datetime

from taskdock import model
from taskdock.date_picker import DateTimePicker
from taskdock.page_mail import AIProjectReviewDialog, AIProjectSummaryDialog
from taskdock.page_collab import ForwardDialog, FriendChatDialog
from taskdock.page_tasks import LostReasonDialog, SubtaskDialog, TaskView, TaskEditor
from taskdock.ui_app import build_app
from taskdock.owner_picker import OwnerField


class UiFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = build_app(data_dir=self.temp.name, seed=True, auto_show=False)
        self.pump()

    def tearDown(self):
        try:
            self.app.close_app()
        except Exception:
            try:
                self.app.destroy()
            except Exception:
                pass
        self.temp.cleanup()

    def pump(self, rounds=3):
        for _ in range(rounds):
            self.app.update()
            time.sleep(0.02)

    def test_pages_built(self):
        self.assertEqual(set(self.app.pages), {"tasks", "mail", "collab", "settings"})
        self.assertEqual(len(self.app.store.tasks), 5)
        self.assertEqual(len(self.app.store.emails), 4)
        self.assertTrue(all(e.get("analysis") for e in self.app.store.emails))

    def test_collab_page_login_view(self):
        self.app.switch_page("collab")
        self.pump()
        page = self.app.pages["collab"]
        self.assertTrue(hasattr(page, "login_btn"))
        self.assertIn("协作网络", page.body.winfo_children()[0].winfo_children()[0].cget("text"))

    def test_completed_and_lost_tasks_sink_to_bottom(self):
        active = model.create_task("进行中任务")
        done = model.create_task("已完成任务")
        lost = model.create_task("已流失任务")
        model.mark_complete(done)
        model.mark_lost(lost)
        ordered = model.sort_tasks([lost, active, done])
        self.assertEqual(ordered[0]["id"], active["id"])
        self.assertEqual({ordered[-1]["id"], ordered[-2]["id"]}, {done["id"], lost["id"]})

    def test_task_view_has_lost_action(self):
        task = self.app.store.tasks[0]
        task["tags"] = []
        view = TaskView(self.app, task)
        self.pump()
        view._toggle_lost()
        self.pump()
        dialogs = [w for w in self.app.winfo_children()
                   if isinstance(w, LostReasonDialog)]
        self.assertEqual(len(dialogs), 1)
        dialogs[0].reason_text.insert("1.0", "客户取消")
        dialogs[0]._submit()
        self.pump()
        self.assertIn("lost", task["tags"])
        self.assertEqual(task["lost_reason"], "客户取消")
        view = TaskView(self.app, task)
        self.pump()
        texts = []
        stack = [view.content]
        while stack:
            widget = stack.pop()
            stack.extend(widget.winfo_children())
            try:
                value = widget.cget("text")
            except Exception:
                value = ""
            if value:
                texts.append(str(value))
        self.assertIn("流失原因", texts)
        self.assertIn("客户取消", texts)
        view.force_close()
        self.app.toggle_task_lost(task)

    def test_lost_reason_dialog_requires_text(self):
        task = self.app.store.tasks[0]
        reasons = []
        dialog = LostReasonDialog(self.app, task, reasons.append)
        self.pump()
        dialog._submit()
        self.assertEqual(reasons, [])
        self.assertIn("请填写", dialog.error.cget("text"))
        dialog.reason_text.insert("1.0", "预算取消")
        dialog._submit()
        self.pump()
        self.assertEqual(reasons, ["预算取消"])

    def test_task_lost_button_toggles_tag(self):
        task = self.app.store.tasks[0]
        task["tags"] = []
        self.app.mark_task_lost(task, "客户取消")
        self.assertIn("lost", task["tags"])
        self.assertIn(task, model.filter_tasks([task], "lost"))
        self.app.toggle_task_lost(task)
        self.assertNotIn("lost", task["tags"])
        self.assertEqual(task["lost_reason"], "")

    def test_owner_picker_has_no_duplicate_entries(self):
        field = OwnerField(self.app, self.app, display="待指派")
        self.assertEqual(field.values.count("待指派"), 1)
        self.assertEqual(len(field.values), len(set(field.values)))
        self.assertEqual(field.get(), ("", ""))
        field.destroy()

    def test_convert_task_to_existing_parent_subtask(self):
        parent = model.create_task("父任务", "父")
        child = model.create_task("原子任务", "子")
        self.app.store.add_task(parent)
        self.app.store.add_task(child)
        before = len(parent["subtasks"])
        self.app.convert_task_to_subtask(child, parent)
        self.assertEqual(len(parent["subtasks"]), before + 1)
        self.assertTrue(child.get("archived"))
        self.assertEqual(child.get("converted_to_subtask_parent_id"), parent["id"])
        self.assertEqual(parent["subtasks"][-1]["title"], "原子任务")

    def test_ai_project_summary_adds_subtask(self):
        email = self.app.store.emails[0]
        parent = model.create_task("父项目", "父")
        self.app.store.add_task(parent)
        project = {"title": "AI 子事项", "requirement": "做子事项", "owner": "不存在"}
        self.app.add_ai_project_subtask(project, email, parent)
        self.assertEqual(project["task_id"], parent["id"])
        self.assertTrue(any(s["title"] == "AI 子事项" for s in parent["subtasks"]))

    def test_ai_project_can_choose_parent_task(self):
        email = self.app.store.emails[0]
        dialog = AIProjectReviewDialog(self.app, email, {
            "email_summary": "选择父任务",
            "projects": [{"title": "可挂载事项", "relation": "new", "confidence": 0.8}],
        })
        self.pump()
        parent = self.app.store.tasks[0]
        row = dialog.rows[0]
        dialog._set_parent(row, parent)
        self.assertEqual(row["action"], "subtask")
        self.assertEqual(row["target_map"][row["target_var"].get()], parent["id"])
        self.assertIn(parent["title"], row["parent_label"].cget("text"))
        dialog.force_close()
        self.pump()

    def test_ai_project_diff_can_be_added_as_subtask(self):
        store = self.app.store
        email = store.emails[0]
        target = store.tasks[0]
        analysis = {
            "email_summary": "周报差异",
            "projects": [{
                "title": target["title"],
                "summary": "本周有新增要求",
                "requirement": "补充新的验收材料",
                "relation": "update",
                "target_task_id": target["id"],
                "changes": ["新增验收材料要求", "完成时间推迟到下周"],
                "suggest_subtask": True,
                "subtask_title": "补充验收材料",
                "confidence": 0.9,
            }],
        }
        dialog = AIProjectReviewDialog(self.app, email, analysis)
        self.pump()
        row = dialog.rows[0]
        self.assertTrue(row.get("diff_var"))
        row["diff_var"].set(True)
        dialog._toggle_diff_subtask(row)
        self.assertEqual(row["action"], "subtask")
        dialog._apply()
        self.pump()
        sub = next((s for s in target["subtasks"] if s["title"] == "补充验收材料"), None)
        self.assertIsNotNone(sub)
        self.assertIn("新增验收材料要求", sub["requirement"])
        self.assertIn("相关要求", sub["requirement"])
        for summary in [w for w in self.app.winfo_children()
                        if isinstance(w, AIProjectSummaryDialog)]:
            summary.force_close()
        self.pump()

    def test_forward_dialog_allows_multiple_tasks(self):
        tasks = self.app.store.active_tasks()[:2]
        friend = {"id": "friend-1", "display_name": "陈宇", "username": "chenyu"}
        dialog = ForwardDialog(self.app, friend=friend)
        self.pump()
        for task in tasks:
            dialog._choose_task(task)
        self.assertEqual([item["id"] for item in dialog.selected_tasks],
                         [task["id"] for task in tasks])
        dialog._choose_task(tasks[0])
        self.assertEqual([item["id"] for item in dialog.selected_tasks],
                         [tasks[1]["id"]])
        dialog._choose_task(tasks[0])
        captured = {}

        def fake_forward(task_ids, friend_id, mode, message, on_success=None, on_error=None):
            captured.update(task_ids=list(task_ids), friend_id=friend_id, mode=mode)
            if on_success:
                on_success([{} for _ in task_ids])

        self.app.forward_tasks_async = fake_forward
        dialog._send()
        self.assertEqual(captured["task_ids"], [tasks[1]["id"], tasks[0]["id"]])
        self.pump()

    def test_friend_chat_sends_and_renders_messages(self):
        self.app.collab_user = {"id": 1, "username": "alice"}
        friend = {"id": 2, "display_name": "陈宇", "username": "chenyu"}
        dialog = FriendChatDialog(self.app, friend)
        self.pump()
        dialog._render([
            {"from_id": 1, "from_name": "我", "body": "你好", "created_at": "2026-11-10T10:00:00"},
            {"from_id": 2, "from_name": "陈宇", "body": "收到", "created_at": "2026-11-10T10:01:00"},
        ])
        self.pump()
        texts = []
        stack = [dialog.messages_box]
        while stack:
            widget = stack.pop()
            stack.extend(widget.winfo_children())
            try:
                value = widget.cget("text")
            except Exception:
                value = ""
            if value:
                texts.append(str(value))
        self.assertIn("你好", texts)
        self.assertIn("收到", texts)
        captured = {}

        def fake_send(friend_id, body, on_success=None, on_error=None):
            captured.update(friend_id=friend_id, body=body)
            if on_success:
                on_success({"ok": True})

        self.app.send_friend_message = fake_send
        dialog.input.insert("1.0", "转发这个任务给你")
        dialog._send()
        self.assertEqual(captured["friend_id"], 2)
        self.assertEqual(captured["body"], "转发这个任务给你")
        dialog.force_close()
        self.pump()

    def test_ai_project_review_actions(self):
        store = self.app.store
        email = store.emails[0]
        target = store.tasks[0]
        before_tasks = len(store.tasks)
        before_subs = len(target["subtasks"])
        analysis = {
            "email_summary": "两个项目",
            "projects": [
                {"title": "新项目", "summary": "新事项", "requirement": "完成新事项",
                 "due": "2026-11-20T18:00:00", "owner": "林夏",
                 "relation": "new", "confidence": 0.8},
                {"title": "目标子任务", "summary": "补充子事项",
                 "requirement": "补充子事项", "due": None, "owner": "周然",
                 "relation": "subtask", "target_task_id": target["id"],
                 "confidence": 0.9},
            ],
        }
        self.app.collab_data = {}
        dialog = AIProjectReviewDialog(self.app, email, analysis)
        self.pump()
        self.assertEqual(len(dialog.rows), 2)
        dialog._apply()
        self.pump()
        self.assertEqual(len(store.tasks), before_tasks + 1)
        self.assertEqual(len(target["subtasks"]), before_subs + 1)
        self.assertTrue(any("新项目" in t.get("title", "") for t in store.tasks))
        self.assertIn(target["id"], email["analysis"].get("linked_task_ids", []))
        summaries = [w for w in self.app.winfo_children()
                     if isinstance(w, AIProjectSummaryDialog)]
        self.assertEqual(len(summaries), 1)
        self.assertGreater(len(email["analysis"]["projects"][0].get("task_id") or ""), 0)
        summaries[0].force_close()

    def test_task_complete_and_reopen(self):
        task = model.create_task("完成测试", "验证完成按钮", owner="测试员")
        self.app.store.add_task(task)
        self.assertTrue(self.app.toggle_task_complete(task))
        self.assertTrue(task["completed"])
        self.assertEqual(task["progress"], 100)
        self.assertTrue(self.app.toggle_task_complete(task))
        self.assertFalse(task["completed"])
        self.assertLess(task["progress"], 100)

    def test_task_subset_list(self):
        ids = [t["id"] for t in self.app.store.active_tasks()[:2]]
        self.app.show_tasks(ids, "测试筛选")
        self.pump()
        page = self.app.pages["tasks"]
        self.assertEqual(page.subset_ids, set(ids))
        self.assertEqual(set(page.cards), set(ids))
        page.clear_subset()
        self.pump()
        self.assertIsNone(page.subset_ids)
        self.assertEqual(len(page.cards), len(self.app.store.active_tasks()))

    def test_owner_directory_crud(self):
        store = self.app.store
        owner = store.add_owner("林夏", "linxia")
        self.assertEqual(store.owner_directory()[0]["name"], "林夏")
        updated = store.update_owner(owner["id"], "林夏夏", "linxia2", False)
        self.assertEqual(updated["name"], "林夏夏")
        self.assertFalse(updated["active"])
        page = self.app.pages["settings"]
        page._render_owners()
        self.pump()
        self.assertTrue(page.owner_list.winfo_children())
        self.assertTrue(store.delete_owner(owner["id"]))
        self.assertEqual(store.owner_directory(), [])

    def test_owner_options_use_self_and_friends_only(self):
        self.app.collab_data = {
            "user": {"display_name": "我自己", "username": "me"},
            "friends": [{"display_name": "好友甲", "username": "friend1"}],
            "directory": [{"display_name": "无关账号", "username": "stranger"}],
        }
        self.app.store.tasks[0]["owner"] = "鲁总"
        options = self.app.owner_options()
        names = {item.get("display_name") for item in options}
        accounts = {item.get("username") for item in options}
        self.assertIn("我自己", names)
        self.assertIn("好友甲", names)
        self.assertIn("me", accounts)
        self.assertIn("friend1", accounts)
        self.assertNotIn("无关账号", names)
        self.assertNotIn("鲁总", names)

    def test_owner_options_follow_org_scope(self):
        self.app.collab_data = {
            "user": {"display_name": "我自己", "username": "me"},
            "org_unit_id": 10,
            "owner_scope": [
                {"display_name": "同级同事", "username": "peer"},
                {"display_name": "下级同事", "username": "child"},
            ],
            "friends": [{"display_name": "范围外好友", "username": "outsider"}],
        }
        options = self.app.owner_options()
        accounts = {item.get("username") for item in options}
        self.assertIn("peer", accounts)
        self.assertIn("child", accounts)
        self.assertIn("me", accounts)
        self.assertNotIn("outsider", accounts)

    def test_owner_settings_lists_synced_accounts(self):
        self.app.collab_data = {
            "user": {"display_name": "我自己", "username": "me"},
            "org_unit_id": 10,
            "owner_scope": [{"display_name": "同步同事", "username": "synced"}],
        }
        page = self.app.pages["settings"]
        page._render_owners()
        self.pump()
        texts = []
        stack = [page.owner_list]
        while stack:
            widget = stack.pop()
            stack.extend(widget.winfo_children())
            try:
                value = widget.cget("text")
            except Exception:
                value = ""
            if value:
                texts.append(str(value))
        self.assertTrue(any("同步同事" in text for text in texts))
        self.assertTrue(any("组织同步" in text for text in texts))

    def test_task_search_filters_title_owner_and_tags(self):
        page = self.app.pages["tasks"]
        task = model.create_task("杭州数据局重保服务", "保障数据安全", owner="陈宇")
        task["tags"] = ["warning"]
        self.app.store.add_task(task)
        page.search_query = "杭州"
        self.assertEqual([t["id"] for t in page._search_filtered([task])], [task["id"]])
        page.search_query = "预警"
        self.assertEqual([t["id"] for t in page._search_filtered([task])], [task["id"]])
        page.search_query = "不存在"
        self.assertEqual(page._search_filtered([task]), [])

    def test_ai_owner_without_account_defaults_unassigned(self):
        self.assertEqual(self.app.resolve_ai_owner("不存在的王总"), ("待指派", ""))
        self.assertEqual(self.app.resolve_ai_owner("陈宇、李易懋"), ("待指派", ""))
        self.assertEqual(self.app.resolve_ai_owner(""), ("待指派", ""))
        old = model.create_task("AI 旧任务", owner="高彬、陈宇")
        old["source_email_id"] = "e1"
        old = model.normalize_task(old)
        self.assertEqual(old["owner"], "待指派")

    def test_ai_rescan_deleted_task_becomes_pending(self):
        email = self.app.store.emails[0]
        email["analysis"] = {
            "projects": [{
                "title": "已删除项目", "task_id": "missing-task",
                "applied_action": "new", "task_deleted": True,
            }],
        }
        merged, updated = self.app._merge_rescan(email, {
            "projects": [{"title": "已删除项目", "requirement": "新要求"}],
        })
        project = merged["projects"][0]
        self.assertIsNone(project["task_id"])
        self.assertFalse(project["task_deleted"])
        self.assertEqual(updated, 0)

    def test_ai_rescan_updates_linked_task_content(self):
        store = self.app.store
        email = store.emails[0]
        task = model.create_task("杭千高速运维", "旧要求")
        store.add_task(task)
        email["analysis"] = {
            "projects": [{"title": "杭千高速运维", "task_id": task["id"],
                          "requirement": "旧要求", "applied_action": "new"}],
        }
        merged, updated = self.app._merge_rescan(email, {
            "projects": [{"title": "杭千高速运维",
                          "requirement": "【背景】新背景\n【当前进展】新进展",
                          "task_id": None}],
        })
        self.assertEqual(updated, 1)
        self.assertIn("【背景】", task["requirement"])
        self.assertEqual(merged["projects"][0]["task_id"], task["id"])

    def test_ai_project_history_survives_task_delete(self):
        store = self.app.store
        email = store.emails[0]
        task = model.create_task("AI 历史任务", "验证删除后仍保留")
        store.add_task(task)
        email["analysis"] = {
            "analyzed_at": model.iso(model.now()),
            "projects": [{"title": "AI 历史任务", "requirement": "保留记录",
                          "task_id": task["id"], "applied_action": "new"}],
        }
        store.delete_tasks([task["id"]])
        self.assertIsInstance(email.get("analysis"), dict)
        project = email["analysis"]["projects"][0]
        self.assertEqual(project.get("task_id"), task["id"])
        self.assertTrue(project.get("task_deleted"))
        dialog = AIProjectSummaryDialog(self.app, email)
        self.pump()
        self.assertIsNone(dialog._task(project))
        dialog.force_close()

    def test_email_link_and_unlink(self):
        store = self.app.store
        email = store.emails[0]
        first = store.tasks[0]
        second = store.tasks[1]
        self.assertTrue(store.link_email(email["id"], first["id"]))
        self.assertEqual(email["analysis"]["linked_task_id"], first["id"])
        self.assertIn(email["id"], first["email_ids"])
        self.assertTrue(store.link_email(email["id"], second["id"]))
        self.assertNotIn(email["id"], first["email_ids"])
        self.assertIn(email["id"], second["email_ids"])
        self.assertTrue(store.unlink_email(email["id"]))
        self.assertNotIn("linked_task_id", email["analysis"])
        self.assertNotIn(email["id"], second["email_ids"])

    def test_date_picker_drilldown(self):
        editor = TaskEditor(self.app, task=self.app.store.tasks[0])
        self.pump()
        editor.start_field._pick()
        self.pump()
        picker = [w for w in self.app.winfo_children()
                  if isinstance(w, DateTimePicker)][0]
        self.assertEqual(picker.view_mode, "day")
        picker._drill_down()
        self.pump()
        self.assertEqual(picker.view_mode, "month")
        picker._drill_down()
        self.pump()
        self.assertEqual(picker.view_mode, "year")
        picker._choose_year(2027)
        self.pump()
        self.assertEqual(picker.view_mode, "month")
        picker._choose_month(3)
        self.pump()
        self.assertEqual(picker.view_mode, "day")
        self.assertEqual((picker.view_year, picker.view_month), (2027, 3))
        picker.close()
        self.pump()

    def test_ai_settings_save(self):
        page = self.app.pages["settings"]
        page.ai_provider_var.set("DeepSeek")
        page._apply_ai_provider()
        self.assertIn("deepseek", page.ai_endpoint_var.get())
        self.assertEqual(page.ai_model_var.get(), "deepseek-chat")
        page.ai_key_var.set("secret-key")
        page.ai_enabled_toggle.set(True)
        self.assertTrue(page._save_ai(silent=True))
        self.assertTrue(self.app.store.settings()["ai_enabled"])
        self.assertEqual(self.app.store.settings()["ai_provider"], "DeepSeek")
        self.assertEqual(self.app.store.ai_key(), "secret-key")
        self.assertEqual(page.ai_status.cget("text"), "已启用")
        page.ai_enabled_toggle.set(False)
        page._save_ai(silent=True)

    def test_task_view_is_read_only_until_edit(self):
        task = self.app.store.tasks[0]
        self.app.open_task_view(task)
        self.pump()
        views = [w for w in self.app.winfo_children() if isinstance(w, TaskView)]
        self.assertEqual(len(views), 1)
        views[0]._edit()
        self.pump()
        self.assertTrue([w for w in self.app.winfo_children()
                         if isinstance(w, TaskEditor)])

    def test_card_subtask_button_expands(self):
        page = self.app.pages["tasks"]
        page.refresh()
        self.pump()
        card = page.cards[self.app.store.active_tasks()[0]["id"]]
        card._toggle_subtasks()
        self.pump()
        self.assertTrue(card.subtasks_open)
        self.assertTrue(card.subtask_panel.winfo_ismapped())
        card._toggle_subtasks()
        self.pump()
        self.assertFalse(card.subtasks_open)

    def test_subtask_dialog_create_and_edit(self):
        task = self.app.store.tasks[0]
        editor = TaskEditor(self.app, task=task)
        self.pump()
        before = len(task["subtasks"])
        editor._add_subtask()
        self.pump()
        dialogs = [w for w in self.app.winfo_children()
                   if isinstance(w, SubtaskDialog)]
        self.assertEqual(len(dialogs), 1)
        dialogs[0].title_var.set("新增测试子任务")
        dialogs[0].content_text.insert("1.0", "这是子任务的具体内容")
        dialogs[0]._save()
        self.pump()
        self.assertEqual(len(editor.task["subtasks"]), before + 1)
        created = next(s for s in editor.task["subtasks"] if s["title"] == "新增测试子任务")
        self.assertEqual(created["requirement"], "这是子任务的具体内容")
        editor._edit_subtask(editor.task["subtasks"][0]["id"])
        self.pump()
        dialogs = [w for w in self.app.winfo_children()
                   if isinstance(w, SubtaskDialog)]
        self.assertEqual(len(dialogs), 1)
        dialogs[0].title_var.set("编辑测试子任务")
        dialogs[0]._save()
        self.pump()
        self.assertEqual(editor.task["subtasks"][0]["title"], "编辑测试子任务")

    def test_date_filter_does_not_grab_and_freeze(self):
        editor = TaskEditor(self.app, task=self.app.store.tasks[0])
        self.pump()
        editor.start_field._pick()
        self.pump()
        pickers = [w for w in self.app.winfo_children()
                   if isinstance(w, DateTimePicker)]
        self.assertTrue(pickers)
        self.assertIsNone(pickers[0].grab_current())
        pickers[0].close()
        self.pump()
        self.assertTrue(self.app.winfo_exists())

    def test_taskbar_window_style(self):
        import ctypes
        self.app._make_appwindow()
        hwnd = ctypes.windll.user32.GetParent(self.app.winfo_id()) or self.app.winfo_id()
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        self.assertTrue(style & 0x00040000)  # WS_EX_APPWINDOW
        self.assertFalse(style & 0x00000080)  # WS_EX_TOOLWINDOW

    def test_date_range_filter_year_month_day(self):
        page = self.app.pages["tasks"]
        task = self.app.store.active_tasks()[0]
        due = model.parse_dt(task["due"])
        day_start = due.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = due.replace(hour=23, minute=59, second=0, microsecond=0)
        page.apply_date_filter({
            "unit": "day", "label": "test",
            "start": day_start.strftime("%Y-%m-%d %H:%M"),
            "end": day_end.strftime("%Y-%m-%d %H:%M"),
        })
        self.pump()
        self.assertIn(task["id"], page._visible_task_ids())
        page.apply_date_filter({
            "unit": "year", "label": "2000",
            "start": "2000-01-01 00:00", "end": "2000-12-31 23:59",
        })
        self.pump()
        self.assertEqual(page._visible_task_ids(), [])
        page.clear_date_filter()
        self.pump()
        self.assertIsNone(page.date_filter)

    def test_collapsed_edge_drag_and_expand(self):
        self.app.deiconify()
        self.app.geometry("424x960+120+120")
        self.pump()
        self.app.collapse()
        self.pump()
        self.assertTrue(self.app._collapsed)
        self.assertEqual(self.app.winfo_width(), 38)
        start_x = self.app.winfo_x()
        event = type("Event", (), {})()
        event.x_root = start_x + 20
        event.y_root = self.app.winfo_y() + 60
        self.app._edge_press(event)
        event.x_root -= 100
        event.y_root += 40
        self.app._edge_motion(event)
        self.app._edge_release(event)
        self.pump()
        self.assertTrue(self.app._collapsed)
        self.assertLess(self.app.winfo_x(), start_x)
        self.app.expand()
        self.pump()
        self.assertFalse(self.app._collapsed)
        self.assertEqual(self.app.winfo_width(), 424)

        self.app.collapse()
        self.pump()
        click = type("Event", (), {})()
        click.x_root = self.app.winfo_x() + 20
        click.y_root = self.app.winfo_y() + 50
        self.app._edge_press(click)
        self.app._edge_release(click)
        self.pump()
        self.assertFalse(self.app._collapsed)

    def test_card_completion_respects_subtasks(self):
        task = next(t for t in self.app.store.tasks if not t.get("completed"))
        before = len(model.pending_subtasks(task))
        self.assertGreater(before, 0)
        self.app.toggle_task_done(task)
        self.pump()
        self.assertFalse(task.get("completed"))
        for sub in list(task["subtasks"]):
            if not sub.get("done"):
                model.toggle_subtask(task, sub["id"])
        self.app.toggle_task_done(task)
        self.pump()
        self.assertTrue(task.get("completed"))
        self.assertEqual(task["progress"], 100)

    def test_editor_save_and_progress_guard(self):
        task = self.app.store.tasks[2]
        editor = TaskEditor(self.app, task=task)
        self.pump()
        editor.title_var.set("供应商续签（已更新）")
        editor._save_subtask({
            "title": "补充盖章版资质", "start": "2026-11-04T09:00:00",
            "due": "2026-11-06T18:00:00",
            "owner": "周然", "owner_username": "bob", "done": False,
        })
        editor.progress_slider.set_limit(100)
        editor._on_progress(100)
        editor._save()
        self.pump()
        saved = next(t for t in self.app.store.tasks if t["id"] == task["id"])
        self.assertEqual(saved["title"], "供应商续签（已更新）")
        self.assertFalse(saved["completed"])
        self.assertEqual(saved["progress"], 99)
        self.assertTrue(any(s["title"] == "补充盖章版资质" for s in saved["subtasks"]))
        self.assertTrue(any(s.get("owner") == "周然" for s in saved["subtasks"]))
        self.assertTrue(any(s.get("due") == "2026-11-06T18:00:00"
                            for s in saved["subtasks"]))

    def test_mail_update_writes_note_and_progress(self):
        email = self.app.store.emails[0]
        task = next(t for t in self.app.store.tasks if t["title"] == "Q4 品牌发布会方案")
        old_notes = len(task.get("notes", []))
        self.app.apply_mail_update(email)
        self.pump()
        self.assertGreaterEqual(task["progress"], 70)
        self.assertGreater(len(task.get("notes", [])), old_notes)
        self.assertEqual(email["analysis"]["linked_task_id"], task["id"])
        self.assertIn(email["id"], task["email_ids"])

    def test_mail_update_does_not_regress_progress(self):
        email = self.app.store.emails[0]
        task = next(t for t in self.app.store.tasks if t["title"] == "Q4 品牌发布会方案")
        task["progress"] = 85
        self.app.store.save()
        self.app.apply_mail_update(email)
        self.pump()
        self.assertEqual(task["progress"], 85)

    def test_create_task_from_email(self):
        email = next(e for e in self.app.store.emails if "供应商合规材料" in e["subject"])
        before = len(self.app.store.tasks)
        self.app.create_task_from_email(email)
        self.pump()
        editor = self.app._modals[-1]
        self.assertIsInstance(editor, TaskEditor)
        self.assertIn("供应商合规材料", editor.title_var.get())
        editor._save()
        self.pump()
        self.assertEqual(len(self.app.store.tasks), before + 1)
        created = next(t for t in self.app.store.tasks if t.get("source_email_id") == email["id"])
        self.assertIn(email["id"], created["email_ids"])

    def test_collapse_and_expand(self):
        self.app.deiconify()
        self.pump()
        self.app.collapse()
        self.pump()
        self.assertTrue(self.app._collapsed)
        self.assertEqual(self.app.winfo_width(), 38)
        self.app.expand()
        self.pump()
        self.assertFalse(self.app._collapsed)
        self.assertEqual(self.app.winfo_width(), 424)

    def test_settings_save(self):
        self.app.switch_page("settings")
        self.pump()
        page = self.app.pages["settings"]
        page.account_var.set("me@example.com")
        page.password_var.set("app-password")
        page.host_var.set("imap.example.com")
        page.port_var.set("993")
        page.days_var.set("21")
        self.assertTrue(page._collect())
        self.assertEqual(self.app.store.settings()["account"], "me@example.com")
        self.assertEqual(self.app.store.password(), "app-password")
        self.assertEqual(self.app.store.settings()["days"], 21)

    def test_delete_task_via_store(self):
        task = self.app.store.tasks[-1]
        task_id = task["id"]
        self.app.store.delete_task(task_id)
        self.pump()
        self.assertIsNone(self.app.store.task(task_id))

    def test_manage_mode_select_and_delete(self):
        page = self.app.pages["tasks"]
        page.enter_manage()
        self.pump()
        self.assertTrue(page.manage)
        ids = [t["id"] for t in self.app.store.tasks]
        page.toggle_select(ids[0])
        self.assertIn(ids[0], page.selected)
        page.toggle_select_all()
        self.assertEqual(len(page.selected), len(ids))
        page.toggle_select_all()
        self.assertEqual(len(page.selected), 0)
        page.toggle_select(ids[0])
        self.app.delete_tasks([ids[0]])
        self.pump()
        self.assertIsNone(self.app.store.task(ids[0]))
        self.assertNotIn(ids[0], page.selected)

    def test_swipe_left_deletes_after_confirm(self):
        page = self.app.pages["tasks"]
        task = self.app.store.tasks[0]
        card = page.cards[task["id"]]
        calls = []
        self.app.confirm_delete_task = lambda t: calls.append(t["id"])
        event = lambda x: type("E", (), {"x_root": x, "y_root": 100})()
        card._press(event(200))
        card._motion(event(120))
        card._release(event(120))
        self.assertEqual(calls, [task["id"]])

    def test_clear_all_via_page(self):
        page = self.app.pages["tasks"]
        page.enter_manage()
        self.pump()
        self.app.confirm = lambda title, message, ok_text="", on_ok=None, danger=False: on_ok()
        page.clear_all()
        self.pump()
        self.assertEqual(self.app.store.tasks, [])
        self.assertFalse(page.manage)


if __name__ == "__main__":
    unittest.main()

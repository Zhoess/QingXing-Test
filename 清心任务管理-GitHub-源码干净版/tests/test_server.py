# -*- coding: utf-8 -*-
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from taskdock_server.app import build_server


class ServerApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.server, cls.db = build_server("127.0.0.1", 0, cls.temp.name)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        cls.admin = cls.call("POST", "/api/setup", {
            "username": "admin", "password": "admin123", "display_name": "主管理员",
        })[1]
        cls.admin_token = cls.admin["token"]
        cls.alice = cls.call("POST", "/api/admin/users", {
            "username": "alice", "password": "pass123", "display_name": "林夏",
        }, cls.admin_token)[1]["user"]
        cls.bob = cls.call("POST", "/api/admin/users", {
            "username": "bob", "password": "pass123", "display_name": "周然",
        }, cls.admin_token)[1]["user"]
        cls.alice_token = cls.call("POST", "/api/login", {
            "username": "alice", "password": "pass123"})[1]["token"]
        cls.bob_token = cls.call("POST", "/api/login", {
            "username": "bob", "password": "pass123"})[1]["token"]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp.cleanup()

    @classmethod
    def call(cls, method, path, body=None, token=None):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = urllib.request.Request(cls.base + path, data=data, method=method)
        if body is not None:
            request.add_header("Content-Type", "application/json")
        if token:
            request.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def task(self, task_id="t1", title="发布会方案", progress=30):
        return {
            "id": task_id, "title": title, "requirement": "确认舞台与嘉宾",
            "cycle": "一次性", "start": "2026-11-01T09:00:00",
            "due": "2026-11-06T18:00:00", "owner": "林夏",
            "owner_username": "alice",
            "progress": progress, "completed": False,
            "subtasks": [{"id": "s1", "title": "舞台", "done": True}],
            "notes": [], "updated_at": "2026-11-03T10:00:00",
            "created_at": "2026-11-01T09:00:00",
        }

    def test_01_health_and_admin_page(self):
        status, payload = self.call("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        request = urllib.request.Request(self.base + "/admin")
        with urllib.request.urlopen(request, timeout=10) as response:
            html = response.read().decode("utf-8")
        self.assertIn("清心任务管理终端", html)
        request = urllib.request.Request(self.base + "/static/admin.js")
        with urllib.request.urlopen(request, timeout=10) as response:
            js = response.read().decode("utf-8")
        self.assertIn("taskdock_admin_token", js)

    def test_02_auth_and_permissions(self):
        status, payload = self.call("GET", "/api/me", token="bad-token")
        self.assertEqual(status, 401)
        status, _ = self.call("GET", "/api/admin/overview", token=self.alice_token)
        self.assertEqual(status, 403)
        status, payload = self.call("GET", "/api/admin/overview", token=self.admin_token)
        self.assertEqual(status, 200)
        self.assertGreaterEqual(payload["stats"]["users"], 3)

    def test_02b_admin_can_request_online_collection(self):
        status, first = self.call("GET", "/api/collect/status", token=self.alice_token)
        self.assertEqual(status, 200)
        self.assertIn("epoch", first)
        status, _ = self.call("POST", "/api/admin/collect", {}, self.alice_token)
        self.assertEqual(status, 403)
        status, result = self.call("POST", "/api/admin/collect", {}, self.admin_token)
        self.assertEqual(status, 200)
        self.assertGreater(result["epoch"], first["epoch"])
        self.assertGreaterEqual(result["online"], 1)
        status, second = self.call("GET", "/api/collect/status", token=self.alice_token)
        self.assertEqual(status, 200)
        self.assertEqual(second["epoch"], result["epoch"])

    def test_02c_org_scope_same_and_next_level(self):
        status, root = self.call("POST", "/api/admin/org/create",
                                 {"name": "测试事业部"}, self.admin_token)
        self.assertEqual(status, 201)
        root_id = root["unit"]["id"]
        status, child = self.call("POST", "/api/admin/org/create",
                                  {"name": "测试交付组", "parent_id": root_id}, self.admin_token)
        self.assertEqual(status, 201)
        child_id = child["unit"]["id"]
        status, sibling = self.call("POST", "/api/admin/org/create",
                                    {"name": "测试其他事业部"}, self.admin_token)
        self.assertEqual(status, 201)
        sibling_id = sibling["unit"]["id"]
        for user, unit_id in ((self.alice, root_id), (self.bob, child_id)):
            status, _ = self.call("POST", "/api/admin/users/%d/update" % user["id"], {
                "username": user["username"], "display_name": user["display_name"],
                "org_unit_id": unit_id,
            }, self.admin_token)
            self.assertEqual(status, 200)
        status, colleague = self.call("POST", "/api/admin/users", {
            "username": "orgcharlie", "password": "pass123",
            "display_name": "组织测试员", "org_unit_id": sibling_id,
        }, self.admin_token)
        self.assertEqual(status, 201)
        status, payload = self.call("GET", "/api/collab", token=self.alice_token)
        self.assertEqual(status, 200)
        usernames = {item["username"] for item in payload.get("owner_scope") or []}
        self.assertIn("bob", usernames)
        self.assertNotIn("orgcharlie", usernames)
        self.assertNotIn("alice", usernames)
        self.assertEqual(payload.get("org_unit_id"), root_id)

    def test_03_sync_and_aggregation(self):
        status, payload = self.call("POST", "/api/sync", {
            "tasks": [self.task()], "deleted_ids": [],
        }, self.alice_token)
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["tasks"]), 1)
        self.assertEqual(payload["tasks"][0]["owner_username"], "alice")
        self.call("POST", "/api/sync", {
            "tasks": [self.task("t2", "周报", 10)], "deleted_ids": [],
        }, self.bob_token)
        status, overview = self.call("GET", "/api/admin/overview", token=self.admin_token)
        self.assertEqual(status, 200)
        self.assertGreaterEqual(overview["stats"]["tasks"], 2)
        self.assertTrue(any(t["username"] == "alice" for t in overview["tasks"]))

    def test_03b_admin_task_detail_tags_sync(self):
        status, _ = self.call("POST", "/api/admin/tasks/%d/t1/tags" % self.alice["id"],
                              {"tags": ["warning", "follow", "bad"]}, self.admin_token)
        self.assertEqual(status, 200)
        status, overview = self.call("GET", "/api/admin/overview", token=self.admin_token)
        self.assertEqual(status, 200)
        task = next(t for t in overview["tasks"] if t["id"] == "t1")
        self.assertEqual(task["tags"], ["warning", "follow"])
        status, payload = self.call("POST", "/api/sync", {
            "tasks": [], "deleted_ids": [],
        }, self.alice_token)
        self.assertEqual(status, 200)
        synced = next(t for t in payload["tasks"] if t["id"] == "t1")
        self.assertEqual(synced["tags"], ["warning", "follow"])

    def test_03c_admin_task_message_and_client_reply(self):
        status, result = self.call("POST", "/api/admin/messages/send", {
            "task_user_id": self.alice["id"], "task_id": "t1",
            "body": "过来办公室开个会",
        }, self.admin_token)
        self.assertEqual(status, 201)
        self.assertIn("online", result)
        status, heartbeat = self.call("GET", "/api/collect/status", token=self.alice_token)
        self.assertEqual(status, 200)
        messages = heartbeat.get("messages") or []
        self.assertEqual(messages[0]["body"], "过来办公室开个会")
        status, _ = self.call("POST", "/api/messages/reply", {
            "message_id": messages[0]["id"], "body": "收到",
        }, self.alice_token)
        self.assertEqual(status, 201)
        status, history = self.call(
            "GET", "/api/admin/messages?task_user_id=%d&task_id=t1" % self.alice["id"],
            token=self.admin_token)
        self.assertEqual(status, 200)
        self.assertEqual(history["messages"][-1]["body"], "收到")

    def test_03d_message_threads_and_unread(self):
        status, data = self.call("GET", "/api/admin/messages/threads", token=self.admin_token)
        self.assertEqual(status, 200)
        thread = next(t for t in data["threads"] if t["task_id"] == "t1")
        self.assertGreaterEqual(thread["unread"], 1)
        status, _ = self.call("POST", "/api/admin/messages/thread/read", {
            "task_user_id": self.alice["id"], "task_id": "t1",
        }, self.admin_token)
        self.assertEqual(status, 200)
        status, data = self.call("GET", "/api/admin/messages/threads", token=self.admin_token)
        thread = next(t for t in data["threads"] if t["task_id"] == "t1")
        self.assertEqual(thread["unread"], 0)
        status, data = self.call("GET", "/api/messages/threads", token=self.alice_token)
        self.assertEqual(status, 200)
        self.assertTrue(any(t["task_id"] == "t1" for t in data["threads"]))

    def test_03e_message_falls_back_to_task_creator(self):
        status, _ = self.call("POST", "/api/sync", {
            "tasks": [{
                "id": "t_no_owner", "title": "无负责人任务", "requirement": "",
                "owner": "", "owner_username": "", "progress": 0, "completed": False,
                "updated_at": "2026-11-04T10:00:00",
            }],
            "deleted_ids": [],
        }, self.alice_token)
        self.assertEqual(status, 200)
        status, _ = self.call("POST", "/api/admin/messages/send", {
            "task_user_id": self.alice["id"], "task_id": "t_no_owner",
            "body": "请更新进展",
        }, self.admin_token)
        self.assertEqual(status, 201)
        status, history = self.call(
            "GET", "/api/admin/messages?task_user_id=%d&task_id=t_no_owner" % self.alice["id"],
            token=self.admin_token)
        self.assertEqual(status, 200)
        self.assertEqual(history["recipient"]["recipient_kind"], "creator")
        self.assertEqual(history["recipient"]["recipient"]["id"], self.alice["id"])

    def test_03f_lost_state_syncs_to_admin(self):
        status, _ = self.call("POST", "/api/sync", {
            "tasks": [{
                "id": "t_lost", "title": "已流失项目", "requirement": "",
                "owner": "陈宇", "owner_username": "alice", "progress": 100,
                "completed": False, "lost": True, "lost_at": "2026-11-06T10:00:00",
                "lost_reason": "客户预算取消",
                "tags": ["lost"], "updated_at": "2026-11-06T10:00:00",
            }],
            "deleted_ids": [],
        }, self.alice_token)
        self.assertEqual(status, 200)
        status, overview = self.call("GET", "/api/admin/overview", token=self.admin_token)
        self.assertEqual(status, 200)
        task = next(t for t in overview["tasks"] if t["id"] == "t_lost")
        self.assertTrue(task["lost"])
        self.assertEqual(task["lost_at"], "2026-11-06T10:00:00")
        self.assertEqual(task["lost_reason"], "客户预算取消")

    def test_04_friend_and_share_flow(self):
        status, payload = self.call("POST", "/api/friends/request", {
            "username": "bob",
        }, self.alice_token)
        self.assertEqual(status, 201)
        self.assertFalse(payload["auto_accepted"])
        status, collab = self.call("GET", "/api/collab", token=self.bob_token)
        incoming = collab["requests"]["incoming"]
        self.assertTrue(incoming)
        request_id = incoming[0]["id"]
        status, _ = self.call("POST", "/api/friends/respond", {
            "request_id": request_id, "accept": True,
        }, self.bob_token)
        self.assertEqual(status, 200)
        status, collab = self.call("GET", "/api/collab", token=self.alice_token)
        self.assertEqual(collab["friends"][0]["username"], "bob")
        self.assertTrue(any(u["username"] == "bob" for u in collab["directory"]))

        status, result = self.call("POST", "/api/offers/forward", {
            "task_id": "t1", "to_user_id": self.bob["id"],
            "mode": "share", "message": "一起推进",
        }, self.alice_token)
        self.assertEqual(status, 201)
        status, collab = self.call("GET", "/api/collab", token=self.bob_token)
        offer = [o for o in collab["offers"]["inbox"] if o["status"] == "pending"][0]
        status, result = self.call("POST", "/api/offers/respond", {
            "offer_id": offer["id"], "accept": True,
        }, self.bob_token)
        self.assertEqual(status, 200)
        shared = result["task"]
        self.assertEqual(shared["source"], "shared")
        self.assertTrue(shared["share_group_id"])

        # Bob updates shared progress; Alice should see it after sync.
        shared["progress"] = 82
        shared["updated_at"] = (datetime.now() + timedelta(minutes=1)).replace(
            microsecond=0).isoformat()
        self.call("POST", "/api/sync", {"tasks": [shared], "deleted_ids": []}, self.bob_token)
        status, payload = self.call("POST", "/api/sync", {"tasks": [], "deleted_ids": []},
                                    self.alice_token)
        alice_task = next(t for t in payload["tasks"] if t["id"] == "t1")
        self.assertEqual(alice_task["progress"], 82)

        status, overview = self.call("GET", "/api/admin/overview", token=self.admin_token)
        self.assertEqual(status, 200)
        merged = [t for t in overview["tasks"]
                  if t.get("share_group_id") == shared["share_group_id"]]
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["copy_count"], 2)
        status, payload = self.call("POST", "/api/offers/forward", {
            "task_id": "t1", "to_user_id": self.bob["id"],
            "mode": "share", "message": "重复共享",
        }, self.alice_token)
        self.assertEqual(status, 400)
        self.assertIn("已共享", payload["error"])

        status, _ = self.call("POST", "/api/friends/messages/send", {
            "friend_id": self.bob["id"], "body": "这个项目一起看下",
        }, self.alice_token)
        self.assertEqual(status, 201)
        status, chat = self.call("GET", "/api/friends/messages?friend_id=%d" % self.alice["id"],
                                 token=self.bob_token)
        self.assertEqual(status, 200)
        self.assertEqual(chat["messages"][-1]["body"], "这个项目一起看下")
        status, threads = self.call("GET", "/api/admin/messages/threads",
                                    token=self.admin_token)
        self.assertEqual(status, 200)
        self.assertNotIn("这个项目一起看下", json.dumps(threads, ensure_ascii=False))

        status, _ = self.call("POST", "/api/locks/acquire", {"scope": "group:test-share"},
                              self.alice_token)
        self.assertEqual(status, 200)
        status, payload = self.call("POST", "/api/locks/acquire", {"scope": "group:test-share"},
                                    self.bob_token)
        self.assertEqual(status, 409)
        self.assertIn("编辑中", payload["error"])
        self.call("POST", "/api/locks/release", {"scope": "group:test-share"}, self.alice_token)
        status, _ = self.call("POST", "/api/locks/acquire", {"scope": "group:test-share"},
                              self.bob_token)
        self.assertEqual(status, 200)

        shared_scope = "group:%s" % shared["share_group_id"]
        status, lock = self.call("POST", "/api/locks/acquire", {"scope": shared_scope},
                                 self.alice_token)
        self.assertEqual(status, 200)
        self.assertEqual(lock["revision"], 0)
        status, updated = self.call("POST", "/api/tasks/shared/update", {
            "scope": shared_scope, "base_revision": 0,
            "task": {"title": "共享更新标题", "requirement": "新要求",
                     "owner": "陈宇", "owner_username": "bob",
                     "due": "2027-12-01T18:00:00", "progress": 30},
        }, self.alice_token)
        self.assertEqual(status, 200)
        self.assertEqual(updated["revision"], 1)
        self.call("POST", "/api/locks/release", {"scope": shared_scope}, self.alice_token)
        status, lock = self.call("POST", "/api/locks/acquire", {"scope": shared_scope},
                                 self.bob_token)
        self.assertEqual(lock["revision"], 1)
        status, payload = self.call("POST", "/api/tasks/shared/update", {
            "scope": shared_scope, "base_revision": 0,
            "task": {"title": "旧副本覆盖"},
        }, self.bob_token)
        self.assertEqual(status, 409)
        self.assertIn("状态更新", payload["error"])
        self.call("POST", "/api/locks/release", {"scope": shared_scope}, self.bob_token)

    def test_05_transfer_and_archive(self):
        status, _ = self.call("POST", "/api/offers/forward", {
            "task_id": "t2", "to_user_id": self.bob["id"], "mode": "transfer",
        }, self.alice_token)
        # t2 belongs to Bob in this test class's data sequence; Alice must own it.
        if status != 201:
            self.call("POST", "/api/sync", {"tasks": [self.task("t2", "周报", 10)],
                                           "deleted_ids": []}, self.alice_token)
            status, _ = self.call("POST", "/api/offers/forward", {
                "task_id": "t2", "to_user_id": self.bob["id"], "mode": "transfer",
            }, self.alice_token)
        self.assertEqual(status, 201)
        _, collab = self.call("GET", "/api/collab", token=self.bob_token)
        offer = [o for o in collab["offers"]["inbox"] if o["status"] == "pending" and o["mode"] == "transfer"][0]
        status, result = self.call("POST", "/api/offers/respond", {
            "offer_id": offer["id"], "accept": True,
        }, self.bob_token)
        self.assertEqual(status, 200)
        self.assertEqual(result["task"]["source"], "transferred")
        _, payload = self.call("POST", "/api/sync", {"tasks": [], "deleted_ids": []},
                               self.alice_token)
        archived = next(t for t in payload["tasks"] if t["id"] == "t2")
        self.assertTrue(archived["archived"])

    def test_06_delete_and_account_status(self):
        status, payload = self.call("POST", "/api/sync", {
            "tasks": [], "deleted_ids": ["t1"],
        }, self.alice_token)
        self.assertEqual(status, 200)
        self.assertNotIn("t1", [t["id"] for t in payload["tasks"]])
        status, payload = self.call(
            "GET", "/api/admin/messages?task_user_id=%d&task_id=t1" % self.alice["id"],
            token=self.admin_token)
        self.assertEqual(status, 200)
        self.assertTrue(payload["messages"])
        status, _ = self.call("POST", "/api/admin/users/%d/status" % self.bob["id"], {
            "status": "disabled",
        }, self.admin_token)
        self.assertEqual(status, 200)
        status, _ = self.call("POST", "/api/login", {
            "username": "bob", "password": "pass123",
        })
        self.assertEqual(status, 403)

        status, created = self.call("POST", "/api/admin/users", {
            "username": "charlie", "password": "pass123", "display_name": "临时账户",
        }, self.admin_token)
        self.assertEqual(status, 201)
        charlie = created["user"]
        status, updated = self.call("POST", "/api/admin/users/%d/update" % charlie["id"], {
            "username": "charlie2", "display_name": "修改后的账户",
        }, self.admin_token)
        self.assertEqual(status, 200)
        self.assertEqual(updated["user"]["username"], "charlie2")
        status, _ = self.call("POST", "/api/login", {
            "username": "charlie", "password": "pass123",
        })
        self.assertEqual(status, 401)
        status, _ = self.call("POST", "/api/login", {
            "username": "charlie2", "password": "pass123",
        })
        self.assertEqual(status, 200)
        status, _ = self.call("POST", "/api/admin/users/%d/update" % charlie["id"], {
            "username": "alice", "display_name": "冲突",
        }, self.admin_token)
        self.assertEqual(status, 400)
        status, _ = self.call("POST", "/api/admin/users/%d/delete" % charlie["id"], {
            "confirm": "wrong",
        }, self.admin_token)
        self.assertEqual(status, 400)
        status, _ = self.call("POST", "/api/admin/users/%d/delete" % charlie["id"], {
            "confirm": "charlie2",
        }, self.admin_token)
        self.assertEqual(status, 200)
        status, _ = self.call("POST", "/api/login", {
            "username": "charlie2", "password": "pass123",
        })
        self.assertEqual(status, 401)

    def test_07_duplicate_setup_rejected(self):
        status, _ = self.call("POST", "/api/setup", {
            "username": "admin2", "password": "admin123",
        })
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()

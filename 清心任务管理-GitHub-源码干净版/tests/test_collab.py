# -*- coding: utf-8 -*-
import tempfile
import threading
import unittest
from datetime import datetime, timedelta

from taskdock.collab import CollabClient, CollabError
from taskdock.store import Store
from taskdock_server.app import build_server


class CollabClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.server, cls.db = build_server("127.0.0.1", 0, cls.temp.name)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        cls.db.create_user("admin", "admin123", "主管理员", "admin")
        cls.alice_user = cls.db.create_user("alice", "pass123", "林夏", "member")
        cls.bob_user = cls.db.create_user("bob", "pass123", "周然", "member")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp.cleanup()

    def test_login_and_collab(self):
        alice = CollabClient(self.base)
        result = alice.login("alice", "pass123")
        self.assertEqual(result["user"]["username"], "alice")
        alice.token = result["token"]
        collab = alice.collab()
        self.assertEqual(collab["counts"]["friends"], 0)
        with self.assertRaises(CollabError):
            CollabClient(self.base, "bad").collab()

    def test_admin_can_see_all_account_tasks(self):
        admin = CollabClient(self.base)
        login = admin.login("admin", "admin123")
        self.assertEqual(login["user"]["role"], "admin")
        admin.token = login["token"]
        alice = CollabClient(self.base)
        alice.token = alice.login("alice", "pass123")["token"]
        alice.sync([{
            "id": "admin-view-task", "title": "全局可见任务", "requirement": "",
            "cycle": "一次性", "start": "2026-11-03T09:00:00",
            "due": "2026-11-09T18:00:00", "owner": "林夏", "owner_username": "alice",
            "progress": 30, "completed": False, "subtasks": [], "notes": [],
            "updated_at": (datetime.now() + timedelta(minutes=2)).replace(
                microsecond=0).isoformat(), "created_at": "2026-11-03T09:00:00",
        }], [])
        overview = admin.overview()
        self.assertTrue(any(t["id"] == "admin-view-task" for t in overview["tasks"]))
        self.assertGreaterEqual(overview["stats"]["users"], 3)

    def test_share_forward_and_merge(self):
        alice = CollabClient(self.base)
        alice.token = alice.login("alice", "pass123")["token"]
        bob = CollabClient(self.base)
        bob.token = bob.login("bob", "pass123")["token"]

        alice.add_friend("bob")
        requests = bob.collab()["requests"]["incoming"]
        bob.respond_friend(requests[0]["id"], True)

        task = {
            "id": "local-1", "title": "联合方案", "requirement": "完成联调",
            "cycle": "一次性", "start": "2026-11-03T09:00:00",
            "due": "2026-11-09T18:00:00", "owner": "林夏",
            "progress": 20, "completed": False, "subtasks": [],
            "notes": [], "updated_at": "2026-11-03T10:00:00",
            "created_at": "2026-11-03T09:00:00",
        }
        alice.sync([task], [])
        alice.forward_task("local-1", self.bob_user["id"], "share", "一起推进")
        offer = [o for o in bob.collab()["offers"]["inbox"] if o["status"] == "pending"][0]
        accepted = bob.respond_offer(offer["id"], True)["task"]
        self.assertEqual(accepted["source"], "shared")
        self.assertTrue(accepted["share_group_id"])

        accepted["progress"] = 88
        accepted["updated_at"] = (datetime.now() + timedelta(minutes=1)).replace(
            microsecond=0).isoformat()
        bob.sync([accepted], [])
        alice_tasks = alice.sync([], [])["tasks"]
        local = next(t for t in alice_tasks if t["id"] == "local-1")
        self.assertEqual(local["progress"], 88)

    def test_store_merge_and_tombstone(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            store.load()
            store.set_collab_session("token", {"id": 1, "username": "alice"}, "http://x")
            self.assertEqual(store.collab_token(), "token")
            self.assertEqual(store.collab_user()["username"], "alice")
            task = {
                "id": "r1", "title": "远端任务", "requirement": "",
                "cycle": "一次性", "start": "2026-11-03T09:00:00",
                "due": "2026-11-05T18:00:00", "owner": "林夏",
                "progress": 10, "completed": False, "subtasks": [], "notes": [],
                "updated_at": "2026-11-03T10:00:00", "created_at": "2026-11-03T09:00:00",
            }
            added, updated = store.merge_server_tasks([task], [])
            self.assertEqual(added, 1)
            self.assertIsNotNone(store.task("r1"))
            store.delete_tasks(["r1"])
            self.assertIn("r1", store.deleted_task_ids)
            store.merge_server_tasks([task], ["r1"])
            self.assertNotIn("r1", store.deleted_task_ids)
            self.assertIsNone(store.task("r1"))


if __name__ == "__main__":
    unittest.main()

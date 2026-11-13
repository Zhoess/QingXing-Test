# -*- coding: utf-8 -*-
"""SQLite persistence for the TaskDock collaboration server."""

import json
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from .auth import hash_password, new_token, verify_password

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    last_seen_at TEXT,
    org_unit_id INTEGER
);
CREATE TABLE IF NOT EXISTS org_units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    parent_id INTEGER,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id INTEGER NOT NULL,
    to_id INTEGER NOT NULL,
    task_user_id INTEGER,
    task_id TEXT,
    task_title TEXT DEFAULT '',
    thread_key TEXT DEFAULT '',
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_at TEXT
);
CREATE TABLE IF NOT EXISTS task_locks (
    scope TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    user_name TEXT DEFAULT '',
    locked_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS friendships (
    user_id INTEGER NOT NULL,
    friend_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, friend_id)
);
CREATE TABLE IF NOT EXISTS friend_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id INTEGER NOT NULL,
    to_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    responded_at TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
    user_id INTEGER NOT NULL,
    task_id TEXT NOT NULL,
    title TEXT NOT NULL,
    requirement TEXT DEFAULT '',
    cycle TEXT DEFAULT '一次性',
    start TEXT,
    due TEXT,
    owner TEXT DEFAULT '',
    owner_username TEXT DEFAULT '',
    progress INTEGER DEFAULT 0,
    completed INTEGER DEFAULT 0,
    lost INTEGER DEFAULT 0,
    lost_at TEXT,
    lost_reason TEXT DEFAULT '',
    revision INTEGER DEFAULT 0,
    subtasks_json TEXT DEFAULT '[]',
    notes_json TEXT DEFAULT '[]',
    tags_json TEXT DEFAULT '[]',
    share_group_id TEXT,
    source TEXT DEFAULT 'local',
    archived INTEGER DEFAULT 0,
    received_from TEXT,
    transferred_to TEXT,
    updated_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, task_id)
);
CREATE INDEX IF NOT EXISTS idx_tasks_updated ON tasks(user_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_tasks_group ON tasks(share_group_id);
CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id INTEGER NOT NULL,
    to_id INTEGER NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    task_id TEXT NOT NULL,
    task_snapshot TEXT NOT NULL,
    share_group_id TEXT,
    message TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    responded_at TEXT,
    accepted_task_id TEXT
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    action TEXT NOT NULL,
    detail TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
"""


def now_iso():
    return datetime.now().replace(microsecond=0).isoformat()


def _bool(value):
    return 1 if value else 0


def _safe_json(value, fallback):
    try:
        data = json.loads(value) if isinstance(value, str) else value
        return data if data is not None else fallback
    except Exception:
        return fallback


def _merge_title_key(title):
    """Normalize a project title so client-specific suffixes do not split it."""
    text = re.sub(r"[（(【\[].*?[）)】\]]", "", title or "")
    text = re.sub(r"[\s\-—_/·,，。.、:：|]+", "", text)
    for word in ("项目", "服务", "建设", "安全", "数据", "平台", "系统", "工程", "方案", "实施"):
        text = text.replace(word, "")
    return text.lower()


def merge_admin_tasks(tasks):
    """Show one row per shared/related project across different clients."""
    groups = []
    for task in tasks:
        group_id = task.get("share_group_id")
        key = _merge_title_key(task.get("title"))
        target = None
        if group_id:
            target = next((g for g in groups
                           if g["share_group_id"] == group_id), None)
        if target is None and key:
            for group in groups:
                if group["share_group_id"] or not group["key"]:
                    continue
                if any(member["user_id"] == task["user_id"] for member in group["members"]):
                    continue
                ratio = SequenceMatcher(None, key, group["key"]).ratio()
                if key == group["key"] or (ratio >= 0.72 and min(len(key), len(group["key"])) >= 4):
                    target = group
                    break
        if target is None:
            target = {
                "share_group_id": group_id,
                "key": key,
                "members": [],
            }
            groups.append(target)
        target["members"].append(task)
        if key and (not target["key"] or len(key) > len(target["key"])):
            target["key"] = key

    merged = []
    for group in groups:
        members = group["members"]
        canonical = max(members, key=lambda item: (not item.get("archived"), item.get("updated_at") or ""))
        canonical = dict(canonical)
        participants = []
        seen = set()
        for member in members:
            marker = (member.get("user_id"), member.get("task_id"))
            if marker in seen:
                continue
            seen.add(marker)
            participants.append({
                "user_id": member.get("user_id"),
                "task_id": member.get("task_id"),
                "username": member.get("username") or "",
                "display_name": member.get("display_name") or member.get("username") or "",
                "source": member.get("source") or "local",
            })
        canonical["participants"] = participants
        canonical["copy_count"] = len(participants)
        canonical["merged"] = len(participants) > 1
        canonical["share_group_id"] = group["share_group_id"] or canonical.get("share_group_id")
        merged.append(canonical)
    merged.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return merged


class Database(object):
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(str(self.path), timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def init(self):
        with self.connection() as connection:
            connection.executescript(SCHEMA)
            connection.execute("PRAGMA journal_mode=WAL")
            columns = [row["name"] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()]
            if "owner_username" not in columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN owner_username TEXT DEFAULT ''")
            if "tags_json" not in columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN tags_json TEXT DEFAULT '[]'")
            if "lost" not in columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN lost INTEGER DEFAULT 0")
            if "lost_at" not in columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN lost_at TEXT")
            if "lost_reason" not in columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN lost_reason TEXT DEFAULT ''")
            if "revision" not in columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN revision INTEGER DEFAULT 0")
            message_columns = [row["name"] for row in connection.execute(
                "PRAGMA table_info(messages)").fetchall()]
            if "thread_key" not in message_columns:
                connection.execute("ALTER TABLE messages ADD COLUMN thread_key TEXT DEFAULT ''")
            user_columns = [row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()]
            if "org_unit_id" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN org_unit_id INTEGER")

    # ------------------------------------------------------------------ auth
    def setup_required(self):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM users WHERE role='admin'"
            ).fetchone()
            return row["n"] == 0

    def create_user(self, username, password, display_name, role="member", org_unit_id=None):
        username = (username or "").strip().lower()
        display_name = (display_name or username).strip()
        if len(username) < 3 or len(username) > 32:
            raise ValueError("账号需要 3–32 个字符")
        if len(password or "") < 6:
            raise ValueError("密码至少 6 位")
        if org_unit_id and not self.get_org_unit(org_unit_id):
            raise ValueError("组织不存在")
        created = now_iso()
        try:
            with self.connection() as connection:
                cursor = connection.execute(
                    "INSERT INTO users(username, display_name, password_hash, role, created_at, org_unit_id) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (username, display_name, hash_password(password), role, created, org_unit_id or None),
                )
                user_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError("这个账号已经存在")
        return self.get_user(user_id)

    def get_user(self, user_id):
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return self._user(row) if row else None

    def get_user_by_username(self, username):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE username=?", ((username or "").strip().lower(),)
            ).fetchone()
        return self._user(row) if row else None

    @staticmethod
    def _user(row):
        if not row:
            return None
        return {
            "id": row["id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "role": row["role"],
            "status": row["status"],
            "created_at": row["created_at"],
            "last_seen_at": row["last_seen_at"],
            "org_unit_id": row["org_unit_id"] if "org_unit_id" in row.keys() else None,
        }

    def authenticate(self, username, password):
        user = self.get_user_by_username(username)
        if not user:
            return None
        with self.connection() as connection:
            row = connection.execute(
                "SELECT password_hash FROM users WHERE id=?", (user["id"],)
            ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            return None
        if user["status"] != "active":
            raise PermissionError("账号已被停用，请联系管理员")
        self.touch_user(user["id"])
        return user

    def set_password(self, user_id, password):
        if len(password or "") < 6:
            raise ValueError("密码至少 6 位")
        with self.connection() as connection:
            connection.execute(
                "UPDATE users SET password_hash=? WHERE id=?",
                (hash_password(password), user_id),
            )

    def set_status(self, user_id, status):
        if status not in ("active", "disabled"):
            raise ValueError("无效状态")
        with self.connection() as connection:
            connection.execute("UPDATE users SET status=? WHERE id=?", (status, user_id))

    def update_user(self, user_id, username, display_name, org_unit_id=None):
        target = self.get_user(user_id)
        if not target:
            raise ValueError("账号不存在")
        username = (username or "").strip().lower()
        display_name = (display_name or "").strip()
        if len(username) < 3 or len(username) > 32:
            raise ValueError("账号需要 3–32 个字符")
        if not display_name:
            raise ValueError("显示名称不能为空")
        if len(display_name) > 60:
            raise ValueError("显示名称不能超过 60 个字符")
        if org_unit_id and not self.get_org_unit(org_unit_id):
            raise ValueError("组织不存在")
        old_username = target["username"]
        try:
            with self.connection() as connection:
                connection.execute(
                    "UPDATE users SET username=?, display_name=?, org_unit_id=? WHERE id=?",
                    (username, display_name, org_unit_id or None, user_id),
                )
                if username != old_username:
                    # Keep human-facing references consistent with the new login name.
                    connection.execute(
                        "UPDATE tasks SET owner=?, owner_username=?, updated_at=? "
                        "WHERE owner_username=?",
                        (display_name, username, now_iso(), old_username),
                    )
                    connection.execute(
                        "UPDATE tasks SET received_from=? WHERE received_from=?",
                        (username, old_username),
                    )
                    connection.execute(
                        "UPDATE tasks SET transferred_to=? WHERE transferred_to=?",
                        (username, old_username),
                    )
                if display_name != target["display_name"]:
                    connection.execute(
                        "UPDATE tasks SET owner=?, updated_at=? WHERE owner_username=?",
                        (display_name, now_iso(), username),
                    )
        except sqlite3.IntegrityError:
            raise ValueError("这个账号已经存在")
        return self.get_user(user_id)

    def delete_user(self, actor_id, user_id, confirm_username):
        target = self.get_user(user_id)
        if not target:
            raise ValueError("账号不存在")
        if target["id"] == actor_id:
            raise ValueError("不能删除当前登录的管理账号")
        if target["role"] == "admin":
            raise ValueError("主管理账号不能在这里删除")
        if (confirm_username or "").strip().lower() != target["username"]:
            raise ValueError("账号确认不匹配")
        with self.connection() as connection:
            counts = {
                "tasks": connection.execute(
                    "DELETE FROM tasks WHERE user_id=?", (user_id,)
                ).rowcount,
                "offers": connection.execute(
                    "DELETE FROM offers WHERE from_id=? OR to_id=?", (user_id, user_id)
                ).rowcount,
                "friendships": connection.execute(
                    "DELETE FROM friendships WHERE user_id=? OR friend_id=?",
                    (user_id, user_id),
                ).rowcount,
                "requests": connection.execute(
                    "DELETE FROM friend_requests WHERE from_id=? OR to_id=?",
                    (user_id, user_id),
                ).rowcount,
                "sessions": connection.execute(
                    "DELETE FROM sessions WHERE user_id=?", (user_id,)
                ).rowcount,
            }
            connection.execute("DELETE FROM users WHERE id=?", (user_id,))
        return counts

    def touch_user(self, user_id):
        with self.connection() as connection:
            connection.execute(
                "UPDATE users SET last_seen_at=? WHERE id=?", (now_iso(), user_id)
            )

    def online_count(self, seconds=45):
        cutoff = (datetime.now() - timedelta(seconds=seconds)).replace(microsecond=0).isoformat()
        with self.connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM users "
                "WHERE role='member' AND status='active' AND last_seen_at IS NOT NULL "
                "AND last_seen_at >= ?",
                (cutoff,),
            ).fetchone()
        return int(row["n"] if row else 0)

    def create_session(self, user_id, days=30):
        token = new_token()
        created = datetime.now()
        expires = (created + timedelta(days=days)).replace(microsecond=0).isoformat()
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO sessions(token,user_id,created_at,expires_at) VALUES (?,?,?,?)",
                (token, user_id, created.replace(microsecond=0).isoformat(), expires),
            )
        return token

    def user_for_token(self, token):
        if not token:
            return None
        with self.connection() as connection:
            row = connection.execute(
                "SELECT u.*, s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id "
                "WHERE s.token=?",
                (token,),
            ).fetchone()
        if not row:
            return None
        try:
            if datetime.fromisoformat(row["expires_at"]) < datetime.now():
                return None
        except Exception:
            return None
        if row["status"] != "active":
            return None
        self.touch_user(row["id"])
        return self._user(row)

    def logout(self, token):
        with self.connection() as connection:
            connection.execute("DELETE FROM sessions WHERE token=?", (token,))

    # ----------------------------------------------------------------- tasks
    def upsert_task(self, user_id, task):
        """Store a client task snapshot if it is not older than the server copy."""
        task_id = str(task.get("id") or task.get("task_id") or "").strip()
        if not task_id:
            return False
        title = str(task.get("title") or "未命名任务")[:160]
        requirement = str(task.get("requirement") or "")[:4000]
        cycle = str(task.get("cycle") or "一次性")[:40]
        start = str(task.get("start") or "") or None
        due = str(task.get("due") or "") or None
        owner = str(task.get("owner") or "")[:80]
        owner_username = str(task.get("owner_username") or "")[:80]
        try:
            progress = max(0, min(100, int(task.get("progress") or 0)))
        except (TypeError, ValueError):
            progress = 0
        completed = 1 if task.get("completed") else 0
        lost = 1 if task.get("lost") else 0
        if lost:
            completed = 0
        lost_at = str(task.get("lost_at") or "")[:40] or None
        lost_reason = str(task.get("lost_reason") or "").strip()[:500]
        subtasks = task.get("subtasks") if isinstance(task.get("subtasks"), list) else []
        notes = task.get("notes") if isinstance(task.get("notes"), list) else []
        tags = [tag for tag in (task.get("tags") or [])
                if tag in ("warning", "lost", "follow")] if isinstance(task.get("tags"), list) else []
        share_group_id = task.get("share_group_id") or None
        source = str(task.get("source") or "local")[:30]
        archived = 1 if task.get("archived") else 0
        received_from = task.get("received_from") or None
        transferred_to = task.get("transferred_to") or None
        updated_at = str(task.get("updated_at") or now_iso())
        created_at = str(task.get("created_at") or updated_at)
        try:
            revision = max(0, int(task.get("revision") or 0))
        except (TypeError, ValueError):
            revision = 0

        with self.connection() as connection:
            existing = connection.execute(
                "SELECT updated_at, share_group_id, archived, transferred_to, revision FROM tasks "
                "WHERE user_id=? AND task_id=?",
                (user_id, task_id),
            ).fetchone()
            if existing and str(existing["updated_at"] or "") > updated_at:
                return False
            if (existing and existing["share_group_id"]
                    and int(existing["revision"] or 0) > revision):
                # A stale shared copy must sync before it can overwrite newer data.
                return False
            if existing and existing["archived"] and not archived and existing["transferred_to"]:
                # A task transferred away must not be resurrected by a stale client.
                return False
            connection.execute(
                "INSERT INTO tasks(user_id,task_id,title,requirement,cycle,start,due,owner,"
                "owner_username,progress,completed,lost,lost_at,lost_reason,revision,subtasks_json,notes_json,tags_json,share_group_id,source,"
                "archived,received_from,transferred_to,updated_at,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(user_id,task_id) DO UPDATE SET "
                "title=excluded.title, requirement=excluded.requirement, cycle=excluded.cycle, "
                "start=excluded.start, due=excluded.due, owner=excluded.owner, "
                "owner_username=excluded.owner_username, "
                "progress=excluded.progress, completed=excluded.completed, "
                "lost=excluded.lost, lost_at=excluded.lost_at, lost_reason=excluded.lost_reason, "
                "revision=excluded.revision, "
                "subtasks_json=excluded.subtasks_json, notes_json=excluded.notes_json, "
                "tags_json=excluded.tags_json, "
                "share_group_id=excluded.share_group_id, source=excluded.source, "
                "archived=excluded.archived, received_from=excluded.received_from, "
                "transferred_to=excluded.transferred_to, updated_at=excluded.updated_at",
                (user_id, task_id, title, requirement, cycle, start, due, owner,
                 owner_username, progress, completed, lost, lost_at, lost_reason, revision,
                 json.dumps(subtasks, ensure_ascii=False),
                 json.dumps(notes, ensure_ascii=False),
                 json.dumps(tags, ensure_ascii=False), share_group_id, source, archived,
                 received_from, transferred_to, updated_at, created_at),
            )
            group = share_group_id or (existing["share_group_id"] if existing else None)
            if group and (completed or progress):
                # Shared tasks keep progress/subtasks in sync across copies.
                connection.execute(
                    "UPDATE tasks SET progress=?, completed=?, subtasks_json=?, updated_at=? "
                    "WHERE share_group_id=? AND user_id<>?",
                    (progress, completed, json.dumps(subtasks, ensure_ascii=False),
                     updated_at, group, user_id),
                )
        return True

    def upsert_tasks(self, user_id, tasks):
        changed = 0
        for task in tasks or []:
            if isinstance(task, dict) and self.upsert_task(user_id, task):
                changed += 1
        return changed

    def delete_tasks(self, user_id, task_ids):
        ids = [str(task_id) for task_id in task_ids or [] if task_id]
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        with self.connection() as connection:
            cursor = connection.execute(
                "DELETE FROM tasks WHERE user_id=? AND task_id IN (%s)" % placeholders,
                [user_id] + ids,
            )
            return cursor.rowcount

    def get_tasks(self, user_id):
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks WHERE user_id=? ORDER BY updated_at DESC", (user_id,)
            ).fetchall()
        return [self._task(row) for row in rows]

    def get_task(self, user_id, task_id):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE user_id=? AND task_id=?", (user_id, task_id)
            ).fetchone()
        return self._task(row) if row else None

    @staticmethod
    def _task(row):
        return {
            "id": row["task_id"],
            "user_id": row["user_id"],
            "title": row["title"],
            "requirement": row["requirement"],
            "cycle": row["cycle"],
            "start": row["start"],
            "due": row["due"],
            "owner": row["owner"],
            "owner_username": row["owner_username"] if "owner_username" in row.keys() else "",
            "progress": row["progress"],
            "completed": bool(row["completed"]),
            "lost": bool(row["lost"]) if "lost" in row.keys() else False,
            "lost_at": row["lost_at"] if "lost_at" in row.keys() else None,
            "lost_reason": row["lost_reason"] if "lost_reason" in row.keys() else "",
            "revision": int(row["revision"] or 0) if "revision" in row.keys() else 0,
            "subtasks": _safe_json(row["subtasks_json"], []),
            "notes": _safe_json(row["notes_json"], []),
            "tags": _safe_json(row["tags_json"], []) if "tags_json" in row.keys() else [],
            "share_group_id": row["share_group_id"],
            "source": row["source"],
            "archived": bool(row["archived"]),
            "received_from": row["received_from"],
            "transferred_to": row["transferred_to"],
            "updated_at": row["updated_at"],
            "created_at": row["created_at"],
        }

    def archive_task(self, user_id, task_id, transferred_to):
        with self.connection() as connection:
            connection.execute(
                "UPDATE tasks SET archived=1, transferred_to=?, updated_at=? "
                "WHERE user_id=? AND task_id=?",
                (transferred_to, now_iso(), user_id, task_id),
            )

    def set_task_tags(self, user_id, task_id, tags):
        clean = [tag for tag in (tags or [])
                 if tag in ("warning", "lost", "follow")] if isinstance(tags, list) else []
        with self.connection() as connection:
            cursor = connection.execute(
                "UPDATE tasks SET tags_json=?, updated_at=? WHERE user_id=? AND task_id=?",
                (json.dumps(clean, ensure_ascii=False), now_iso(), user_id, task_id),
            )
            if not cursor.rowcount:
                raise ValueError("任务不存在")
        return clean

    # ----------------------------------------------------------------- friends
    def friends(self, user_id):
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT u.* FROM friendships f JOIN users u ON u.id=f.friend_id "
                "WHERE f.user_id=? ORDER BY u.display_name",
                (user_id,),
            ).fetchall()
        return [self._user(row) for row in rows]

    def directory(self):
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT id, username, display_name, role, status FROM users "
                "WHERE status='active' ORDER BY role='admin' DESC, display_name"
            ).fetchall()
        return [dict(row) for row in rows]

    def are_friends(self, user_id, friend_id):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM friendships WHERE user_id=? AND friend_id=?",
                (user_id, friend_id),
            ).fetchone()
        return bool(row)

    def add_friend_request(self, from_id, to_id):
        if from_id == to_id:
            raise ValueError("不能添加自己为好友")
        if self.are_friends(from_id, to_id):
            raise ValueError("你们已经是好友")
        target = self.get_user(to_id)
        if not target or target["status"] != "active":
            raise ValueError("该账号不存在或已停用")
        with self.connection() as connection:
            existing = connection.execute(
                "SELECT id FROM friend_requests WHERE from_id=? AND to_id=? AND status='pending'",
                (from_id, to_id),
            ).fetchone()
            if existing:
                raise ValueError("好友申请已经发送，等待对方处理")
            reverse = connection.execute(
                "SELECT id FROM friend_requests WHERE from_id=? AND to_id=? AND status='pending'",
                (to_id, from_id),
            ).fetchone()
            if reverse:
                # The other side already asked; accept it directly.
                connection.execute(
                    "UPDATE friend_requests SET status='accepted', responded_at=? WHERE id=?",
                    (now_iso(), reverse["id"]),
                )
                self._create_friendship(connection, from_id, to_id)
                return {"auto_accepted": True}
            cursor = connection.execute(
                "INSERT INTO friend_requests(from_id,to_id,status,created_at) "
                "VALUES (?,?,'pending',?)",
                (from_id, to_id, now_iso()),
            )
            request_id = cursor.lastrowid
        return {"auto_accepted": False, "id": request_id}

    @staticmethod
    def _create_friendship(connection, a, b):
        created = now_iso()
        connection.execute(
            "INSERT OR IGNORE INTO friendships(user_id,friend_id,created_at) VALUES (?,?,?)",
            (a, b, created),
        )
        connection.execute(
            "INSERT OR IGNORE INTO friendships(user_id,friend_id,created_at) VALUES (?,?,?)",
            (b, a, created),
        )

    def friend_requests(self, user_id):
        with self.connection() as connection:
            incoming = connection.execute(
                "SELECT r.*, u.display_name, u.username FROM friend_requests r "
                "JOIN users u ON u.id=r.from_id "
                "WHERE r.to_id=? AND r.status='pending' ORDER BY r.created_at DESC",
                (user_id,),
            ).fetchall()
            outgoing = connection.execute(
                "SELECT r.*, u.display_name, u.username FROM friend_requests r "
                "JOIN users u ON u.id=r.to_id "
                "WHERE r.from_id=? AND r.status='pending' ORDER BY r.created_at DESC",
                (user_id,),
            ).fetchall()
        return {
            "incoming": [dict(row) for row in incoming],
            "outgoing": [dict(row) for row in outgoing],
        }

    def respond_friend_request(self, user_id, request_id, accept):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM friend_requests WHERE id=? AND to_id=? AND status='pending'",
                (request_id, user_id),
            ).fetchone()
            if not row:
                raise ValueError("好友申请不存在或已处理")
            status = "accepted" if accept else "declined"
            connection.execute(
                "UPDATE friend_requests SET status=?, responded_at=? WHERE id=?",
                (status, now_iso(), request_id),
            )
            if accept:
                self._create_friendship(connection, row["from_id"], row["to_id"])
        return status

    # ------------------------------------------------------------------ offers
    def create_offer(self, from_id, task_id, to_id, mode, message=""):
        if mode not in ("share", "transfer"):
            raise ValueError("转发方式无效")
        if not self.are_friends(from_id, to_id):
            raise ValueError("只能转发给好友")
        task = self.get_task(from_id, task_id)
        if not task or task["archived"]:
            raise ValueError("任务不存在或已转出")
        snapshot = {
            "title": task["title"],
            "requirement": task["requirement"],
            "cycle": task["cycle"],
            "start": task["start"],
            "due": task["due"],
            "owner": task["owner"],
            "owner_username": task.get("owner_username", ""),
            "progress": task["progress"],
            "subtasks": task["subtasks"],
            "completed": task["completed"],
        }
        with self.connection() as connection:
            pending = connection.execute(
                "SELECT 1 FROM offers WHERE from_id=? AND to_id=? AND task_id=? "
                "AND status='pending' LIMIT 1",
                (from_id, to_id, task_id),
            ).fetchone()
            if pending:
                raise ValueError("该任务已向此好友发送过邀请，请等待对方处理")
            if mode == "share" and task.get("share_group_id"):
                already = connection.execute(
                    "SELECT 1 FROM tasks WHERE user_id=? AND share_group_id=? "
                    "AND archived=0 LIMIT 1",
                    (to_id, task["share_group_id"]),
                ).fetchone()
                if already:
                    raise ValueError("该任务已共享给此好友，请勿重复共享")
            cursor = connection.execute(
                "INSERT INTO offers(from_id,to_id,mode,status,task_id,task_snapshot,"
                "share_group_id,message,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (from_id, to_id, mode, "pending", task_id,
                 json.dumps(snapshot, ensure_ascii=False),
                 task.get("share_group_id"), message[:500], now_iso()),
            )
            return cursor.lastrowid

    def offers_for(self, user_id):
        with self.connection() as connection:
            incoming = connection.execute(
                "SELECT o.*, u.username AS from_username, u.display_name AS from_name "
                "FROM offers o JOIN users u ON u.id=o.from_id "
                "WHERE o.to_id=? ORDER BY o.created_at DESC LIMIT 80",
                (user_id,),
            ).fetchall()
            sent = connection.execute(
                "SELECT o.*, u.username AS to_username, u.display_name AS to_name "
                "FROM offers o JOIN users u ON u.id=o.to_id "
                "WHERE o.from_id=? ORDER BY o.created_at DESC LIMIT 80",
                (user_id,),
            ).fetchall()
        return {
            "inbox": [self._offer(row) for row in incoming],
            "sent": [self._offer(row) for row in sent],
        }

    @staticmethod
    def _offer(row):
        return {
            "id": row["id"],
            "from_id": row["from_id"],
            "to_id": row["to_id"],
            "mode": row["mode"],
            "status": row["status"],
            "task_id": row["task_id"],
            "task": _safe_json(row["task_snapshot"], {}),
            "message": row["message"],
            "created_at": row["created_at"],
            "responded_at": row["responded_at"],
            "accepted_task_id": row["accepted_task_id"],
            "from_username": row["from_username"] if "from_username" in row.keys() else "",
            "from_name": row["from_name"] if "from_name" in row.keys() else "",
            "to_username": row["to_username"] if "to_username" in row.keys() else "",
            "to_name": row["to_name"] if "to_name" in row.keys() else "",
        }

    def respond_offer(self, user_id, offer_id, accept):
        with self.connection() as connection:
            offer = connection.execute(
                "SELECT * FROM offers WHERE id=? AND to_id=? AND status='pending'",
                (offer_id, user_id),
            ).fetchone()
            if not offer:
                raise ValueError("任务邀请不存在或已处理")
            if not accept:
                connection.execute(
                    "UPDATE offers SET status='declined', responded_at=? WHERE id=?",
                    (now_iso(), offer_id),
                )
                return None
            sender_task = connection.execute(
                "SELECT * FROM tasks WHERE user_id=? AND task_id=?",
                (offer["from_id"], offer["task_id"]),
            ).fetchone()
            if not sender_task or sender_task["archived"]:
                raise ValueError("原任务已不存在或已转出")
            recipient = self.get_user(user_id)
            sender = self.get_user(offer["from_id"])
            snapshot = _safe_json(offer["task_snapshot"], {})
            group = offer["share_group_id"]
            if offer["mode"] == "share":
                group = group or ("g_" + secrets.token_hex(8))
                connection.execute(
                    "UPDATE tasks SET share_group_id=? WHERE user_id=? AND task_id=?",
                    (group, offer["from_id"], offer["task_id"]),
                )
            new_task_id = "t_" + secrets.token_hex(8)
            timestamp = now_iso()
            owner_name = recipient["display_name"] if recipient else ""
            source = "shared" if offer["mode"] == "share" else "transferred"
            connection.execute(
                "INSERT INTO tasks(user_id,task_id,title,requirement,cycle,start,due,owner,"
                "owner_username,progress,completed,subtasks_json,notes_json,share_group_id,source,"
                "archived,received_from,transferred_to,updated_at,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,NULL,?,?)",
                (user_id, new_task_id, snapshot.get("title", "共享任务"),
                 snapshot.get("requirement", ""), snapshot.get("cycle", "一次性"),
                 snapshot.get("start"), snapshot.get("due"), owner_name,
                 recipient["username"] if recipient else "",
                 int(snapshot.get("progress") or 0),
                 1 if snapshot.get("completed") else 0,
                 json.dumps(snapshot.get("subtasks") or [], ensure_ascii=False), "[]",
                 group, source, sender["username"] if sender else "", timestamp, timestamp),
            )
            if offer["mode"] == "transfer":
                connection.execute(
                    "UPDATE tasks SET archived=1, transferred_to=?, updated_at=? "
                    "WHERE user_id=? AND task_id=?",
                    (recipient["username"] if recipient else "", timestamp,
                     offer["from_id"], offer["task_id"]),
                )
            connection.execute(
                "UPDATE offers SET status='accepted', responded_at=?, accepted_task_id=? "
                "WHERE id=?",
                (timestamp, new_task_id, offer_id),
            )
        return self.get_task(user_id, new_task_id)

    # ------------------------------------------------------------------- stats
    # ---------------------------------------------------------------- org tree
    def list_org_units(self):
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM org_units ORDER BY sort_order, name"
            ).fetchall()
            counts = {
                row["org_unit_id"]: row["n"]
                for row in connection.execute(
                    "SELECT org_unit_id, COUNT(*) AS n FROM users "
                    "WHERE org_unit_id IS NOT NULL GROUP BY org_unit_id"
                ).fetchall()
            }
        units = []
        for row in rows:
            units.append({
                "id": row["id"],
                "name": row["name"],
                "parent_id": row["parent_id"],
                "sort_order": row["sort_order"],
                "member_count": counts.get(row["id"], 0),
            })
        return units

    def get_org_unit(self, unit_id):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM org_units WHERE id=?", (unit_id,)
            ).fetchone()
        return dict(row) if row else None

    def create_org_unit(self, name, parent_id=None):
        name = (name or "").strip()
        if not name or len(name) > 60:
            raise ValueError("组织名称需要 1–60 个字符")
        if parent_id and not self.get_org_unit(parent_id):
            raise ValueError("上级组织不存在")
        with self.connection() as connection:
            cursor = connection.execute(
                "INSERT INTO org_units(name, parent_id, created_at) VALUES (?, ?, ?)",
                (name, parent_id or None, now_iso()),
            )
        return self.get_org_unit(cursor.lastrowid)

    def update_org_unit(self, unit_id, name, parent_id=None):
        unit = self.get_org_unit(unit_id)
        if not unit:
            raise ValueError("组织不存在")
        name = (name or "").strip()
        if not name or len(name) > 60:
            raise ValueError("组织名称需要 1–60 个字符")
        parent_id = parent_id or None
        if parent_id:
            if not self.get_org_unit(parent_id):
                raise ValueError("上级组织不存在")
            cursor = parent_id
            while cursor:
                if cursor == unit_id:
                    raise ValueError("不能把组织移动到自己或下级组织")
                parent = self.get_org_unit(cursor)
                cursor = parent.get("parent_id") if parent else None
        with self.connection() as connection:
            connection.execute(
                "UPDATE org_units SET name=?, parent_id=? WHERE id=?",
                (name, parent_id, unit_id),
            )
        return self.get_org_unit(unit_id)

    def delete_org_unit(self, unit_id):
        if not self.get_org_unit(unit_id):
            return False
        with self.connection() as connection:
            children = connection.execute(
                "SELECT COUNT(*) AS n FROM org_units WHERE parent_id=?", (unit_id,)
            ).fetchone()["n"]
            members = connection.execute(
                "SELECT COUNT(*) AS n FROM users WHERE org_unit_id=?", (unit_id,)
            ).fetchone()["n"]
            if children:
                raise ValueError("请先删除或移动下级组织")
            if members:
                raise ValueError("请先把该组织的成员移到其它组织")
            connection.execute("DELETE FROM org_units WHERE id=?", (unit_id,))
        return True

    def owner_scope(self, user_id):
        user = self.get_user(user_id)
        if not user or not user.get("org_unit_id"):
            return []
        units = self.list_org_units()
        by_id = {unit["id"]: unit for unit in units}
        root = user["org_unit_id"]
        ids = {root}
        ids.update(unit["id"] for unit in units if unit.get("parent_id") == root)
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT id, username, display_name, org_unit_id FROM users "
                "WHERE status='active' AND org_unit_id IS NOT NULL AND id<>? "
                "ORDER BY display_name",
                (user_id,),
            ).fetchall()
        result = []
        for row in rows:
            if row["org_unit_id"] in ids:
                result.append({
                    "id": row["id"],
                    "username": row["username"],
                    "display_name": row["display_name"],
                    "org_unit_id": row["org_unit_id"],
                    "org_unit_name": (by_id.get(row["org_unit_id"]) or {}).get("name", ""),
                })
        return result

    # ---------------------------------------------------------------- messages
    def task_recipient(self, task_user_id, task_id):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT task_id, title, owner, owner_username FROM tasks "
                "WHERE user_id=? AND task_id=?",
                (task_user_id, task_id),
            ).fetchone()
        if not row:
            return None
        recipient = None
        recipient_kind = "creator"
        if row["owner_username"]:
            recipient = self.get_user_by_username(row["owner_username"])
            if recipient:
                recipient_kind = "owner"
        if not recipient:
            # Task bucket owner is the account that created/received the task.
            recipient = self.get_user(task_user_id)
            recipient_kind = "creator"
        if not recipient or recipient["role"] == "admin":
            return None
        return {
            "task_id": row["task_id"],
            "task_title": row["title"],
            "owner": row["owner"],
            "recipient": recipient,
            "recipient_kind": recipient_kind,
        }

    def send_message(self, from_id, to_id, body, task_user_id=None, task_id=None,
                     task_title="", thread_key=""):
        body = (body or "").strip()
        if not body:
            raise ValueError("消息不能为空")
        if len(body) > 500:
            body = body[:500]
        created = now_iso()
        with self.connection() as connection:
            cursor = connection.execute(
                "INSERT INTO messages(from_id,to_id,task_user_id,task_id,task_title,thread_key,body,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (from_id, to_id, task_user_id, task_id, (task_title or "")[:200],
                 (thread_key or "")[:120], body, created),
            )
            message_id = cursor.lastrowid
        return message_id

    @staticmethod
    def friend_thread_key(a, b):
        return ":".join(str(item) for item in sorted((int(a), int(b))))

    def friend_messages(self, user_id, friend_id, limit=200):
        thread_key = self.friend_thread_key(user_id, friend_id)
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT m.*, fu.display_name AS from_name, fu.username AS from_username "
                "FROM messages m JOIN users fu ON fu.id=m.from_id "
                "WHERE m.thread_key=? ORDER BY m.id ASC LIMIT ?",
                (thread_key, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def acquire_task_lock(self, scope, user_id, user_name, ttl=600):
        scope = (scope or "").strip()[:200]
        if not scope:
            raise ValueError("缺少任务范围")
        now = datetime.now()
        expires = now + timedelta(seconds=ttl)
        with self.connection() as connection:
            connection.execute("DELETE FROM task_locks WHERE expires_at < ?", (now_iso(),))
            revision_row = connection.execute(
                "SELECT COALESCE(MAX(revision), 0) AS revision FROM tasks "
                "WHERE share_group_id=?", (scope[6:] if scope.startswith("group:") else "",),
            ).fetchone()
            revision = int(revision_row["revision"] or 0) if revision_row else 0
            row = connection.execute(
                "SELECT * FROM task_locks WHERE scope=?", (scope,)
            ).fetchone()
            if row and row["user_id"] != user_id:
                return False, row["user_name"] or "其他账户", revision
            connection.execute(
                "INSERT INTO task_locks(scope,user_id,user_name,locked_at,expires_at) "
                "VALUES (?,?,?,?,?) ON CONFLICT(scope) DO UPDATE SET "
                "user_id=excluded.user_id, user_name=excluded.user_name, "
                "locked_at=excluded.locked_at, expires_at=excluded.expires_at",
                (scope, user_id, (user_name or "")[:80], now_iso(),
                 expires.isoformat(timespec="seconds")),
            )
        return True, "", revision

    def release_task_lock(self, scope, user_id):
        with self.connection() as connection:
            count = connection.execute(
                "DELETE FROM task_locks WHERE scope=? AND user_id=?",
                ((scope or "").strip()[:200], user_id),
            ).rowcount
        return count

    def shared_task_revision(self, scope):
        scope = (scope or "").strip()
        if not scope.startswith("group:"):
            return 0
        group = scope[6:]
        with self.connection() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(revision), 0) AS revision FROM tasks "
                "WHERE share_group_id=?", (group,),
            ).fetchone()
        return int(row["revision"] or 0) if row else 0

    def update_shared_task(self, user_id, scope, task, base_revision):
        scope = (scope or "").strip()[:200]
        if not scope.startswith("group:"):
            raise ValueError("不是共享任务")
        group = scope[6:]
        with self.connection() as connection:
            lock = connection.execute(
                "SELECT user_id FROM task_locks WHERE scope=?", (scope,)
            ).fetchone()
            if not lock or lock["user_id"] != user_id:
                raise ValueError("任务编辑锁已失效，请重新进入编辑")
            row = connection.execute(
                "SELECT COALESCE(MAX(revision), 0) AS revision, COUNT(*) AS total "
                "FROM tasks WHERE share_group_id=?", (group,),
            ).fetchone()
            if not row or not row["total"]:
                raise ValueError("共享任务不存在")
            current = int(row["revision"] or 0)
            if int(base_revision or 0) != current:
                raise ValueError("任务已更新，请先点「状态更新」后再编辑")
            new_revision = current + 1
            timestamp = now_iso()
            title = str(task.get("title") or "未命名任务")[:160]
            requirement = str(task.get("requirement") or "")[:4000]
            cycle = str(task.get("cycle") or "一次性")[:40]
            start = str(task.get("start") or "") or None
            due = str(task.get("due") or "") or None
            owner = str(task.get("owner") or "")[:80]
            owner_username = str(task.get("owner_username") or "")[:80]
            try:
                progress = max(0, min(100, int(task.get("progress") or 0)))
            except (TypeError, ValueError):
                progress = 0
            lost = 1 if task.get("lost") else 0
            completed = 1 if task.get("completed") and not lost else 0
            lost_at = str(task.get("lost_at") or "")[:40] or None
            lost_reason = str(task.get("lost_reason") or "").strip()[:500]
            subtasks = task.get("subtasks") if isinstance(task.get("subtasks"), list) else []
            notes = task.get("notes") if isinstance(task.get("notes"), list) else []
            tags = [tag for tag in (task.get("tags") or [])
                    if tag in ("warning", "lost", "follow")] if isinstance(task.get("tags"), list) else []
            connection.execute(
                "UPDATE tasks SET title=?, requirement=?, cycle=?, start=?, due=?, owner=?, "
                "owner_username=?, progress=?, completed=?, lost=?, lost_at=?, lost_reason=?, "
                "subtasks_json=?, notes_json=?, tags_json=?, revision=?, updated_at=? "
                "WHERE share_group_id=?",
                (title, requirement, cycle, start, due, owner, owner_username, progress,
                 completed, lost, lost_at, lost_reason,
                 json.dumps(subtasks, ensure_ascii=False),
                 json.dumps(notes, ensure_ascii=False),
                 json.dumps(tags, ensure_ascii=False), new_revision, timestamp, group),
            )
        return new_revision, timestamp

    def task_messages(self, task_user_id, task_id, limit=100):
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT m.*, fu.display_name AS from_name, fu.username AS from_username, "
                "tu.display_name AS to_name, tu.username AS to_username "
                "FROM messages m JOIN users fu ON fu.id=m.from_id "
                "JOIN users tu ON tu.id=m.to_id "
                "WHERE m.task_user_id=? AND m.task_id=? ORDER BY m.id ASC LIMIT ?",
                (task_user_id, task_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def unread_messages(self, user_id, limit=5):
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT m.*, fu.display_name AS from_name, fu.username AS from_username "
                "FROM messages m JOIN users fu ON fu.id=m.from_id "
                "WHERE m.to_id=? AND m.read_at IS NULL AND (m.thread_key='' OR m.thread_key IS NULL) "
                "ORDER BY m.id ASC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_messages_read(self, user_id, message_ids):
        ids = [int(item) for item in (message_ids or []) if str(item).isdigit()]
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        with self.connection() as connection:
            return connection.execute(
                "UPDATE messages SET read_at=? WHERE to_id=? AND id IN (%s) AND read_at IS NULL"
                % placeholders,
                tuple([now_iso(), user_id] + ids),
            ).rowcount

    def message(self, message_id):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM messages WHERE id=?", (message_id,)
            ).fetchone()
        return dict(row) if row else None

    def message_threads(self, viewer_id, admin=False):
        with self.connection() as connection:
            if admin:
                rows = connection.execute(
                    "SELECT m.*, fu.display_name AS from_name, fu.username AS from_username, "
                    "tu.display_name AS to_name, tu.username AS to_username "
                    "FROM messages m JOIN users fu ON fu.id=m.from_id "
                    "JOIN users tu ON tu.id=m.to_id "
                    "WHERE (m.thread_key='' OR m.thread_key IS NULL) "
                    "ORDER BY m.id ASC"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT m.*, fu.display_name AS from_name, fu.username AS from_username, "
                    "tu.display_name AS to_name, tu.username AS to_username "
                    "FROM messages m JOIN users fu ON fu.id=m.from_id "
                    "JOIN users tu ON tu.id=m.to_id "
                    "WHERE (m.from_id=? OR m.to_id=?) "
                    "AND (m.thread_key='' OR m.thread_key IS NULL) ORDER BY m.id ASC",
                    (viewer_id, viewer_id),
                ).fetchall()
        groups = {}
        for row in rows:
            key = (row["task_user_id"], row["task_id"] or row["thread_key"] or "")
            group = groups.setdefault(key, {
                "task_user_id": row["task_user_id"],
                "task_id": row["task_id"],
                "task_title": row["task_title"] or "",
                "messages": [],
                "unread": 0,
            })
            group["messages"].append(dict(row))
            if row["to_id"] == viewer_id and not row["read_at"]:
                group["unread"] += 1
        threads = []
        for group in groups.values():
            latest = group["messages"][-1]
            group["latest_body"] = latest.get("body") or ""
            group["latest_at"] = latest.get("created_at") or ""
            group["latest_from"] = latest.get("from_name") or latest.get("from_username") or ""
            group["from_name"] = latest.get("from_name") or ""
            group["to_name"] = latest.get("to_name") or ""
            threads.append(group)
        threads.sort(key=lambda item: item.get("latest_at") or "", reverse=True)
        return {
            "threads": threads,
            "unread": sum(item["unread"] for item in threads),
        }

    def mark_thread_read(self, viewer_id, task_user_id, task_id):
        with self.connection() as connection:
            return connection.execute(
                "UPDATE messages SET read_at=? WHERE to_id=? AND "
                "COALESCE(task_user_id,0)=COALESCE(?,0) AND COALESCE(task_id,'')=COALESCE(?,'') "
                "AND read_at IS NULL",
                (now_iso(), viewer_id, task_user_id, task_id),
            ).rowcount

    def user_online(self, user_id, seconds=45):
        user = self.get_user(user_id)
        if not user or not user.get("last_seen_at"):
            return False
        seen = _parse_dt(user["last_seen_at"])
        return bool(seen and (datetime.now() - seen).total_seconds() <= seconds)

    def admin_overview(self):
        users = self.list_users()
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT t.*, u.username, u.display_name, u.role AS user_role "
                "FROM tasks t JOIN users u ON u.id=t.user_id "
                "ORDER BY t.updated_at DESC"
            ).fetchall()
            pending_offers = connection.execute(
                "SELECT COUNT(*) AS n FROM offers WHERE status='pending'"
            ).fetchone()["n"]
        tasks = []
        for row in rows:
            task = self._task(row)
            task["username"] = row["username"]
            task["display_name"] = row["display_name"]
            task["user_role"] = row["user_role"]
            tasks.append(task)
        tasks = merge_admin_tasks(tasks)
        now = datetime.now()
        active = [t for t in tasks if not t["archived"]]
        done = [t for t in active if t["completed"]]
        lost_tasks = [t for t in active if t["lost"]]
        overdue = []
        due_soon = []
        stalled = []
        for task in active:
            if task["completed"] or task["lost"]:
                continue
            due = _parse_dt(task.get("due"))
            if due and due < now:
                overdue.append(task)
            if due and now <= due <= now + timedelta(days=3):
                due_soon.append(task)
            updated = _parse_dt(task.get("updated_at"))
            if updated and updated < now - timedelta(days=7):
                stalled.append(task)
        completion_denominator = len(active) - len(lost_tasks)
        completion = int(round(len(done) * 100.0 / completion_denominator)) if completion_denominator else 0
        workload = {}
        for task in active:
            if task["completed"] or task["lost"]:
                continue
            key = task["display_name"] or task["username"]
            workload[key] = workload.get(key, 0) + 1
        insights = []
        if lost_tasks:
            insights.append({
                "tone": "danger",
                "title": "%d 个任务已流失" % len(lost_tasks),
                "detail": "已作为终态沉底：" + "、".join(t["title"] for t in lost_tasks[:3]),
            })
        if overdue:
            insights.append({
                "tone": "danger",
                "title": "%d 个任务已逾期" % len(overdue),
                "detail": "优先关注：" + "、".join(t["title"] for t in overdue[:3]),
            })
        if due_soon:
            insights.append({
                "tone": "warn",
                "title": "%d 个任务将在 3 天内到期" % len(due_soon),
                "detail": "、".join(t["title"] for t in due_soon[:3]),
            })
        if stalled:
            insights.append({
                "tone": "muted",
                "title": "%d 个任务超过 7 天未更新" % len(stalled),
                "detail": "建议确认是否仍在推进：" + "、".join(t["title"] for t in stalled[:3]),
            })
        if workload:
            top_name = max(workload, key=workload.get)
            top_count = workload[top_name]
            avg = sum(workload.values()) / float(len(workload))
            if top_count >= max(3, avg * 1.8):
                insights.append({
                    "tone": "warn",
                    "title": "%s 的任务负载偏高" % top_name,
                    "detail": "当前未完成任务 %d 个，建议协调或转交。" % top_count,
                })
        if not insights:
            insights.append({
                "tone": "good",
                "title": "当前节奏健康",
                "detail": "没有明显的逾期、临期或停滞任务。",
            })
        return {
            "stats": {
                "users": len(users),
                "active_users": len([u for u in users if u["status"] == "active"]),
                "online": self.online_count(),
                "tasks": len(active),
                "completed": len(done),
                "lost": len(lost_tasks),
                "overdue": len(overdue),
                "due_soon": len(due_soon),
                "shared": len([t for t in active if t["source"] != "local"]),
                "pending_offers": pending_offers,
                "completion": completion,
            },
            "users": users,
            "org_units": self.list_org_units(),
            "tasks": tasks,
            "workload": sorted(
                [{"name": key, "count": value} for key, value in workload.items()],
                key=lambda item: -item["count"],
            ),
            "insights": insights,
            "generated_at": now_iso(),
        }

    def list_users(self):
        with self.connection() as connection:
            users = connection.execute(
                "SELECT * FROM users ORDER BY role='admin' DESC, created_at"
            ).fetchall()
            counts = connection.execute(
                "SELECT user_id, COUNT(*) AS n, "
                "SUM(CASE WHEN completed=0 AND archived=0 THEN 1 ELSE 0 END) AS open_n, "
                "SUM(CASE WHEN completed=1 AND archived=0 THEN 1 ELSE 0 END) AS done_n "
                "FROM tasks GROUP BY user_id"
            ).fetchall()
        by_user = {row["user_id"]: row for row in counts}
        org_names = {unit["id"]: unit["name"] for unit in self.list_org_units()}
        result = []
        for row in users:
            user = self._user(row)
            stat = by_user.get(user["id"])
            user["tasks"] = stat["n"] if stat else 0
            user["open_tasks"] = stat["open_n"] if stat else 0
            user["completed_tasks"] = stat["done_n"] if stat else 0
            user["org_unit_name"] = org_names.get(user.get("org_unit_id"), "")
            result.append(user)
        return result

    def audit(self, actor_id, action, detail=""):
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO audit(actor_id,action,detail,created_at) VALUES (?,?,?,?)",
                (actor_id, action, detail[:500], now_iso()),
            )


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", ""))
    except Exception:
        return None

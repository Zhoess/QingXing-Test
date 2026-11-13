# -*- coding: utf-8 -*-
"""Local JSON storage with atomic writes and Windows DPAPI password protection."""

import base64
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from . import demo, model


def default_data_dir():
    override = os.environ.get("TASKDOCK_DATA_DIR")
    if override:
        return Path(override)
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "TaskDock"


def _empty_data():
    return {
        "version": 1,
        "tasks": [],
        "emails": [],
        "deleted_tasks": [],
        "settings": demo.default_settings(),
    }


def _protect(text):
    if not text:
        return ""
    try:
        import win32crypt

        blob = win32crypt.CryptProtectData(
            text.encode("utf-8"), "TaskDock secret", None, None, None, 0
        )
        return "dpapi:" + base64.b64encode(blob).decode("ascii")
    except Exception:
        # Keep the app usable on non-Windows/dev machines, but label it honestly.
        return "b64:" + base64.b64encode(text.encode("utf-8")).decode("ascii")


def _unprotect(value):
    if not value:
        return ""
    try:
        if value.startswith("dpapi:"):
            import win32crypt

            blob = base64.b64decode(value.split(":", 1)[1])
            _description, raw = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
            return raw.decode("utf-8")
        if value.startswith("b64:"):
            return base64.b64decode(value.split(":", 1)[1]).decode("utf-8")
    except Exception:
        return ""
    return ""


class Store(object):
    def __init__(self, directory=None, seed=False):
        self.directory = Path(directory) if directory else default_data_dir()
        self.path = self.directory / "data.json"
        self.backup_path = self.directory / "data.backup.json"
        self.seed = seed
        self.data = _empty_data()

    def load(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.data = demo.seed_data() if self.seed else _empty_data()
            self.save()
            return self.data
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            # Keep the broken file for inspection, then start clean.
            try:
                shutil.copy2(str(self.path), str(self.path.with_suffix(".broken.json")))
            except Exception:
                pass
            self.data = demo.seed_data() if self.seed else _empty_data()
            self.save()
            return self.data

        base = _empty_data()
        if not isinstance(data, dict):
            data = base
        settings = dict(base["settings"])
        settings.update(data.get("settings") or {})
        migrated_host = settings.get("imap_host") in ("", "imap.dingtalk.com")
        if migrated_host:
            settings["imap_host"] = "imap.em.dingtalk.com"
        data["settings"] = settings
        data["tasks"] = [model.normalize_task(t) for t in (data.get("tasks") or []) if isinstance(t, dict)]
        data["emails"] = [self._normalize_email(e) for e in (data.get("emails") or []) if isinstance(e, dict)]
        data["deleted_tasks"] = [str(x) for x in (data.get("deleted_tasks") or []) if x]
        data.setdefault("version", 1)
        self.data = data
        if migrated_host:
            self.save()
        return data

    def _normalize_email(self, email):
        email.setdefault("id", model.new_id("m"))
        email.setdefault("uid", email["id"])
        email.setdefault("subject", "（无主题）")
        email.setdefault("sender", "未知发件人")
        email.setdefault("sender_email", "")
        email.setdefault("date", model.iso(model.now()))
        email.setdefault("body", "")
        email.setdefault("snippet", "")
        email.setdefault("read", False)
        email.setdefault("analysis", None)
        email.setdefault("demo", False)
        email.setdefault("folder", "INBOX")
        return email

    def save(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                shutil.copy2(str(self.path), str(self.backup_path))
            except Exception:
                pass
        tmp = self.path.with_suffix(".tmp")
        payload = json.dumps(self.data, ensure_ascii=False, indent=2)
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except Exception:
                pass
        os.replace(str(tmp), str(self.path))

    # ---------------------------------------------------------------- settings
    def settings(self):
        return self.data.setdefault("settings", demo.default_settings())

    def set_setting(self, key, value):
        self.settings()[key] = value
        self.save()

    def owner_directory(self):
        items = self.settings().setdefault("owner_directory", [])
        result = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = (item.get("name") or "").strip()
            if not name:
                continue
            if not item.get("id"):
                item["id"] = model.new_id("o")
            result.append(item)
        if result != items:
            self.settings()["owner_directory"] = result
        return result

    def add_owner(self, name, username="", active=True):
        name = (name or "").strip()
        username = (username or "").strip()
        if not name:
            raise ValueError("负责人姓名不能为空")
        if any(char in name for char in "、,，/;；"):
            raise ValueError("负责人只能填写一个人")
        items = self.owner_directory()
        if any((item.get("name") or "").strip() == name for item in items):
            raise ValueError("负责人已存在")
        item = {
            "id": model.new_id("o"),
            "name": name,
            "username": username,
            "active": bool(active),
        }
        items.append(item)
        self.settings()["owner_directory"] = items
        self.save()
        return item

    def update_owner(self, owner_id, name, username="", active=True):
        name = (name or "").strip()
        username = (username or "").strip()
        if not name:
            raise ValueError("负责人姓名不能为空")
        if any(char in name for char in "、,，/;；"):
            raise ValueError("负责人只能填写一个人")
        items = self.owner_directory()
        for item in items:
            if item.get("id") == owner_id:
                if any(other.get("id") != owner_id
                       and (other.get("name") or "").strip() == name for other in items):
                    raise ValueError("负责人已存在")
                item["name"] = name
                item["username"] = username
                item["active"] = bool(active)
                self.settings()["owner_directory"] = items
                self.save()
                return item
        raise ValueError("负责人不存在")

    def delete_owner(self, owner_id):
        items = self.owner_directory()
        remaining = [item for item in items if item.get("id") != owner_id]
        if len(remaining) == len(items):
            return False
        self.settings()["owner_directory"] = remaining
        self.save()
        return True

    def set_password(self, plain):
        self.settings()["mail_password"] = _protect(plain)
        self.save()

    def password(self):
        return _unprotect(self.settings().get("mail_password", ""))

    def has_password(self):
        return bool(self.settings().get("mail_password"))

    def set_ai_key(self, plain):
        self.settings()["ai_api_key"] = _protect(plain)
        self.save()

    def ai_key(self):
        return _unprotect(self.settings().get("ai_api_key", ""))

    def has_ai_key(self):
        return bool(self.settings().get("ai_api_key"))

    # ------------------------------------------------------------- collaboration
    def set_collab_session(self, token, user, server):
        settings = self.settings()
        settings["collab_server"] = server
        settings["collab_token"] = _protect(token)
        settings["collab_user_id"] = user.get("id")
        settings["collab_username"] = user.get("username", "")
        settings["collab_display_name"] = user.get("display_name", "")
        settings["collab_role"] = user.get("role", "member")
        self.save()

    def collab_token(self):
        return _unprotect(self.settings().get("collab_token", ""))

    def collab_user(self):
        settings = self.settings()
        if not settings.get("collab_user_id") or not settings.get("collab_username"):
            return None
        return {
            "id": settings.get("collab_user_id"),
            "username": settings.get("collab_username"),
            "display_name": settings.get("collab_display_name") or settings.get("collab_username"),
            "role": settings.get("collab_role") or "member",
        }

    def clear_collab_session(self):
        settings = self.settings()
        for key in ("collab_token", "collab_user_id", "collab_username",
                    "collab_display_name", "collab_role", "collab_last_sync"):
            settings[key] = "" if key != "collab_user_id" else None
        self.save()

    # -------------------------------------------------------------------- data
    @property
    def tasks(self):
        return self.data.setdefault("tasks", [])

    @property
    def emails(self):
        return self.data.setdefault("emails", [])

    @property
    def deleted_task_ids(self):
        return self.data.setdefault("deleted_tasks", [])

    def active_tasks(self):
        return [t for t in self.tasks if not t.get("archived")]

    def mark_deleted_synced(self, task_ids):
        ids = {str(task_id) for task_id in task_ids or [] if task_id}
        if not ids:
            return
        self.deleted_task_ids[:] = [
            task_id for task_id in self.deleted_task_ids if task_id not in ids
        ]
        self.save()

    def merge_server_tasks(self, server_tasks, accepted_deleted_ids=None):
        """Merge server snapshots without deleting local-only unsynced tasks."""
        local = {t.get("id"): t for t in self.tasks}
        added = updated = 0
        for remote in server_tasks or []:
            if not isinstance(remote, dict):
                continue
            task_id = remote.get("id")
            if not task_id or task_id in self.deleted_task_ids:
                continue
            remote = model.normalize_task(dict(remote))
            current = local.get(task_id)
            if current is None:
                self.tasks.append(remote)
                local[task_id] = remote
                added += 1
            elif str(remote.get("updated_at") or "") >= str(current.get("updated_at") or ""):
                current.update(remote)
                updated += 1
        if accepted_deleted_ids:
            self.mark_deleted_synced(accepted_deleted_ids)
        if added or updated:
            self.save()
        return added, updated

    def task(self, task_id):
        return next((t for t in self.tasks if t.get("id") == task_id), None)

    def email(self, email_id):
        return next((e for e in self.emails if e.get("id") == email_id), None)

    def add_task(self, task):
        self.tasks.insert(0, task)
        self.save()
        return task

    def delete_task(self, task_id):
        return self.delete_tasks([task_id])

    def delete_tasks(self, task_ids):
        ids = {str(task_id) for task_id in task_ids if task_id}
        removed_tasks = [t for t in self.tasks if t.get("id") in ids]
        before = len(self.tasks)
        self.tasks[:] = [t for t in self.tasks if t.get("id") not in ids]
        removed = before - len(self.tasks)
        if removed:
            tombstones = set(self.deleted_task_ids)
            for task in removed_tasks:
                if not task.get("demo") and not task.get("archived"):
                    tombstones.add(task.get("id"))
            self.data["deleted_tasks"] = sorted(t for t in tombstones if t)
            for email in self.emails:
                analysis = email.get("analysis")
                if not isinstance(analysis, dict):
                    continue
                linked = analysis.get("linked_task_id")
                linked_ids = set(analysis.get("linked_task_ids") or [])
                if linked:
                    linked_ids.add(linked)
                matches = analysis.get("matches") or []
                projects = analysis.get("projects") or []
                if projects:
                    # AI project history is permanent. Deleting a task must not
                    # turn the recommendation back into "not created".
                    for project in projects:
                        if isinstance(project, dict) and project.get("task_id") in ids:
                            project["task_deleted"] = True
                            project["task_deleted_at"] = model.iso(model.now())
                    remaining_links = [task_id for task_id in linked_ids if task_id not in ids]
                    if remaining_links:
                        analysis["linked_task_ids"] = remaining_links
                        analysis["linked_task_id"] = remaining_links[0]
                    else:
                        analysis.pop("linked_task_ids", None)
                        analysis.pop("linked_task_id", None)
                    analysis["matches"] = [
                        match for match in matches if match.get("task_id") not in ids]
                    continue
                if linked_ids & ids or any(m.get("task_id") in ids for m in matches):
                    # No AI project history: recompute this mail's suggestion later.
                    email["analysis"] = None
            self.save()
        return removed

    def delete_all_tasks(self):
        return self.delete_tasks([t.get("id") for t in self.tasks])

    def merge_emails(self, incoming):
        """Merge freshly fetched messages by (folder, uid), preserving local state."""
        index = {}
        for i, email in enumerate(self.emails):
            index[(email.get("folder") or "INBOX", str(email.get("uid") or email.get("id")))] = i
        added, updated = 0, 0
        for email in incoming:
            key = (email.get("folder") or "INBOX", str(email.get("uid") or email.get("id")))
            if key in index:
                old = self.emails[index[key]]
                changed = any(old.get(field) != email.get(field) for field in (
                    "subject", "sender", "sender_email", "date", "body", "snippet"
                ))
                read = old.get("read", False)
                old_analysis = old.get("analysis")
                old.update(email)
                old["read"] = read
                old["analysis"] = None if changed else old_analysis
                if changed:
                    updated += 1
            else:
                self.emails.append(self._normalize_email(email))
                index[key] = len(self.emails) - 1
                added += 1
        self.emails.sort(key=lambda e: e.get("date") or "", reverse=True)
        self.save()
        return added, updated

    def add_email(self, email, analyze=True):
        for old in self.emails:
            if old.get("id") == email.get("id"):
                return old
        self.emails.append(self._normalize_email(email))
        self.emails.sort(key=lambda e: e.get("date") or "", reverse=True)
        self.save()
        return email

    def link_email(self, email_id, task_id, note=None):
        return self.link_email_many(email_id, [task_id], note=note)

    def link_email_many(self, email_id, task_ids, note=None):
        email = self.email(email_id)
        targets = [self.task(task_id) for task_id in (task_ids or [])]
        targets = [task for task in targets if task]
        if not email or not targets:
            return False
        if not isinstance(email.get("analysis"), dict):
            email["analysis"] = {}
        target_ids = {task["id"] for task in targets}
        for other in self.tasks:
            if other.get("id") not in target_ids and email_id in (other.get("email_ids") or []):
                other["email_ids"] = [eid for eid in other["email_ids"] if eid != email_id]
                other["updated_at"] = model.iso(model.now())
        email["analysis"]["linked_task_ids"] = [task["id"] for task in targets]
        email["analysis"]["linked_task_id"] = targets[0]["id"]
        email["read"] = True
        for task in targets:
            model.link_email(task, email_id)
        if note:
            for task in targets:
                model.add_note(task, note, email_id=email_id)
        self.save()
        return True

    def unlink_email(self, email_id):
        email = self.email(email_id)
        if not email:
            return False
        analysis = email.get("analysis") if isinstance(email.get("analysis"), dict) else {}
        old_task_id = analysis.get("linked_task_id")
        for task in self.tasks:
            if email_id in (task.get("email_ids") or []):
                task["email_ids"] = [eid for eid in task["email_ids"] if eid != email_id]
                task["updated_at"] = model.iso(model.now())
        analysis.pop("linked_task_id", None)
        analysis.pop("linked_task_ids", None)
        if analysis.get("actionable"):
            analysis["intent"] = "new"
        elif not analysis.get("intent"):
            analysis["intent"] = "info"
        email["analysis"] = analysis
        self.save()
        return True if old_task_id else False

    def purge_demo_once(self):
        """Remove the old first-run sample data exactly once."""
        settings = self.settings()
        if int(settings.get("demo_cleaned_version") or 0) >= 2:
            return 0
        demo_tasks = [t for t in self.tasks if t.get("demo")]
        demo_emails = [e for e in self.emails if e.get("demo")]
        if demo_tasks or demo_emails:
            self.clear_demo()
        settings["demo_cleaned_version"] = 2
        self.save()
        return len(demo_tasks) + len(demo_emails)

    def clear_demo(self):
        self.data["tasks"] = [t for t in self.tasks if not t.get("demo")]
        self.data["emails"] = [e for e in self.emails if not e.get("demo")]
        # Drop links that pointed at removed demo tasks.
        remaining = {t.get("id") for t in self.tasks}
        for email in self.emails:
            analysis = email.get("analysis") or {}
            if analysis.get("linked_task_id") not in remaining:
                analysis["linked_task_id"] = None
            analysis["matches"] = [m for m in analysis.get("matches", []) if m.get("task_id") in remaining]
            email["analysis"] = analysis
        self.save()

    def reset_demo(self):
        fresh = demo.seed_data()
        self.data["tasks"] = fresh["tasks"]
        self.data["emails"] = fresh["emails"]
        self.save()

    def export_payload(self):
        return {
            "app": "TaskDock",
            "version": 2,
            "exported_at": model.iso(model.now()),
            "tasks": self.tasks,
            "emails": self.emails,
            "deleted_tasks": self.deleted_task_ids,
            "settings": {
                k: v
                for k, v in self.settings().items()
                if k not in ("mail_password", "ai_api_key", "last_sync_error", "collab_token")
            },
        }

    def import_payload(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("文件内容不是有效的 TaskDock 备份")
        tasks = payload.get("tasks")
        emails = payload.get("emails")
        if not isinstance(tasks, list) or not isinstance(emails, list):
            raise ValueError("备份中缺少任务或邮件列表")
        self.data["tasks"] = [model.normalize_task(t) for t in tasks if isinstance(t, dict)]
        self.data["emails"] = [self._normalize_email(e) for e in emails if isinstance(e, dict)]
        self.data["deleted_tasks"] = [
            str(x) for x in (payload.get("deleted_tasks") or []) if x
        ]
        settings = self.settings()
        imported = payload.get("settings") or {}
        skip = {"mail_password", "ai_api_key", "collab_token", "collab_user_id", "collab_username",
                "collab_display_name", "collab_role", "collab_last_sync"}
        for key, value in imported.items():
            if key in settings and key not in skip:
                settings[key] = value
        self.save()
        return len(self.data["tasks"]), len(self.data["emails"])

    def stats(self):
        return {
            "path": str(self.path),
            "size": self.path.stat().st_size if self.path.exists() else 0,
            "updated": datetime.fromtimestamp(self.path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            if self.path.exists()
            else "—",
        }

# -*- coding: utf-8 -*-
"""HTTP client for the TaskDock collaboration server (stdlib only)."""

import json
import urllib.error
import urllib.parse
import urllib.request


class CollabError(Exception):
    def __init__(self, message, status=0):
        self.status = status
        super(CollabError, self).__init__(message)


def normalize_server(url):
    url = (url or "").strip().rstrip("/")
    if not url:
        raise CollabError("请填写主管理服务地址")
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url


class CollabClient(object):
    def __init__(self, server, token=""):
        self.server = normalize_server(server)
        self.token = token or ""

    def _request(self, method, path, payload=None, timeout=15):
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(self.server + path, data=data, method=method)
        request.add_header("Accept", "application/json")
        if payload is not None:
            request.add_header("Content-Type", "application/json; charset=utf-8")
        if self.token:
            request.add_header("Authorization", "Bearer " + self.token)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8", errors="replace"))
            except Exception:
                payload = {}
            raise CollabError(payload.get("error") or ("服务返回 HTTP %s" % exc.code), exc.code)
        except urllib.error.URLError as exc:
            raise CollabError("无法连接主管理服务：%s" % getattr(exc, "reason", exc))
        except Exception as exc:
            raise CollabError("请求失败：%s" % exc)

    def status(self):
        return self._request("GET", "/api/status")

    def login(self, username, password):
        return self._request("POST", "/api/login", {
            "username": username, "password": password,
        })

    def register(self, username, password, display_name=""):
        return self._request("POST", "/api/register", {
            "username": username, "password": password,
            "display_name": display_name or username,
        })

    def me(self):
        return self._request("GET", "/api/me")

    def collab(self):
        return self._request("GET", "/api/collab")

    def overview(self):
        return self._request("GET", "/api/admin/overview")

    def sync(self, tasks, deleted_ids=None):
        return self._request("POST", "/api/sync", {
            "tasks": tasks,
            "deleted_ids": deleted_ids or [],
        }, timeout=25)

    def collect_status(self):
        return self._request("GET", "/api/collect/status", timeout=10)

    def messages_read(self, ids):
        return self._request("POST", "/api/messages/read", {"ids": ids}, timeout=10)

    def reply_message(self, message_id, body):
        return self._request("POST", "/api/messages/reply",
                             {"message_id": message_id, "body": body}, timeout=15)

    def message_threads(self):
        return self._request("GET", "/api/messages/threads", timeout=15)

    def friend_messages(self, friend_id):
        return self._request("GET", "/api/friends/messages?friend_id=%s" % int(friend_id),
                             timeout=15)

    def send_friend_message(self, friend_id, body):
        return self._request("POST", "/api/friends/messages/send",
                             {"friend_id": friend_id, "body": body}, timeout=15)

    def acquire_task_lock(self, scope):
        return self._request("POST", "/api/locks/acquire", {"scope": scope}, timeout=8)

    def release_task_lock(self, scope):
        return self._request("POST", "/api/locks/release", {"scope": scope}, timeout=8)

    def update_shared_task(self, scope, task, base_revision):
        return self._request("POST", "/api/tasks/shared/update", {
            "scope": scope,
            "task": task,
            "base_revision": base_revision,
        }, timeout=15)

    def add_friend(self, username):
        return self._request("POST", "/api/friends/request", {"username": username})

    def respond_friend(self, request_id, accept):
        return self._request("POST", "/api/friends/respond", {
            "request_id": request_id, "accept": bool(accept),
        })

    def forward_task(self, task_id, to_user_id, mode="share", message=""):
        return self._request("POST", "/api/offers/forward", {
            "task_id": task_id,
            "to_user_id": to_user_id,
            "mode": mode,
            "message": message,
        })

    def respond_offer(self, offer_id, accept):
        return self._request("POST", "/api/offers/respond", {
            "offer_id": offer_id, "accept": bool(accept),
        }, timeout=25)

    def logout(self):
        try:
            return self._request("POST", "/api/logout", {})
        except CollabError:
            return {}

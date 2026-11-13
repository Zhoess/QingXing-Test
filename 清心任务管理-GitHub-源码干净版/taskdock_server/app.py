# -*- coding: utf-8 -*-
"""清心任务管理终端 HTTP 服务（标准库实现，无第三方依赖）。

启动：
    python -m taskdock_server --host 0.0.0.0 --port 8787
管理端：
    http://127.0.0.1:8787/admin
"""

import argparse
import json
import os
import socket
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .db import Database, now_iso

VERSION = "2.0.0"
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def default_data_dir():
    override = os.environ.get("TASKDOCK_SERVER_DATA_DIR")
    if override:
        return Path(override)
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "TaskDockServer"


class AppContext(object):
    def __init__(self, database):
        self.db = database
        self.collect_epoch = 0
        self.collect_requested_at = None
        self.collect_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    context = None
    server_version = "TaskDockServer/%s" % VERSION

    # ------------------------------------------------------------- plumbing
    def log_message(self, fmt, *args):
        sys.stdout.write("[%s] %s\n" % (datetime.now().strftime("%H:%M:%S"), fmt % args))
        sys.stdout.flush()

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status, message):
        self._json(status, {"error": message})

    def _body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > 8 * 1024 * 1024:
            raise ValueError("请求内容过大")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            raise ValueError("请求 JSON 格式错误")

    def _bearer(self):
        header = self.headers.get("Authorization") or ""
        if header.lower().startswith("bearer "):
            return header[7:].strip()
        return self.headers.get("X-TaskDock-Token") or ""

    def _auth(self, admin=False):
        user = self.context.db.user_for_token(self._bearer())
        if not user:
            self._error(401, "未登录或登录已过期")
            return None
        if admin and user.get("role") != "admin":
            self._error(403, "需要管理账号权限")
            return None
        return user

    def _is_loopback(self):
        return self.client_address[0] in ("127.0.0.1", "::1", "localhost")

    def _static(self, relative):
        name = os.path.basename(relative)
        if name not in ("admin.css", "admin.js"):
            return self._error(404, "文件不存在")
        path = STATIC_DIR / name
        if not path.exists():
            return self._error(404, "文件不存在")
        body = path.read_bytes()
        content_type = "text/css; charset=utf-8" if name.endswith(".css") else (
            "application/javascript; charset=utf-8"
        )
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _admin_page(self):
        path = BASE_DIR / "templates" / "admin.html"
        if not path.exists():
            return self._error(500, "管理端页面缺失")
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _dispatch_get(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/admin")
            self.end_headers()
            return
        if path in ("/admin", "/setup"):
            return self._admin_page()
        if path.startswith("/static/"):
            return self._static(path[len("/static/"):])
        if path == "/api/health":
            return self._json(200, {"ok": True, "version": VERSION, "time": now_iso()})
        if path == "/api/status":
            return self._json(200, {
                "setup_required": self.context.db.setup_required(),
                "version": VERSION,
                "server_time": now_iso(),
            })
        if path == "/api/me":
            user = self._auth()
            return self._json(200, {"user": user}) if user else None
        if path == "/api/collab":
            user = self._auth()
            if not user:
                return
            return self._json(200, self._collab_payload(user))
        if path == "/api/collect/status":
            user = self._auth()
            if not user:
                return
            self.context.db.touch_user(user["id"])
            with self.context.collect_lock:
                epoch = self.context.collect_epoch
                requested_at = self.context.collect_requested_at
            return self._json(200, {
                "epoch": epoch,
                "requested_at": requested_at,
                "online": self.context.db.online_count(),
                "messages": self.context.db.unread_messages(user["id"]),
                "server_time": now_iso(),
            })
        if path == "/api/admin/messages/threads":
            user = self._auth(admin=True)
            if not user:
                return
            return self._json(200, self.context.db.message_threads(user["id"], admin=True))
        if path == "/api/messages/threads":
            user = self._auth()
            if not user:
                return
            return self._json(200, self.context.db.message_threads(user["id"], admin=False))
        if path == "/api/friends/messages":
            user = self._auth()
            if not user:
                return
            query = parse_qs(parsed.query)
            try:
                friend_id = int((query.get("friend_id") or [""])[0])
            except (TypeError, ValueError):
                return self._error(400, "无效好友")
            if not self.context.db.are_friends(user["id"], friend_id):
                return self._error(403, "对方不是好友")
            return self._json(200, {
                "messages": self.context.db.friend_messages(user["id"], friend_id),
            })
        if path == "/api/messages/thread":
            user = self._auth()
            if not user:
                return
            query = parse_qs(parsed.query)
            try:
                task_user_id = int((query.get("task_user_id") or [""])[0])
            except (TypeError, ValueError):
                return self._error(400, "无效账户")
            task_id = (query.get("task_id") or [""])[0]
            messages = self.context.db.task_messages(task_user_id, task_id)
            if not any(item.get("from_id") == user["id"] or item.get("to_id") == user["id"]
                       for item in messages):
                return self._error(403, "无权查看该对话")
            return self._json(200, {"messages": messages})
        if path == "/api/admin/messages":
            if not self._auth(admin=True):
                return
            query = parse_qs(parsed.query)
            try:
                task_user_id = int((query.get("task_user_id") or [""])[0])
            except (TypeError, ValueError):
                return self._error(400, "无效账户")
            task_id = (query.get("task_id") or [""])[0]
            if not task_id:
                return self._error(400, "缺少任务")
            return self._json(200, {
                "messages": self.context.db.task_messages(task_user_id, task_id),
                "recipient": self.context.db.task_recipient(task_user_id, task_id),
            })
        if path == "/api/admin/overview":
            if not self._auth(admin=True):
                return
            return self._json(200, self.context.db.admin_overview())
        self._error(404, "接口不存在")

    def _dispatch_post(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            body = self._body()
        except ValueError as exc:
            return self._error(400, str(exc))

        if path == "/api/setup":
            if not self._is_loopback():
                return self._error(403, "首次初始化只能在本机浏览器完成")
            if not self.context.db.setup_required():
                return self._error(400, "管理账号已存在")
            try:
                user = self.context.db.create_user(
                    body.get("username"), body.get("password"),
                    body.get("display_name") or body.get("username"), "admin",
                )
            except ValueError as exc:
                return self._error(400, str(exc))
            token = self.context.db.create_session(user["id"])
            self.context.db.audit(user["id"], "setup", "创建管理账号")
            return self._json(201, {"token": token, "user": user})
        if path == "/api/login":
            try:
                user = self.context.db.authenticate(body.get("username"), body.get("password"))
            except PermissionError as exc:
                return self._error(403, str(exc))
            if not user:
                return self._error(401, "账号或密码不正确")
            token = self.context.db.create_session(user["id"])
            return self._json(200, {"token": token, "user": user})
        if path == "/api/register":
            try:
                user = self.context.db.create_user(
                    body.get("username"), body.get("password"),
                    body.get("display_name") or body.get("username"), "member",
                )
            except ValueError as exc:
                return self._error(400, str(exc))
            token = self.context.db.create_session(user["id"])
            return self._json(201, {"token": token, "user": user})
        if path == "/api/logout":
            self.context.db.logout(self._bearer())
            return self._json(200, {"ok": True})

        user = self._auth()
        if not user:
            return
        if path == "/api/admin/messages/thread/read":
            if user.get("role") != "admin":
                return self._error(403, "需要管理账号权限")
            try:
                task_user_id = int(body.get("task_user_id"))
            except (TypeError, ValueError):
                return self._error(400, "无效账户")
            count = self.context.db.mark_thread_read(
                user["id"], task_user_id, body.get("task_id") or "")
            return self._json(200, {"ok": True, "read": count})
        if path == "/api/admin/messages/send":
            if user.get("role") != "admin":
                return self._error(403, "需要管理账号权限")
            try:
                task_user_id = int(body.get("task_user_id"))
            except (TypeError, ValueError):
                return self._error(400, "无效账户")
            task_id = str(body.get("task_id") or "").strip()
            context = self.context.db.task_recipient(task_user_id, task_id)
            if not context:
                return self._error(400, "该任务没有可沟通的客户端账号")
            try:
                message_id = self.context.db.send_message(
                    user["id"], context["recipient"]["id"], body.get("body"),
                    task_user_id=task_user_id, task_id=task_id,
                    task_title=context["task_title"],
                )
            except ValueError as exc:
                return self._error(400, str(exc))
            self.context.db.audit(user["id"], "send_task_message",
                                  "%s/%s" % (task_user_id, task_id))
            return self._json(201, {
                "id": message_id,
                "online": self.context.db.user_online(context["recipient"]["id"]),
                "recipient": context["recipient"],
                "recipient_kind": context.get("recipient_kind"),
            })
        if path == "/api/messages/read":
            ids = body.get("ids") or []
            count = self.context.db.mark_messages_read(user["id"], ids)
            return self._json(200, {"ok": True, "read": count})
        if path == "/api/messages/reply":
            try:
                message_id = int(body.get("message_id"))
            except (TypeError, ValueError):
                return self._error(400, "无效消息")
            original = self.context.db.message(message_id)
            if not original or original["to_id"] != user["id"]:
                return self._error(404, "消息不存在")
            try:
                new_id = self.context.db.send_message(
                    user["id"], original["from_id"], body.get("body"),
                    task_user_id=original.get("task_user_id"),
                    task_id=original.get("task_id"),
                    task_title=original.get("task_title") or "",
                )
            except ValueError as exc:
                return self._error(400, str(exc))
            self.context.db.mark_messages_read(user["id"], [message_id])
            return self._json(201, {"id": new_id, "ok": True})
        if path == "/api/friends/messages/send":
            try:
                friend_id = int(body.get("friend_id"))
            except (TypeError, ValueError):
                return self._error(400, "无效好友")
            if not self.context.db.are_friends(user["id"], friend_id):
                return self._error(403, "对方不是好友")
            try:
                message_id = self.context.db.send_message(
                    user["id"], friend_id, body.get("body"),
                    thread_key=self.context.db.friend_thread_key(user["id"], friend_id),
                )
            except ValueError as exc:
                return self._error(400, str(exc))
            return self._json(201, {"ok": True, "id": message_id})
        if path == "/api/locks/acquire":
            scope = str(body.get("scope") or "").strip()
            if not scope:
                return self._error(400, "缺少任务范围")
            try:
                ok, owner, revision = self.context.db.acquire_task_lock(
                    scope, user["id"],
                    user.get("display_name") or user.get("username") or "",
                )
            except ValueError as exc:
                return self._error(400, str(exc))
            if not ok:
                return self._error(409, "%s 账户编辑中，请稍后更新重试" % owner)
            return self._json(200, {"ok": True, "revision": revision})
        if path == "/api/tasks/shared/update":
            scope = str(body.get("scope") or "").strip()
            task = body.get("task") if isinstance(body.get("task"), dict) else {}
            try:
                revision, updated_at = self.context.db.update_shared_task(
                    user["id"], scope, task, body.get("base_revision"))
            except ValueError as exc:
                message = str(exc)
                status = 409 if "更新" in message or "锁" in message else 400
                return self._error(status, message)
            return self._json(200, {"ok": True, "revision": revision,
                                    "updated_at": updated_at})
        if path == "/api/locks/release":
            count = self.context.db.release_task_lock(
                str(body.get("scope") or "").strip(), user["id"])
            return self._json(200, {"ok": True, "released": count})
        if path == "/api/admin/collect":
            if user.get("role") != "admin":
                return self._error(403, "需要管理账号权限")
            with self.context.collect_lock:
                self.context.collect_epoch += 1
                self.context.collect_requested_at = now_iso()
                epoch = self.context.collect_epoch
                requested_at = self.context.collect_requested_at
            return self._json(200, {
                "ok": True,
                "epoch": epoch,
                "requested_at": requested_at,
                "online": self.context.db.online_count(),
            })
        if path == "/api/sync":
            tasks = body.get("tasks") or []
            deleted = body.get("deleted_ids") or []
            if not isinstance(tasks, list) or not isinstance(deleted, list):
                return self._error(400, "tasks / deleted_ids 必须是数组")
            tasks = [t for t in tasks[:800] if isinstance(t, dict)]
            changed = self.context.db.upsert_tasks(user["id"], tasks)
            removed = self.context.db.delete_tasks(user["id"], deleted[:800])
            return self._json(200, {
                "tasks": self.context.db.get_tasks(user["id"]),
                "accepted_deleted_ids": deleted[:800],
                "changed": changed,
                "removed": removed,
                "server_time": now_iso(),
            })
        if path == "/api/friends/request":
            target = self.context.db.get_user_by_username(body.get("username"))
            if not target:
                return self._error(404, "没有找到这个账号")
            try:
                result = self.context.db.add_friend_request(user["id"], target["id"])
            except ValueError as exc:
                return self._error(400, str(exc))
            return self._json(201, result)
        if path == "/api/friends/respond":
            try:
                status = self.context.db.respond_friend_request(
                    user["id"], int(body.get("request_id")), bool(body.get("accept"))
                )
            except (ValueError, TypeError) as exc:
                return self._error(400, str(exc))
            return self._json(200, {"status": status})
        if path == "/api/offers/forward":
            try:
                offer_id = self.context.db.create_offer(
                    user["id"], body.get("task_id"), int(body.get("to_user_id")),
                    body.get("mode") or "share", body.get("message") or "",
                )
            except (ValueError, TypeError) as exc:
                return self._error(400, str(exc))
            return self._json(201, {"offer_id": offer_id, "status": "pending"})
        if path == "/api/offers/respond":
            try:
                task = self.context.db.respond_offer(
                    user["id"], int(body.get("offer_id")), bool(body.get("accept"))
                )
            except (ValueError, TypeError) as exc:
                return self._error(400, str(exc))
            return self._json(200, {
                "status": "accepted" if body.get("accept") else "declined",
                "task": task,
            })
        if path.startswith("/api/admin/tasks/"):
            if user.get("role") != "admin":
                return self._error(403, "需要管理账号权限")
            parts = path.split("/")
            try:
                target_user_id = int(parts[4])
            except (IndexError, ValueError):
                return self._error(400, "无效账户")
            if len(parts) < 7 or parts[6] != "tags":
                return self._error(404, "接口不存在")
            try:
                tags = self.context.db.set_task_tags(
                    target_user_id, parts[5], body.get("tags") or [])
            except ValueError as exc:
                return self._error(400, str(exc))
            self.context.db.audit(user["id"], "set_task_tags",
                                  "%s/%s: %s" % (target_user_id, parts[5], ",".join(tags)))
            return self._json(200, {"ok": True, "tags": tags})
        if path == "/api/admin/users":
            if user.get("role") != "admin":
                return self._error(403, "需要管理账号权限")
            try:
                created = self.context.db.create_user(
                    body.get("username"), body.get("password"),
                    body.get("display_name") or body.get("username"), "member",
                    org_unit_id=body.get("org_unit_id"),
                )
            except ValueError as exc:
                return self._error(400, str(exc))
            self.context.db.audit(user["id"], "create_user", created["username"])
            return self._json(201, {"user": created})
        if path == "/api/admin/org/create":
            if user.get("role") != "admin":
                return self._error(403, "需要管理账号权限")
            try:
                unit = self.context.db.create_org_unit(
                    body.get("name"), body.get("parent_id"))
            except ValueError as exc:
                return self._error(400, str(exc))
            return self._json(201, {"unit": unit})
        if path == "/api/admin/org/update":
            if user.get("role") != "admin":
                return self._error(403, "需要管理账号权限")
            try:
                unit = self.context.db.update_org_unit(
                    int(body.get("id")), body.get("name"), body.get("parent_id"))
            except (ValueError, TypeError) as exc:
                return self._error(400, str(exc))
            return self._json(200, {"unit": unit})
        if path == "/api/admin/org/delete":
            if user.get("role") != "admin":
                return self._error(403, "需要管理账号权限")
            try:
                self.context.db.delete_org_unit(int(body.get("id")))
            except (ValueError, TypeError) as exc:
                return self._error(400, str(exc))
            return self._json(200, {"ok": True})
        if path.startswith("/api/admin/users/"):
            if user.get("role") != "admin":
                return self._error(403, "需要管理账号权限")
            parts = path.split("/")
            try:
                target_id = int(parts[4])
            except (IndexError, ValueError):
                return self._error(400, "无效账号")
            action = parts[5] if len(parts) > 5 else ""
            if action == "status":
                try:
                    self.context.db.set_status(target_id, body.get("status"))
                except ValueError as exc:
                    return self._error(400, str(exc))
                self.context.db.audit(user["id"], "set_status", "%s -> %s" % (
                    target_id, body.get("status")))
                return self._json(200, {"ok": True})
            if action == "password":
                try:
                    self.context.db.set_password(target_id, body.get("password"))
                except ValueError as exc:
                    return self._error(400, str(exc))
                self.context.db.audit(user["id"], "reset_password", str(target_id))
                return self._json(200, {"ok": True})
            if action == "update":
                try:
                    updated = self.context.db.update_user(
                        target_id, body.get("username"), body.get("display_name"),
                        org_unit_id=body.get("org_unit_id"),
                    )
                except ValueError as exc:
                    return self._error(400, str(exc))
                self.context.db.audit(user["id"], "update_user", str(target_id))
                return self._json(200, {"ok": True, "user": updated})
            if action == "delete":
                try:
                    counts = self.context.db.delete_user(
                        user["id"], target_id, body.get("confirm")
                    )
                except ValueError as exc:
                    return self._error(400, str(exc))
                self.context.db.audit(user["id"], "delete_user", str(target_id))
                return self._json(200, {"ok": True, "removed": counts})
        self._error(404, "接口不存在")

    def _collab_payload(self, user):
        db = self.context.db
        friends = db.friends(user["id"])
        requests = db.friend_requests(user["id"])
        offers = db.offers_for(user["id"])
        pending = [o for o in offers["inbox"] if o["status"] == "pending"]
        return {
            "user": user,
            "friends": friends,
            "directory": db.directory(),
            "org_unit_id": user.get("org_unit_id"),
            "owner_scope": db.owner_scope(user["id"]),
            "requests": requests,
            "offers": offers,
            "counts": {
                "friends": len(friends),
                "friend_requests": len(requests["incoming"]),
                "pending_offers": len(pending),
            },
            "server_time": now_iso(),
        }

    def do_GET(self):
        try:
            self._dispatch_get()
        except Exception as exc:
            self.log_message("GET error: %s", exc)
            try:
                self._error(500, "服务器内部错误")
            except Exception:
                pass

    def do_POST(self):
        try:
            self._dispatch_post()
        except Exception as exc:
            self.log_message("POST error: %s", exc)
            try:
                self._error(500, "服务器内部错误")
            except Exception:
                pass


class TaskDockServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def build_server(host="0.0.0.0", port=8787, data_dir=None):
    data_dir = Path(data_dir) if data_dir else default_data_dir()
    database = Database(data_dir / "server.db")
    handler = type("BoundHandler", (Handler,), {"context": AppContext(database)})
    server = TaskDockServer((host, int(port)), handler)
    return server, database


def lan_ip():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def main():
    parser = argparse.ArgumentParser(description="清心任务管理终端服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址，默认 0.0.0.0")
    parser.add_argument("--port", type=int, default=8787, help="监听端口")
    parser.add_argument("--data-dir", default=None, help="数据目录")
    args = parser.parse_args()

    server, database = build_server(args.host, args.port, args.data_dir)
    data_dir = Path(args.data_dir) if args.data_dir else default_data_dir()
    local = "http://127.0.0.1:%d/admin" % server.server_address[1]
    network = "http://%s:%d/admin" % (lan_ip(), server.server_address[1])
    print("")
    print("  清心任务管理终端 %s" % VERSION)
    print("  ------------------------------------------")
    print("  本机管理端 : %s" % local)
    print("  局域网管理端: %s" % network)
    print("  数据文件   : %s" % (data_dir / "server.db"))
    print("  清心任务客户端填写服务器地址: http://%s:%d" % (lan_ip(), server.server_address[1]))
    if database.setup_required():
        print("  首次使用：请在本机浏览器打开管理端，创建管理账号账号。")
    print("  Ctrl+C 停止服务。")
    print("")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止服务…")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()

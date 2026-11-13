# -*- coding: utf-8 -*-
"""Desktop shell, window behavior and cross-page actions."""

import ctypes
import json
import os
import queue
import re
import threading
import time
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox

from . import analyzer, mailer, model
from .collab import CollabClient, CollabError, normalize_server
from .constants import APP_NAME, APP_NAME_EN, COLORS, VERSION
from .page_collab import CollabPage, ForwardDialog, FriendChatDialog, GlobalTasksModal
from .page_mail import (AIProjectReviewDialog, AIProjectSummaryDialog, LinkTaskDialog,
                        MailDetail, MailPage, MessageDialog, MessageInboxDialog, intent_of)
from .page_settings import SettingsPage
from .page_tasks import LostReasonDialog, TaskEditor, TasksPage, TaskView
from .store import Store
from .ui_common import Toast, truncate
from .widgets import PillButton, ScrollFrame, SmallIconButton, round_rect


def get_work_area():
    try:
        import ctypes.wintypes as wintypes

        rect = wintypes.RECT()
        ok = ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0)
        if ok:
            return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        pass
    root = tk._default_root
    width = root.winfo_screenwidth() if root else 1920
    height = root.winfo_screenheight() if root else 1080
    return 0, 0, width, height - 48


class TaskDockApp(tk.Tk):
    def __init__(self, data_dir=None, seed=False, auto_show=True):
        tk.Tk.__init__(self)
        self.withdraw()
        self.store = Store(data_dir, seed=seed)
        self.store.load()
        if not seed:
            self.store.purge_demo_once()
        self.W = 424
        self.work = get_work_area()
        work_h = self.work[3] - self.work[1]
        self.H = max(640, min(960, work_h - 16))
        self.syncing = False
        self._modals = []
        self._collapsed = False
        self._expanded_geom = None
        self._drag = None
        self._edge_drag = None
        self._collapsed_moved = False
        self._running = True
        self.current_page = "tasks"
        self._show_after = None
        self._auto_sync_after = None
        self._collab_after = None
        self._collab_sync_after = None
        self._collab_meta_last = 0.0
        self._collect_seen = 0
        self._collect_checking = False
        self._task_locks = {}
        self._message_dialog = None
        self.collab_user = self.store.collab_user()
        self.collab_data = None
        self.collab_busy = False
        self.collab_syncing = False
        self._ai_busy = False
        self._ai_started = None
        self._ai_progress_frame = None
        self._ai_progress_after = None
        self.collab_refreshing = False
        self.collab_error = ""
        self.collab_message = ""
        self.toast = Toast(self)
        self._setup_window()
        analyzer.ensure_analyses(self.store)
        self._build_shell()
        self._bind_global()
        self._load_icon()
        if auto_show:
            self._show_after = self.after(80, self._show)
        self._auto_sync_after = self.after(1500, self._maybe_auto_sync)
        if self.collab_user and self.store.collab_token():
            self.after(1600, self.collab_refresh)
        self._collab_after = self.after(10000, self._collab_tick)

    # --------------------------------------------------------------- window
    def _setup_window(self):
        self.configure(bg=COLORS["line"])
        self.overrideredirect(True)
        self.title(APP_NAME)
        self.attributes("-topmost", bool(self.store.settings().get("topmost", True)))
        x, y = self._initial_position()
        self.geometry("%dx%d+%d+%d" % (self.W, self.H, x, y))
        self.update_idletasks()
        self._round_corners()
        self._make_appwindow()

    def _make_appwindow(self):
        """Force the frameless window into the Windows taskbar / Alt-Tab list."""
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "TaskClient.Desktop"
            )
        except Exception:
            pass
        try:
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            gwl_exstyle = -20
            ws_ex_toolwindow = 0x00000080
            ws_ex_appwindow = 0x00040000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, gwl_exstyle)
            style = (style | ws_ex_appwindow) & ~ws_ex_toolwindow
            ctypes.windll.user32.SetWindowLongW(hwnd, gwl_exstyle, style)
            flags = 0x0001 | 0x0002 | 0x0004 | 0x0020 | 0x0010  # NOSIZE/NOMOVE/NOZORDER/FRAMECHANGED/NOACTIVATE
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, flags)
            self._taskbar_add_tab(hwnd)
        except Exception:
            pass

    @staticmethod
    def _taskbar_add_tab(hwnd):
        """Ask the Windows taskbar to add this HWND as a tab (best effort)."""
        try:
            class GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", ctypes.c_ulong),
                    ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort),
                    ("Data4", ctypes.c_ubyte * 8),
                ]

            clsid = GUID(0x56FDF344, 0xFD6D, 0x11D0,
                         (ctypes.c_ubyte * 8)(0x95, 0x8A, 0x00, 0x60, 0x97, 0xC9, 0xA0, 0x90))
            iid = GUID(0x56FDF342, 0xFD6D, 0x11D0,
                       (ctypes.c_ubyte * 8)(0x95, 0x8A, 0x00, 0x60, 0x97, 0xC9, 0xA0, 0x90))
            ole32 = ctypes.windll.ole32
            ole32.CoInitialize(None)
            obj = ctypes.c_void_p()
            result = ole32.CoCreateInstance(
                ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(obj)
            )
            if result != 0 or not obj:
                return
            vtable = ctypes.cast(
                obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
            ).contents
            hr_init = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vtable[3])
            add_tab = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p
            )(vtable[4])
            release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])
            hr_init(obj)
            add_tab(obj, hwnd)
            release(obj)
        except Exception:
            pass

    def _initial_position(self):
        left, top, right, bottom = self.work
        settings = self.store.settings()
        if settings.get("dock_right", True):
            x = right - self.W - 16
            y = top + max(10, (bottom - top - self.H) // 2)
        else:
            try:
                x = int(settings.get("window_x"))
                y = int(settings.get("window_y"))
            except (TypeError, ValueError):
                x = right - self.W - 16
                y = top + 30
            x = max(left - 60, min(x, right - 80))
            y = max(top, min(y, bottom - 120))
        return x, y

    def _round_corners(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            preference = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(preference), ctypes.sizeof(preference)
            )
        except Exception:
            pass

    def _load_icon(self):
        icon = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
        if icon.exists():
            try:
                self._icon_image = tk.PhotoImage(file=str(icon))
                self.iconphoto(True, self._icon_image)
            except Exception:
                pass

    def _show(self):
        self.deiconify()
        self.lift()
        self.attributes("-topmost", bool(self.store.settings().get("topmost", True)))
        self.after(30, self._make_appwindow)

    def _build_shell(self):
        self.outer = tk.Frame(self, bg=COLORS["line"])
        self.outer.pack(fill="both", expand=True)
        self.shell = tk.Frame(self.outer, bg=COLORS["bg"])
        self.shell.pack(fill="both", expand=True, padx=1, pady=1)

        self._build_header()
        self._build_nav()
        self.content = tk.Frame(self.shell, bg=COLORS["bg"])
        self.content.pack(fill="both", expand=True)

        self.pages = {}
        self.pages["tasks"] = TasksPage(self.content, self)
        self.pages["mail"] = MailPage(self.content, self)
        self.pages["collab"] = CollabPage(self.content, self)
        self.pages["settings"] = SettingsPage(self.content, self)
        for page in self.pages.values():
            page.place(x=0, y=0, relwidth=1, relheight=1)
        self.switch_page("tasks", refresh=False)

        self.edge = tk.Frame(self, bg=COLORS["dark"], width=38)
        self._build_edge()

    def _build_header(self):
        header = tk.Frame(self.shell, bg=COLORS["surface"], height=60)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        self.header = header
        tk.Frame(header, bg=COLORS["line_soft"], height=1).pack(side="bottom", fill="x")

        mark = tk.Canvas(header, width=30, height=30, bg=COLORS["surface"],
                         highlightthickness=0, bd=0)
        mark.pack(side="left", padx=(16, 9))
        round_rect(mark, 1, 1, 29, 29, 8, fill=COLORS["accent"], outline=COLORS["accent"])
        mark.create_line(8, 15, 13, 20, 22, 10, fill=COLORS["white"], width=2,
                         capstyle="round", joinstyle="round")
        brand = tk.Frame(header, bg=COLORS["surface"])
        brand.pack(side="left")
        self.brand_title = tk.Label(brand, text=APP_NAME, bg=COLORS["surface"],
                                    fg=COLORS["ink"], font=("Microsoft YaHei UI", 12, "bold"))
        self.brand_title.pack(anchor="w", pady=(9, 0))
        self.brand_sub = tk.Label(brand, text="桌面任务协作", bg=COLORS["surface"],
                                  fg=COLORS["faint"], font=("Microsoft YaHei UI", 7))
        self.brand_sub.pack(anchor="w")

        close = SmallIconButton(header, "×", self.close_app, bg=COLORS["surface"],
                                size=30, hover_bg=COLORS["danger_soft"])
        close.pack(side="right", padx=(0, 10), pady=15)
        self.collapse_btn = SmallIconButton(header, "›", self.collapse, bg=COLORS["surface"],
                                            size=30)
        self.collapse_btn.pack(side="right", padx=(0, 2), pady=15)
        pinned = bool(self.store.settings().get("topmost", True))
        self.pin_btn = PillButton(header, "已置顶" if pinned else "置顶", self.toggle_pin,
                                  kind="soft" if pinned else "ghost", width=54, height=28)
        self.pin_btn.pack(side="right", padx=(0, 5), pady=16)

        for widget in (header, mark, brand, self.brand_title, self.brand_sub):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._do_drag)
            widget.bind("<ButtonRelease-1>", self._end_drag)

    def _build_nav(self):
        nav = tk.Frame(self.shell, bg=COLORS["surface"], height=62)
        nav.pack(fill="x", side="bottom")
        nav.pack_propagate(False)
        tk.Frame(nav, bg=COLORS["line_soft"], height=1).pack(side="top", fill="x")
        bar = tk.Frame(nav, bg=COLORS["surface"])
        bar.pack(fill="both", expand=True)
        self.nav_items = {}
        from .widgets import NavItem

        specs = [("tasks", "任务", "tasks"), ("mail", "邮件", "mail"),
                 ("collab", "协作", "users"), ("settings", "设置", "settings")]
        for index, (key, label, icon) in enumerate(specs):
            item = NavItem(bar, icon, label, lambda k=key: self.switch_page(k),
                           active=(key == "tasks"))
            item.grid(row=0, column=index, sticky="nsew")
            bar.grid_columnconfigure(index, weight=1)
            self.nav_items[key] = item

    def _build_edge(self):
        self.edge.pack_propagate(False)
        top = tk.Frame(self.edge, bg=COLORS["dark"], height=42)
        top.pack(fill="x", pady=(12, 0))
        mark = tk.Canvas(top, width=26, height=26, bg=COLORS["dark"],
                         highlightthickness=0, bd=0)
        mark.pack()
        mark.create_oval(1, 1, 25, 25, fill=COLORS["accent"], outline=COLORS["accent"])
        mark.create_line(8, 13, 12, 17, 19, 9, fill=COLORS["white"], width=2,
                         capstyle="round", joinstyle="round")
        self.edge_text = tk.Label(self.edge, text="任\n务\n清\n单", bg=COLORS["dark"],
                                  fg=COLORS["white"], font=("Microsoft YaHei UI", 10, "bold"),
                                  justify="center", cursor="hand2")
        self.edge_text.pack(pady=(14, 8))
        self.edge_count = tk.Label(self.edge, text="0", bg=COLORS["dark_soft"],
                                   fg=COLORS["white"], font=("Microsoft YaHei UI", 8, "bold"),
                                   padx=6, pady=2)
        self.edge_count.pack()
        mark.configure(cursor="fleur")
        for widget in (self.edge, top, mark, self.edge_text, self.edge_count):
            widget.configure(cursor="fleur") if widget is not mark else None
            widget.bind("<ButtonPress-1>", self._edge_press)
            widget.bind("<B1-Motion>", self._edge_motion)
            widget.bind("<ButtonRelease-1>", self._edge_release)
            widget.bind("<Button-3>", self._edge_menu)

    def _edge_press(self, event):
        self._edge_drag = [
            event.x_root, event.y_root,
            event.x_root - self.winfo_x(), event.y_root - self.winfo_y(), False,
        ]
        try:
            self.edge.grab_set()
        except Exception:
            pass

    def _edge_motion(self, event):
        if not self._edge_drag:
            return
        start_x, start_y, offset_x, offset_y, _ = self._edge_drag
        if abs(event.x_root - start_x) + abs(event.y_root - start_y) > 3:
            self._edge_drag[4] = True
        self.geometry("+%d+%d" % (event.x_root - offset_x, event.y_root - offset_y))

    def _edge_release(self, event=None):
        if not self._edge_drag:
            return
        moved = self._edge_drag[4]
        offset_x, offset_y = self._edge_drag[2], self._edge_drag[3]
        self._edge_drag = None
        try:
            self.edge.grab_release()
        except Exception:
            pass
        if not moved:
            self.expand()
            return
        left, top, right, bottom = self.work
        if event is not None:
            x = event.x_root - offset_x
            y = event.y_root - offset_y
        else:
            x, y = self.winfo_x(), self.winfo_y()
        x = max(left, min(x, right - 38))
        y = max(top, min(y, bottom - 220))
        self.geometry("+%d+%d" % (x, y))
        self._collapsed_moved = True

    def _edge_menu(self, event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="展开", command=self.expand)
        menu.add_separator()
        menu.add_command(label="退出", command=self.close_app)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _start_drag(self, event):
        if self._collapsed:
            return
        self._drag = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _do_drag(self, event):
        if not self._drag or self._collapsed:
            return
        x = event.x_root - self._drag[0]
        y = event.y_root - self._drag[1]
        self.geometry("+%d+%d" % (x, y))

    def _end_drag(self, _event):
        if not self._drag:
            return
        self._drag = None
        left, top, right, bottom = self.work
        x, y = self.winfo_x(), self.winfo_y()
        if right - (x + self.W) < 24:
            x = right - self.W - 12
        if x < left:
            x = left
        if y < top:
            y = top
        if y + 80 > bottom:
            y = bottom - 120
        self.geometry("+%d+%d" % (x, y))
        self.store.settings()["window_x"] = x
        self.store.settings()["window_y"] = y
        self.store.save()

    def collapse(self):
        if self._collapsed:
            return
        self._expanded_geom = (
            self.winfo_x(), self.winfo_y(), self.winfo_width(), self.winfo_height()
        )
        self._collapsed_moved = False
        self._edge_drag = None
        self.outer.pack_forget()
        self.edge.pack(fill="both", expand=True)
        _, top, right, bottom = self.work
        y = max(top + 80, min(self.winfo_y(), bottom - 260))
        self.geometry("38x220+%d+%d" % (right - 38, y))
        self.attributes("-topmost", True)
        self._collapsed = True
        self._update_edge_count()

    def expand(self):
        if not self._collapsed:
            return
        self.edge.pack_forget()
        self.outer.pack(fill="both", expand=True)
        if self._expanded_geom:
            old_x, old_y, w, h = self._expanded_geom
            if self._collapsed_moved:
                left, top, right, bottom = self.work
                tab_x, tab_y = self.winfo_x(), self.winfo_y()
                if tab_x + 19 > (left + right) / 2:
                    old_x = tab_x + 38 - w
                else:
                    old_x = tab_x
                old_y = tab_y
                old_x = max(left, min(old_x, right - w))
                old_y = max(top, min(old_y, bottom - h))
            self.geometry("%dx%d+%d+%d" % (w, h, old_x, old_y))
        else:
            x, y = self._initial_position()
            self.geometry("%dx%d+%d+%d" % (self.W, self.H, x, y))
        self._collapsed = False
        self._collapsed_moved = False
        self.attributes("-topmost", bool(self.store.settings().get("topmost", True)))

    def _update_edge_count(self):
        active = model.counts(self.store.tasks)["active"]
        self.edge_count.configure(text=str(active))

    def toggle_pin(self):
        value = not bool(self.store.settings().get("topmost", True))
        self.store.set_setting("topmost", value)
        self.set_pin(value)

    def set_pin(self, value):
        self.attributes("-topmost", bool(value))
        self.pin_btn.set_text("已置顶" if value else "置顶")
        self.pin_btn.set_kind("soft" if value else "ghost")
        if hasattr(self.pages.get("settings"), "topmost_toggle"):
            self.pages["settings"].topmost_toggle.set(bool(value))

    # --------------------------------------------------------------- globals
    def _bind_global(self):
        self.bind_all("<MouseWheel>", self._on_wheel, add="+")
        self.bind_all("<Control-n>", lambda _e: self.new_task(), add="+")
        self.bind_all("<Control-N>", lambda _e: self.new_task(), add="+")
        self.bind_all("<Escape>", self._escape, add="+")
        self.bind("<FocusIn>", self._focus_expand, add="+")
        self.protocol("WM_DELETE_WINDOW", self.close_app)

    def _focus_expand(self, _event=None):
        if self._collapsed:
            self.after(40, self.expand)

    def _on_wheel(self, event):
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget is None:
            return
        try:
            if widget.winfo_class() in ("Text", "Listbox"):
                return
        except Exception:
            return
        current = widget
        while current is not None:
            if isinstance(current, ScrollFrame):
                current.scroll(event.delta)
                return
            current = getattr(current, "master", None)

    def _escape(self, _event=None):
        if self._modals:
            self._modals[-1].request_close()
            return "break"
        if self._collapsed:
            self.expand()

    def switch_page(self, key, refresh=True):
        if key not in self.pages:
            return
        if self._modals:
            return
        self.current_page = key
        self.pages[key].tkraise()
        for name, item in self.nav_items.items():
            item.set_active(name == key)
        if refresh:
            self.pages[key].on_show()
        self.toast.hide()

    def refresh(self, all_pages=False):
        """Rebuild visible data. Modal contents hold their own working copies."""
        if not self._running:
            return
        try:
            if all_pages:
                for page in self.pages.values():
                    if hasattr(page, "refresh"):
                        page.refresh()
            else:
                page = self.pages.get(self.current_page)
                if page is not None and hasattr(page, "refresh"):
                    page.refresh()
            self.pages["settings"]._refresh_status()
        except tk.TclError:
            pass
        if self._collapsed:
            self._update_edge_count()

    def toast_message(self, text, kind="info"):
        self.toast.show(text, kind)

    toast = None  # replaced in __init__ after Toast creation

    # ----------------------------------------------------------------- modals
    def register_modal(self, modal):
        self._modals.append(modal)

    def unregister_modal(self, modal):
        if modal in self._modals:
            self._modals.remove(modal)

    def _close_modals(self):
        for modal in list(reversed(self._modals)):
            try:
                modal.force_close()
            except Exception:
                try:
                    modal.destroy()
                except Exception:
                    pass
        self._modals = []

    def confirm(self, title, message, ok_text="确定", on_ok=None, danger=False):
        result = messagebox.askyesno(
            title if not danger else "请确认",
            message,
            parent=self,
            icon="warning" if danger else "question",
            default="no",
        )
        if result and on_ok:
            on_ok()
        return result

    def new_task(self):
        if self._modals:
            return
        self.open_task_editor()

    def show_tasks(self, task_ids, note=""):
        page = self.pages.get("tasks")
        if page is None:
            return
        page.show_subset(task_ids, note)
        self.switch_page("tasks")

    def owner_options(self):
        """Owner choices: self + configured people + accepted friends only.

        Task cards from old data may contain arbitrary owner strings; they must
        not pollute the dropdown. Existing task owners stay visible on the task
        itself and as the selected value when editing that task.
        """
        options = []
        seen = set()

        def add(name, username="", source="local"):
            name = (name or "").strip()
            username = (username or "").strip()
            if not name:
                return
            key = username.casefold() if username else name.casefold()
            if key in seen:
                return
            seen.add(key)
            options.append({"display_name": name, "username": username, "source": source})

        data = getattr(self, "collab_data", None) or {}
        me = data.get("user") or {}
        if me:
            add(me.get("display_name") or me.get("username"), me.get("username"), "self")
        for owner in self.store.owner_directory():
            name = owner.get("name") or ""
            if any(char in name for char in "、,，/;；"):
                continue
            if owner.get("active", True):
                add(name, owner.get("username"), "local")
        org_unit_id = data.get("org_unit_id")
        if org_unit_id:
            for peer in data.get("owner_scope") or []:
                add(peer.get("display_name") or peer.get("username"),
                    peer.get("username"), "org")
        else:
            for friend in data.get("friends") or []:
                if friend.get("status", "active") == "active":
                    add(friend.get("display_name") or friend.get("username"),
                        friend.get("username"), "friend")
        return options

    def update_task_status(self):
        if not self.collab_user or not self.store.collab_token():
            self.toast.show("请先登录主管理服务，再更新任务状态", "warn", 3600)
            return
        self.toast.show("正在更新任务状态…", "info", 2400)
        self.collab_sync(silent=False)

    def _show_incoming_messages(self, messages):
        if self._message_dialog is not None:
            return
        ids = [message.get("id") for message in messages if message.get("id")]
        client = self._collab_client()
        if client and ids:
            self.run_async(lambda: client.messages_read(ids), None, None)
        self._message_dialog = MessageDialog(self, messages)

    def reply_message(self, message_id, body):
        client = self._collab_client()
        if not client:
            self.toast.show("请先登录主管理服务", "warn")
            return

        def success(_result):
            self.toast.show("回复已发送", "success")

        def failure(exc):
            self.toast.show(truncate(str(exc), 80), "error")

        self.run_async(lambda: client.reply_message(message_id, body), success, failure)

    def load_message_threads(self, callback, failure=None):
        client = self._collab_client()
        if not client:
            if failure:
                failure("请先登录主管理服务")
            return
        self.run_async(lambda: client.message_threads(), callback, failure)

    def open_message_inbox(self):
        if not self.collab_user or not self.store.collab_token():
            self.toast.show("请先登录主管理服务", "warn", 3600)
            return
        MessageInboxDialog(self)

    def resolve_ai_owner(self, owner_text):
        """Only assign an AI owner when the name maps to a real account."""
        raw = (owner_text or "").strip()
        if not raw or raw in ("待指派", "未指定", "待定"):
            return "待指派", ""
        if any(char in raw for char in "、,，/;；"):
            return "待指派", ""
        key = raw.casefold()
        for option in self.owner_options():
            username = (option.get("username") or "").strip()
            if not username:
                continue
            names = {(option.get("display_name") or "").strip().casefold(),
                     username.casefold()}
            if key in names:
                return (option.get("display_name") or username), username
        return "待指派", ""

    def choose_parent_for_task(self, task):
        from .page_mail import ParentTaskDialog
        ParentTaskDialog(self, lambda parent: self.convert_task_to_subtask(task, parent),
                         exclude_id=task.get("id"))

    def convert_task_to_subtask(self, task, parent):
        if not task or not parent or task.get("id") == parent.get("id"):
            return
        sub = model.add_subtask(
            parent, task.get("title") or "未命名子任务",
            start=task.get("start"), due=task.get("due"),
            owner=task.get("owner") or "", owner_username=task.get("owner_username") or "",
        )
        if sub and task.get("completed"):
            sub["done"] = True
            sub["done_at"] = task.get("completed_at") or model.iso(model.now())
        for child in task.get("subtasks") or []:
            child_sub = model.add_subtask(
                parent, child.get("title") or "未命名子任务",
                start=child.get("start"), due=child.get("due"),
                owner=child.get("owner") or "", owner_username=child.get("owner_username") or "",
            )
            if child_sub and child.get("done"):
                child_sub["done"] = True
                child_sub["done_at"] = child.get("done_at") or model.iso(model.now())
        model.add_note(parent, "由任务「%s」转换为子任务" % (task.get("title") or ""),
                       email_id=task.get("source_email_id"))
        task["archived"] = True
        task["archived_at"] = model.iso(model.now())
        task["converted_to_subtask_parent_id"] = parent.get("id")
        parent["completed"] = False
        self.store.save()
        self.refresh()
        self.toast.show("已转为「%s」的子任务" % truncate(parent.get("title") or "", 20),
                        "success", 3200)

    def choose_parent_for_ai_project(self, project, email):
        from .page_mail import ParentTaskDialog
        ParentTaskDialog(self, lambda parent: self.add_ai_project_subtask(project, email, parent))

    def add_ai_project_subtask(self, project, email, parent):
        owner_name, owner_username = self.resolve_ai_owner(project.get("owner"))
        sub = model.add_subtask(
            parent, project.get("subtask_title") or project.get("title") or "AI 子任务",
            due=project.get("due"), owner=owner_name, owner_username=owner_username,
            requirement=analyzer.ai_subtask_requirement(project),
        )
        if sub and project.get("completed"):
            sub["done"] = True
        model.add_note(parent, "AI 邮件项目转为子任务：%s" % (
            project.get("requirement") or project.get("summary") or ""),
            email_id=email.get("id"))
        project["task_id"] = parent.get("id")
        project["target_task_id"] = parent.get("id")
        project["applied_action"] = "subtask"
        project["applied_at"] = model.iso(model.now())
        project["ignored"] = False
        email["analysis"] = email.get("analysis") or {}
        self.store.link_email_many(
            email.get("id"), [parent.get("id")],
            note="AI 邮件关联：%s" % truncate(email.get("subject", ""), 30))
        self.store.save()
        self.refresh()
        AIProjectSummaryDialog(self, email)
        self.toast.show("已添加为「%s」的子任务" % truncate(parent.get("title") or "", 20),
                        "success", 3200)

    def refresh_owner_scope(self):
        if not self.collab_user or not self.store.collab_token():
            self.toast.show("请先登录主管理服务，再更新负责人范围", "warn", 3600)
            return
        self.toast.show("正在更新负责人范围…", "info", 2400)

        def done(data, error):
            if error:
                self.toast.show(truncate(error, 80), "error", 4200)
                return
            page = self.pages.get("settings")
            if page is not None and hasattr(page, "_render_owners"):
                page._render_owners()
            scope = len((data or {}).get("owner_scope") or [])
            self.toast.show("负责人范围已更新（%d 个账户）" % scope, "success", 3000)

        self.collab_refresh(done)

    def open_task_editor(self, task=None, prefill=None, on_saved=None):
        scope = None
        if task is not None and task.get("share_group_id") and self.collab_user:
            scope = "group:%s" % task.get("share_group_id")
            client = self._collab_client()
            if client:
                try:
                    result = client.acquire_task_lock(scope)
                    server_revision = int((result or {}).get("revision") or 0)
                    local_revision = int(task.get("revision") or 0)
                    if local_revision != server_revision:
                        client.release_task_lock(scope)
                        self.toast.show("任务已更新，请先点「状态更新」后再编辑", "warn", 4600)
                        return
                    self._task_locks[scope] = True
                except CollabError as exc:
                    message = str(exc)
                    if "编辑中" not in message:
                        message = "无法进入共享任务编辑：" + message
                    self.toast.show(message, "warn", 4600)
                    return
                except Exception as exc:
                    self.toast.show("无法锁定共享任务：%s" % exc, "warn", 4200)
                    return
        if self._modals:
            self._close_modals()
        TaskEditor(self, task=task, prefill=prefill, on_saved=on_saved,
                   on_close=(lambda: self._release_task_lock(scope)) if scope else None)

    def _release_task_lock(self, scope):
        if not scope or not self._task_locks.pop(scope, None):
            return
        client = self._collab_client()
        if not client:
            return
        self.run_async(lambda: client.release_task_lock(scope),
                       lambda _result: None, lambda _exc: None)

    def push_shared_task(self, task):
        if not task.get("share_group_id") or not self.collab_user:
            return True
        client = self._collab_client()
        if not client:
            self.toast.show("协作网络未连接，无法保存共享任务", "warn", 4200)
            return False
        scope = "group:%s" % task.get("share_group_id")
        try:
            result = client.update_shared_task(
                scope, task, int(task.get("revision") or 0))
        except CollabError as exc:
            self.toast.show(str(exc), "warn", 4600)
            return False
        except Exception as exc:
            self.toast.show("共享任务保存失败：%s" % exc, "warn", 4200)
            return False
        task["revision"] = int((result or {}).get("revision") or 0)
        task["updated_at"] = (result or {}).get("updated_at") or task.get("updated_at")
        return True

    def toggle_task_complete(self, task):
        if task.get("completed"):
            model.reopen(task)
            message = "任务已恢复"
        else:
            if task.get("lost"):
                model.reopen_lost(task)
                task["tags"] = [tag for tag in (task.get("tags") or []) if tag != "lost"]
            try:
                model.mark_complete(task)
            except model.CompletionBlocked as exc:
                self.toast.show("还有 %d 个子任务未完成，请先完成子任务" % exc.pending,
                                "warn", 4200)
                return False
            message = "任务已完成"
        self.store.save()
        self.refresh()
        self.schedule_collab_sync()
        self.toast.show(message, "success", 2600)
        return True

    def toggle_task_lost(self, task):
        if task.get("lost"):
            model.reopen_lost(task)
            task["tags"] = [tag for tag in (task.get("tags") or []) if tag != "lost"]
            task["updated_at"] = model.iso(model.now())
            self.store.save()
            self.refresh()
            self.toast.show("已恢复任务，不再标记流失", "info", 2600)
            return True
        LostReasonDialog(self, task, lambda reason: self.mark_task_lost(task, reason))
        return True

    def mark_task_lost(self, task, reason):
        model.mark_lost(task, reason=reason)
        tags = [tag for tag in (task.get("tags") or []) if tag not in ("lost", "suspect")]
        tags.append("lost")
        task["tags"] = model.clean_tags(tags)
        task["updated_at"] = model.iso(model.now())
        self.store.save()
        self.refresh()
        self.toast.show("任务已标记为流失", "success", 2600)
        return True

    def toggle_task_suspect(self, task):
        self.toast.show("疑似流失已取消，请直接使用标记流失", "info", 2600)
        return False

    def open_task_view(self, task):
        if not task:
            return
        if self._modals:
            self._close_modals()
        TaskView(self, task)

    # ------------------------------------------------------------------ mail
    def open_mail_detail(self, email):
        if self._modals:
            return
        if not email.get("read"):
            email["read"] = True
            self.store.save()
        MailDetail(self, email)

    def open_mail_by_id(self, email_id):
        if self._modals:
            self.toast.show("请先关闭当前弹层，再到邮件页查看原邮件", "warn")
            return
        email = self.store.email(email_id)
        if email:
            self.open_mail_detail(email)
        else:
            self.toast.show("原邮件已不在收件箱中", "warn")

    def create_task_from_email(self, email):
        analysis = email.get("analysis") or {}
        self._close_modals()
        owner_name, owner_username = self.resolve_ai_owner(analysis.get("owner"))
        prefill = {
            "title": analysis.get("title") or email.get("subject") or "",
            "requirement": analysis.get("requirement") or "",
            "due": analysis.get("due"),
            "owner": owner_name,
            "owner_username": owner_username,
            "progress": analysis.get("progress") or 0,
            "source_email_id": email.get("id"),
        }
        self.open_task_editor(prefill=prefill)

    def ai_ready(self):
        return bool(analyzer.ai_config(self.store))

    def _show_ai_progress(self, email):
        self._ai_started = time.monotonic()
        if self._ai_progress_frame is None:
            frame = tk.Frame(self, bg=COLORS["dark"], highlightthickness=1,
                             highlightbackground=COLORS["dark_line"])
            frame.place(relx=0.5, y=72, anchor="n", width=360, height=42)
            label = tk.Label(frame, text="", bg=COLORS["dark"], fg=COLORS["white"],
                             font=("Microsoft YaHei UI", 8, "bold"), anchor="w")
            label.pack(side="left", fill="x", expand=True, padx=(10, 6))
            canvas = tk.Canvas(frame, width=92, height=6, bg=COLORS["dark"],
                               highlightthickness=0, bd=0)
            canvas.pack(side="right", padx=(0, 10))
            self._ai_progress_frame = frame
            self._ai_progress_label = label
            self._ai_progress_canvas = canvas
        self._ai_progress_label.configure(
            text="AI 分析中 · " + truncate(email.get("subject", ""), 22))
        self._ai_progress_frame.lift()
        self._tick_ai_progress()

    def _tick_ai_progress(self):
        if not self._ai_busy or self._ai_progress_frame is None:
            self._hide_ai_progress()
            return
        elapsed = int(time.monotonic() - (self._ai_started or time.monotonic()))
        self._ai_progress_label.configure(
            text="AI 分析中 · %ds · 可继续其他操作" % elapsed)
        canvas = self._ai_progress_canvas
        canvas.delete("all")
        canvas.create_rectangle(0, 0, 92, 6, fill=COLORS["dark_line"], outline="")
        offset = int((elapsed * 38) % 132) - 40
        canvas.create_rectangle(max(0, offset), 0, min(92, offset + 40), 6,
                                fill=COLORS["accent"], outline="")
        self._ai_progress_after = self.after(120, self._tick_ai_progress)

    def _hide_ai_progress(self):
        if self._ai_progress_after is not None:
            try:
                self.after_cancel(self._ai_progress_after)
            except Exception:
                pass
            self._ai_progress_after = None
        if self._ai_progress_frame is not None:
            self._ai_progress_frame.place_forget()
        self._ai_started = None

    def ai_create_task_from_email(self, email):
        if self._ai_busy:
            self.toast.show("AI 正在分析上一封邮件，请稍候", "info")
            return
        existing = email.get("analysis") or {}
        if existing.get("projects"):
            AIProjectSummaryDialog(self, email)
            return
        config = analyzer.ai_config(self.store)
        if not config:
            self.toast.show("请先在设置中启用 AI 邮件分析并填写 API Key", "warn", 4200)
            self.switch_page("settings")
            return
        self._ai_busy = True
        self._show_ai_progress(email)

        def success(analysis):
            self._ai_busy = False
            self._hide_ai_progress()
            email["analysis"] = analysis
            email["read"] = True
            self.store.save()
            self.refresh()
            if analysis.get("projects"):
                detail_open = any(
                    isinstance(modal, MailDetail) and modal.email is email
                    for modal in self._modals
                )
                if self.current_page == "mail" and detail_open:
                    AIProjectReviewDialog(self, email, analysis)
                else:
                    self.toast.show(
                        "AI 分析完成：%d 个项目。打开邮件详情点「AI 建任务」查看"
                        % len(analysis["projects"]), "success", 6000)
            else:
                self.toast.show("AI 判断这封邮件没有需要创建或更新的项目", "info", 4200)

        def failure(exc):
            self._ai_busy = False
            self._hide_ai_progress()
            self.toast.show(truncate(str(exc), 90), "error", 5200)

        self.run_async(lambda: analyzer.analyze_email_ai(
            email, config, tasks=self.store.active_tasks(),
            previous_emails=self.store.emails), success, failure)

    @staticmethod
    def _project_key(title):
        return re.sub(r"[\s\W_]+", "", (title or "").lower())

    def _reset_deleted_ai_project(self, project):
        project["task_id"] = None
        project["applied_action"] = None
        project["applied_at"] = None
        project["task_deleted"] = False
        project["task_deleted_at"] = None

    def _merge_rescan(self, email, analysis):
        old_projects = [p for p in ((email.get("analysis") or {}).get("projects") or [])
                        if isinstance(p, dict)]
        old_by_key = {self._project_key(p.get("title")): p for p in old_projects}
        used = set()
        projects = []
        updated = 0
        for project in analysis.get("projects") or []:
            key = self._project_key(project.get("title"))
            match = old_by_key.get(key)
            if match is None and key:
                for old_key, candidate in old_by_key.items():
                    if old_key and (key in old_key or old_key in key):
                        match = candidate
                        break
            if match is not None:
                used.add(id(match))
                old_task = self.store.task(match.get("task_id")) if match.get("task_id") else None
                if match.get("task_id") and old_task is None:
                    # The linked task was deleted: show the project as pending again.
                    self._reset_deleted_ai_project(project)
                else:
                    for field in ("task_id", "applied_action", "applied_at", "ignored",
                                  "task_deleted", "task_deleted_at"):
                        if match.get(field) is not None:
                            project[field] = match.get(field)
                    if old_task is not None and not old_task.get("archived"):
                        new_requirement = project.get("requirement") or ""
                        if new_requirement and new_requirement != old_task.get("requirement"):
                            old_task["requirement"] = new_requirement
                            old_task["updated_at"] = model.iso(model.now())
                            updated += 1
            projects.append(project)
        for old in old_projects:
            if id(old) not in used:
                if old.get("task_id") and self.store.task(old.get("task_id")) is None:
                    old = dict(old)
                    self._reset_deleted_ai_project(old)
                projects.append(old)
        analysis["projects"] = projects
        analysis["rescanned_at"] = model.iso(model.now())
        return analysis, updated

    def rescan_email(self, email):
        if self._ai_busy:
            self.toast.show("AI 正在分析邮件，请稍候", "info")
            return
        config = analyzer.ai_config(self.store)
        if not config:
            self.toast.show("请先在设置中启用 AI 邮件分析并填写 API Key", "warn", 4200)
            self.switch_page("settings")
            return
        self._ai_busy = True
        self._show_ai_progress(email)

        def success(analysis):
            self._ai_busy = False
            self._hide_ai_progress()
            merged, updated = self._merge_rescan(email, analysis)
            email["analysis"] = merged
            email["read"] = True
            self.store.save()
            self.refresh()
            AIProjectSummaryDialog(self, email)
            if updated:
                self.toast.show("复扫完成，已更新 %d 个任务内容" % updated, "success", 4200)
            else:
                self.toast.show("复扫完成，项目清单已更新", "success", 4200)

        def failure(exc):
            self._ai_busy = False
            self._hide_ai_progress()
            self.toast.show(truncate(str(exc), 90), "error", 5200)

        self.run_async(lambda: analyzer.analyze_email_ai(
            email, config, tasks=self.store.active_tasks(),
            previous_emails=self.store.emails), success, failure)

    def apply_mail_update(self, email):
        analysis = email.get("analysis") or {}
        task = None
        if analysis.get("linked_task_id"):
            task = self.store.task(analysis["linked_task_id"])
        if task is None and analysis.get("matches"):
            task = self.store.task(analysis["matches"][0].get("task_id"))
        if task is None:
            self.toast.show("找不到可更新的任务，请先创建或关联", "warn")
            return

        changes = []
        warning = ""
        due = model.parse_dt(analysis.get("due"))
        if due:
            old_due = model.parse_dt(task.get("due"))
            if old_due != due:
                start = model.parse_dt(task.get("start"))
                if start and due < start:
                    task["start"] = model.iso(due - timedelta(hours=1))
                task["due"] = model.iso(due)
                changes.append("截止 %s" % due.strftime("%m/%d %H:%M"))

        progress = analysis.get("progress")
        if progress is not None:
            old_progress = int(task.get("progress") or 0)
            if int(progress) > old_progress:
                value = model.set_progress(task, progress)
                changes.append("进度 %d%%" % value)
                if progress >= 100 and value < 100:
                    warning = "邮件称已完成，但还有子任务未完成，进度停在 %d%%" % value

        if analysis.get("done_hint"):
            if model.all_subtasks_done(task):
                model.mark_complete(task)
                changes.append("已完成")
            else:
                pending = len(model.pending_subtasks(task))
                warning = "邮件称已交付，但还有 %d 个子任务未完成，任务保持未完成" % pending

        note = "邮件《%s》更新：%s" % (
            truncate(email.get("subject", ""), 28),
            analysis.get("summary") or "已记录邮件内容",
        )
        model.add_note(task, note, email_id=email.get("id"))
        model.link_email(task, email["id"])
        email["read"] = True
        if not isinstance(email.get("analysis"), dict):
            email["analysis"] = {}
        email["analysis"]["linked_task_id"] = task["id"]
        self.store.save()
        self._close_modals()
        self.refresh()
        if warning:
            self.toast.show(warning, "warn", 3600)
        elif changes:
            self.toast.show("已更新「%s」：%s" % (truncate(task["title"], 12), "，".join(changes)),
                            "success", 3200)
        else:
            self.toast.show("已把邮件记录到「%s」" % truncate(task["title"], 14), "success")
        self.schedule_collab_sync()

    def link_email_to_task(self, email, task):
        self.store.link_email(email["id"], task["id"],
                              note="关联邮件：%s" % truncate(email.get("subject", ""), 30))
        self._close_modals()
        self.refresh()
        self.toast.show("已关联到「%s」" % truncate(task.get("title", ""), 14), "success")

    def unlink_email_from_task(self, email):
        self.store.unlink_email(email["id"])
        self._close_modals()
        self.refresh()
        self.toast.show("已取消邮件关联，邮件仍保留在收件箱", "info")

    def open_link_dialog(self, email):
        LinkTaskDialog(self, email)

    # ------------------------------------------------------------ collaboration
    def _collab_client(self):
        if not self.collab_user:
            return None
        token = self.store.collab_token()
        if not token:
            return None
        return CollabClient(self.store.settings().get("collab_server"), token)

    def _refresh_collab_page(self):
        page = self.pages.get("collab") if hasattr(self, "pages") else None
        if page is not None:
            try:
                page.refresh()
            except tk.TclError:
                pass

    def collab_connect(self, server, username, password, register=False, display_name=""):
        if self.collab_busy:
            return
        try:
            server = normalize_server(server)
        except CollabError as exc:
            self.collab_error = str(exc)
            self._refresh_collab_page()
            return
        self.collab_busy = True
        self.collab_error = ""
        self._refresh_collab_page()
        client = CollabClient(server)

        def work():
            if register:
                return client.register(username, password, display_name)
            return client.login(username, password)

        def success(result):
            self.collab_busy = False
            self.store.set_collab_session(result.get("token", ""), result.get("user", {}), server)
            self.collab_user = self.store.collab_user()
            self.collab_data = None
            self.collab_error = ""
            self.refresh()
            self.toast.show("已登录协作网络", "success")
            self.collab_refresh()
            self.collab_heartbeat()

        def failure(exc):
            self.collab_busy = False
            self.collab_error = str(exc)
            self._refresh_collab_page()
            self.toast.show(truncate(str(exc), 80), "error", 4200)

        self.run_async(work, success, failure)

    def collab_logout(self):
        client = self._collab_client()
        if client:
            self.run_async(client.logout, None, None)
        self.store.clear_collab_session()
        self.collab_user = None
        self.collab_data = None
        self.collab_error = ""
        self.refresh()
        self.toast.show("已退出协作网络", "info")

    def collab_refresh(self, on_done=None):
        if self.collab_refreshing:
            return
        client = self._collab_client()
        if not client:
            if on_done:
                on_done(None, "请先登录主管理服务")
            return
        self.collab_refreshing = True

        def success(data):
            self.collab_refreshing = False
            self.collab_data = data
            self.collab_error = ""
            self._refresh_collab_page()
            if on_done:
                on_done(data, None)

        def failure(exc):
            self.collab_refreshing = False
            if isinstance(exc, CollabError) and exc.status == 401:
                self.store.clear_collab_session()
                self.collab_user = None
                self.collab_data = None
            self.collab_error = str(exc)
            self._refresh_collab_page()
            if on_done:
                on_done(None, str(exc))

        def work():
            data = client.collab()
            if (data.get("user") or {}).get("role") == "admin":
                try:
                    data["admin_overview"] = client.overview()
                except CollabError as exc:
                    data["admin_error"] = str(exc)
            return data

        self.run_async(work, success, failure)

    def collab_heartbeat(self):
        """Lightweight online/collect check; never rebuilds the UI by itself."""
        if self._collect_checking or not self.collab_user or not self.store.collab_token():
            return
        client = self._collab_client()
        if not client:
            return
        self._collect_checking = True

        def success(data):
            self._collect_checking = False
            messages = data.get("messages") or []
            if messages:
                self._show_incoming_messages(messages)
            try:
                epoch = int(data.get("epoch") or 0)
            except (TypeError, ValueError):
                epoch = 0
            if epoch < self._collect_seen:
                # Server restart resets the in-memory epoch.
                self._collect_seen = 0
            if epoch > self._collect_seen:
                if self.collab_syncing:
                    return
                self._collect_seen = epoch
                self.collab_sync(silent=True)

        def failure(exc):
            self._collect_checking = False
            if isinstance(exc, CollabError) and exc.status == 401:
                self.store.clear_collab_session()
                self.collab_user = None
                self.collab_data = None
                self._refresh_collab_page()

        self.run_async(lambda: client.collect_status(), success, failure)

    def collab_sync(self, silent=False):
        if self.collab_syncing:
            return
        client = self._collab_client()
        if not client:
            if not silent:
                self.switch_page("collab")
                self.toast.show("请先登录主管理服务", "warn")
            return
        self.collab_syncing = True
        tasks = list(self.store.tasks)
        deleted_ids = list(self.store.deleted_task_ids)

        def work():
            return client.sync(tasks, deleted_ids)

        def success(result):
            self.collab_syncing = False
            added, updated = self.store.merge_server_tasks(
                result.get("tasks") or [],
                result.get("accepted_deleted_ids") or [],
            )
            self.store.settings()["collab_last_sync"] = model.iso(model.now())
            if added or updated:
                self.store.save()
            self.collab_error = ""
            if added or updated or not silent:
                self.refresh()
            if not silent:
                self.collab_refresh()
            elif self.current_page == "collab" and (
                    time.monotonic() - self._collab_meta_last >= 30):
                self._collab_meta_last = time.monotonic()
                self.collab_refresh()
            if not silent:
                self.toast.show("协作数据已同步", "success")

        def failure(exc):
            self.collab_syncing = False
            if isinstance(exc, CollabError) and exc.status == 401:
                self.store.clear_collab_session()
                self.collab_user = None
                self.collab_data = None
            self.collab_error = str(exc)
            self._refresh_collab_page()
            if not silent:
                self.toast.show(truncate(str(exc), 80), "error", 4200)

        self.run_async(work, success, failure)

    def schedule_collab_sync(self):
        # Client-initiated task pushes are disabled. The admin terminal collects
        # tasks explicitly; the client only answers its collect heartbeat.
        return

    def collab_add_friend(self, username, on_done=None):
        client = self._collab_client()
        if not client:
            if on_done:
                on_done("请先登录")
            return

        def success(result):
            message = "已自动互相添加为好友" if result.get("auto_accepted") else "好友申请已发送"
            self.toast.show(message, "success")
            self.collab_refresh()
            if on_done:
                on_done(message)

        def failure(exc):
            if on_done:
                on_done(str(exc))
            self.toast.show(truncate(str(exc), 80), "error")

        self.run_async(lambda: client.add_friend(username), success, failure)

    def collab_respond_friend(self, request_id, accept):
        client = self._collab_client()
        if not client:
            return

        def success(_result):
            self.toast.show("已接受好友申请" if accept else "已忽略好友申请", "success")
            self.collab_refresh()

        def failure(exc):
            self.toast.show(truncate(str(exc), 80), "error")

        self.run_async(lambda: client.respond_friend(request_id, accept), success, failure)

    def collab_respond_offer(self, offer_id, accept):
        client = self._collab_client()
        if not client:
            return

        def success(result):
            task = result.get("task")
            if accept and task:
                self.store.merge_server_tasks([task], [])
                self.store.save()
            self.toast.show("任务已接收到本地" if accept else "已拒绝任务邀请", "success")
            self.refresh()
            self.collab_refresh()

        def failure(exc):
            self.toast.show(truncate(str(exc), 80), "error")
            self._refresh_collab_page()

        self.run_async(lambda: client.respond_offer(offer_id, accept), success, failure)

    def forward_task_async(self, task_id, friend_id, mode, message, on_success=None, on_error=None):
        client = self._collab_client()
        if not client:
            if on_error:
                on_error("请先登录协作网络")
            return

        def success(result):
            self.collab_refresh()
            if on_success:
                on_success(result)

        def failure(exc):
            if on_error:
                on_error(str(exc))

        self.run_async(
            lambda: client.forward_task(task_id, friend_id, mode, message),
            success, failure,
        )

    def forward_tasks_async(self, task_ids, friend_id, mode, message,
                            on_success=None, on_error=None):
        client = self._collab_client()
        if not client:
            if on_error:
                on_error("请先登录协作网络")
            return

        def success(results):
            self.collab_refresh()
            if on_success:
                on_success(results)

        def failure(exc):
            if on_error:
                on_error(str(exc))

        def work():
            return [client.forward_task(task_id, friend_id, mode, message)
                    for task_id in task_ids]

        self.run_async(work, success, failure)

    def open_friend_chat(self, friend):
        if not self.collab_user:
            self.switch_page("collab")
            self.toast.show("请先登录协作网络", "warn")
            return
        FriendChatDialog(self, friend)

    def load_friend_messages(self, friend_id, on_success=None, on_error=None):
        client = self._collab_client()
        if not client:
            if on_error:
                on_error("请先登录协作网络")
            return
        self.run_async(
            lambda: client.friend_messages(friend_id),
            lambda result: on_success((result or {}).get("messages") or []) if on_success else None,
            lambda exc: on_error(str(exc)) if on_error else None,
        )

    def send_friend_message(self, friend_id, body, on_success=None, on_error=None):
        client = self._collab_client()
        if not client:
            if on_error:
                on_error("请先登录协作网络")
            return
        self.run_async(
            lambda: client.send_friend_message(friend_id, body),
            on_success, lambda exc: on_error(str(exc)) if on_error else None,
        )

    def open_forward_dialog(self, task=None, friend=None):
        if not self.collab_user:
            self.switch_page("collab")
            self.toast.show("请先登录协作网络", "warn")
            return
        if not self.collab_data:
            self.collab_refresh()
            self.toast.show("正在加载好友，请稍后再试", "info")
            return
        friends = self.collab_data.get("friends") or []
        if not friends:
            self.switch_page("collab")
            self.toast.show("还没有好友，请先添加好友", "warn")
            return
        ForwardDialog(self, task=task, friend=friend)

    def open_global_tasks(self):
        if not self.collab_user or (self.collab_user or {}).get("role") != "admin":
            return
        GlobalTasksModal(self)

    def open_ai_settings(self):
        self.switch_page("settings")
        page = self.pages.get("settings")
        if page is not None:
            page.focus_ai()

    def _collab_tick(self):
        if not self._running:
            return
        if self.collab_user and self.store.collab_token():
            self.collab_heartbeat()
        self._collab_after = self.after(10000, self._collab_tick)

    # ------------------------------------------------------------------ sync
    def _mail_credentials(self):
        settings = self.store.settings()
        account = settings.get("account", "")
        password = self.store.password()
        if not account or not password:
            return None
        return {
            "host": settings.get("imap_host", "imap.em.dingtalk.com"),
            "port": settings.get("imap_port", 993),
            "account": account,
            "password": password,
            "days": settings.get("days", 14),
        }

    def sync_mail(self):
        if self.syncing:
            self.toast.show("正在同步，请稍候", "info")
            return
        creds = self._mail_credentials()
        if not creds:
            self.switch_page("settings")
            self.toast.show("请先填写邮箱账号和专用密码", "warn")
            return
        self.syncing = True
        if self.current_page == "mail":
            self.pages["mail"].refresh()
        self.pages["settings"]._refresh_status()

        def work():
            client = mailer.MailClient(creds["host"], creds["port"], creds["account"],
                                       creds["password"], days=creds["days"])
            try:
                return client.fetch()
            finally:
                client.close()

        def success(messages):
            self.syncing = False
            added, updated = self.store.merge_emails(messages)
            analyzer.ensure_analyses(self.store)
            settings = self.store.settings()
            settings["last_sync"] = model.iso(model.now())
            settings["last_sync_error"] = ""
            self.store.save()
            self.refresh()
            text = "同步完成：新增 %d 封，更新 %d 封" % (added, updated)
            self.toast.show(text, "success", 3200)

        def failure(exc):
            self.syncing = False
            message = str(exc)
            self.store.settings()["last_sync_error"] = message
            self.store.save()
            self.refresh()
            self.toast.show(truncate(message, 90), "error", 4200)

        self.run_async(work, success, failure)

    def test_mail(self, button, label):
        creds = self._mail_credentials()
        if not creds:
            self.toast.show("请先保存邮箱账号和专用密码", "warn")
            return

        def work():
            return mailer.check_connection(creds["host"], creds["port"],
                                           creds["account"], creds["password"])

        def success(_value):
            button.set_disabled(False)
            label.configure(text="连接成功，可以读取收件箱", fg=COLORS["mint"])
            self.toast.show("邮箱连接成功", "success")

        def failure(exc):
            button.set_disabled(False)
            label.configure(text=truncate(str(exc), 100), fg=COLORS["danger"])
            self.toast.show(truncate(str(exc), 80), "error", 4000)

        self.run_async(work, success, failure)

    def import_eml(self):
        paths = filedialog.askopenfilenames(
            parent=self,
            title="导入邮件文件",
            filetypes=[("邮件文件", "*.eml"), ("所有文件", "*.*")],
        )
        if not paths:
            return
        added = 0
        errors = []
        for path in paths:
            try:
                email_data = mailer.import_eml(path)
                if any(e.get("id") == email_data["id"] for e in self.store.emails):
                    continue
                email_data["analysis"] = analyzer.analyze_email(email_data, self.store.tasks)
                self.store.add_email(email_data)
                added += 1
            except Exception as exc:
                errors.append(os.path.basename(path) + "：" + str(exc))
        self.refresh()
        if added:
            self.toast.show("已导入 %d 封邮件" % added, "success")
        if errors:
            self.toast.show(truncate(errors[0], 80), "error", 4200)
        elif not added:
            self.toast.show("没有新增邮件（可能已经导入过）", "info")

    # ------------------------------------------------------------------- data
    def toggle_task_done(self, task):
        if task.get("completed"):
            model.reopen(task)
            self.store.save()
            self.refresh()
            self.toast.show("任务已重新打开", "info")
            self.schedule_collab_sync()
            return
        try:
            model.mark_complete(task)
        except model.CompletionBlocked as exc:
            self.toast.show("还有 %d 个子任务未完成，暂时不能完成" % exc.pending, "warn", 3200)
            return
        self.store.save()
        self.refresh()
        self.toast.show("任务已完成", "success")
        self.schedule_collab_sync()

    def confirm_delete_task(self, task):
        task_id = task.get("id")

        def remove():
            self.delete_tasks([task_id])

        self.confirm(
            "删除任务？",
            "「%s」及其子任务会一起删除，关联邮件保留。此操作无法撤销。"
            % truncate(task.get("title", "未命名任务"), 20),
            "删除",
            remove,
            danger=True,
        )

    def delete_tasks(self, task_ids):
        ids = [task_id for task_id in task_ids if task_id]
        if not ids:
            return 0
        removed = self.store.delete_tasks(ids)
        if not removed:
            self.toast.show("任务已经不存在", "info")
            return 0
        analyzer.ensure_analyses(self.store)
        page = self.pages.get("tasks")
        if page is not None:
            page.selected -= set(ids)
            if not self.store.tasks:
                page.manage = False
        self.refresh()
        self.toast.show("已删除 %d 个任务" % removed, "success")
        self.schedule_collab_sync()
        return removed

    def export_data(self):
        default_name = "taskdock-backup-%s.json" % datetime.now().strftime("%Y%m%d")
        desktop = Path(os.path.expanduser("~")) / "Desktop"
        initial = desktop if desktop.exists() else Path.home()
        path = filedialog.asksaveasfilename(
            parent=self,
            title="导出 TaskDock 备份",
            initialdir=str(initial),
            initialfile=default_name,
            defaultextension=".json",
            filetypes=[("JSON 备份", "*.json")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(self.store.export_payload(), handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            self.toast.show("导出失败：%s" % exc, "error", 4000)
            return
        self.toast.show("备份已导出", "success")

    def import_data(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="导入 TaskDock 备份",
            filetypes=[("JSON 备份", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as exc:
            self.toast.show("读取失败：%s" % exc, "error", 4000)
            return

        def replace():
            try:
                task_count, email_count = self.store.import_payload(payload)
            except Exception as exc:
                self.toast.show("导入失败：%s" % exc, "error", 4000)
                return
            self.refresh()
            self.toast.show("已导入 %d 个任务、%d 封邮件" % (task_count, email_count), "success")

        self.confirm("导入备份？", "当前任务和邮件会被备份文件替换（邮箱设置保留）。",
                     "导入", replace, danger=True)

    def open_data_dir(self):
        try:
            os.startfile(str(self.store.directory))
        except Exception as exc:
            self.toast.show("无法打开目录：%s" % exc, "error")

    def _maybe_auto_sync(self):
        if not self._running:
            return
        if self.store.settings().get("auto_sync") and self._mail_credentials():
            self.sync_mail()

    # ---------------------------------------------------------------- async
    def run_async(self, work, on_success=None, on_error=None):
        results = queue.Queue()

        def runner():
            try:
                results.put(("ok", work()))
            except Exception as exc:
                results.put(("error", exc))

        threading.Thread(target=runner, daemon=True).start()

        def poll():
            if not self._running:
                return
            try:
                kind, value = results.get_nowait()
            except queue.Empty:
                self.after(90, poll)
                return
            if kind == "ok":
                if on_success:
                    on_success(value)
            else:
                if on_error:
                    on_error(value)
                else:
                    self.toast.show(truncate(str(value), 90), "error", 4200)

        self.after(90, poll)

    # ------------------------------------------------------------------ close
    def close_app(self):
        self._running = False
        self._hide_ai_progress()
        for after_id in (self._show_after, self._auto_sync_after,
                         self._collab_after, self._collab_sync_after):
            if after_id:
                try:
                    self.after_cancel(after_id)
                except Exception:
                    pass
        try:
            self.toast.hide()
        except Exception:
            pass
        try:
            self.store.settings()["window_x"] = self.winfo_x()
            self.store.settings()["window_y"] = self.winfo_y()
            self.store.save()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass


def build_app(data_dir=None, seed=False, auto_show=True):
    return TaskDockApp(data_dir=data_dir, seed=seed, auto_show=auto_show)


def run():
    app = build_app()
    app.mainloop()

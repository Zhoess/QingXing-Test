# -*- coding: utf-8 -*-
"""Collaboration page and the task-forward dialog."""

import tkinter as tk
from datetime import datetime

from . import model
from .constants import COLORS
from .ui_common import EmptyState, Modal, field_label, gap, section_card, styled_entry, styled_text, truncate
from .widgets import CheckCircle, Chip, PillButton, ScrollFrame, SmallIconButton


def _card(parent, bg=None):
    card = tk.Frame(parent, bg=COLORS["surface"], highlightthickness=1,
                    highlightbackground=COLORS["line"])
    inner = tk.Frame(card, bg=COLORS["surface"], padx=13, pady=11)
    inner.pack(fill="both", expand=True)
    return card, inner


def _status_label(parent, text, kind="muted"):
    colors = {
        "muted": (COLORS["surface_alt"], COLORS["faint"]),
        "accent": (COLORS["accent_soft"], COLORS["accent"]),
        "mint": (COLORS["mint_soft"], COLORS["mint"]),
        "danger": (COLORS["danger_soft"], COLORS["danger"]),
        "blue": (COLORS["blue_soft"], COLORS["blue"]),
    }
    bg, fg = colors.get(kind, colors["muted"])
    return tk.Label(parent, text=text, bg=bg, fg=fg,
                    font=("Microsoft YaHei UI", 7, "bold"), padx=6, pady=1)


class CollabPage(tk.Frame):
    def __init__(self, parent, app):
        tk.Frame.__init__(self, parent, bg=COLORS["bg"])
        self.app = app
        self.scroll = ScrollFrame(self, bg=COLORS["bg"], padding=20)
        self.scroll.pack(fill="both", expand=True)
        self.body = self.scroll.inner
        self.mode = "login"
        self.server_var = tk.StringVar(value=app.store.settings().get(
            "collab_server", "http://127.0.0.1:8787"))
        self.account_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.display_var = tk.StringVar()
        self.friend_var = tk.StringVar()
        self.message = ""
        self.friend_message = ""
        self.refresh()

    def on_show(self):
        self.refresh()
        if self.app.collab_user and self.app.collab_data is None:
            self.app.collab_refresh()

    def _head(self, title, subtitle, with_actions=False):
        head = tk.Frame(self.body, bg=COLORS["bg"])
        head.pack(fill="x", pady=(2, 1))
        tk.Label(head, text=title, bg=COLORS["bg"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 15, "bold")).pack(side="left")
        if with_actions:
            PillButton(head, "刷新", self.app.collab_refresh, kind="ghost",
                       width=54, height=29).pack(side="right")
            PillButton(head, "临时对话", self.app.open_message_inbox, kind="soft",
                       width=76, height=29).pack(side="right", padx=(0, 6))
        tk.Label(self.body, text=subtitle, bg=COLORS["bg"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8), anchor="w").pack(fill="x", pady=(1, 12))
        return head

    def _login_view(self):
        self._head("协作网络", "登录清心任务管理终端，和不同终端上的伙伴交换任务。")
        card, inner = _card(self.body)
        card.pack(fill="x", pady=(0, 12))
        tk.Label(inner, text="连接清心任务管理终端", bg=COLORS["surface"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 11, "bold"), anchor="w").pack(fill="x")
        tk.Label(inner, text="服务器地址填清心任务管理终端所在的电脑或服务器，例如 http://192.168.1.20:8787。",
                 bg=COLORS["surface"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 8),
                 anchor="w", justify="left", wraplength=330).pack(fill="x", pady=(4, 10))
        field_label(inner, "清心任务管理终端地址").pack(fill="x", pady=(0, 4))
        styled_entry(inner, self.server_var, font=("Consolas", 9)).pack(fill="x", ipady=6)
        gap(inner, 9)
        field_label(inner, "清心任务客户端账号").pack(fill="x", pady=(0, 4))
        styled_entry(inner, self.account_var).pack(fill="x", ipady=6)
        gap(inner, 9)
        field_label(inner, "密码").pack(fill="x", pady=(0, 4))
        styled_entry(inner, self.password_var, show="•").pack(fill="x", ipady=6)
        gap(inner, 9)
        field_label(inner, "显示名称", "注册新账号时填写").pack(fill="x", pady=(0, 4))
        styled_entry(inner, self.display_var).pack(fill="x", ipady=6)
        gap(inner, 12)
        mode_row = tk.Frame(inner, bg=COLORS["surface"])
        mode_row.pack(fill="x")
        if self.mode == "register":
            tk.Label(mode_row, text="已经有账号？", bg=COLORS["surface"],
                     fg=COLORS["faint"], font=("Microsoft YaHei UI", 8)).pack(side="left")
            link = tk.Label(mode_row, text="返回登录", bg=COLORS["surface"],
                            fg=COLORS["accent"], font=("Microsoft YaHei UI", 8, "bold"),
                            cursor="hand2")
            link.pack(side="left", padx=(4, 0))
            link.bind("<Button-1>", lambda _e: self._set_mode("login"))
        else:
            tk.Label(mode_row, text="还没有账号？", bg=COLORS["surface"],
                     fg=COLORS["faint"], font=("Microsoft YaHei UI", 8)).pack(side="left")
            link = tk.Label(mode_row, text="注册新账号", bg=COLORS["surface"],
                            fg=COLORS["accent"], font=("Microsoft YaHei UI", 8, "bold"),
                            cursor="hand2")
            link.pack(side="left", padx=(4, 0))
            link.bind("<Button-1>", lambda _e: self._set_mode("register"))
        tk.Label(inner, text="账号也可以由管理账号在清心任务管理终端创建。", bg=COLORS["surface"],
                 fg=COLORS["faint"], font=("Microsoft YaHei UI", 8), anchor="w").pack(
            fill="x", pady=(8, 0))
        self.login_btn = PillButton(
            inner, "正在连接…" if self.app.collab_busy else (
                "登录并同步" if self.mode == "login" else "注册并同步"),
            self._submit_login, kind="primary", width=344, height=38)
        self.login_btn.pack(fill="x", pady=(12, 0))
        if self.app.collab_busy:
            self.login_btn.set_disabled(True)
        if self.message or self.app.collab_error:
            tk.Label(inner, text=self.message or self.app.collab_error,
                     bg=COLORS["surface"], fg=COLORS["danger"],
                     font=("Microsoft YaHei UI", 8), anchor="w", justify="left",
                     wraplength=330).pack(fill="x", pady=(8, 0))
        gap(inner, 4)

        info, content = _card(self.body)
        info.pack(fill="x", pady=(0, 12))
        tk.Label(content, text="清心任务客户端之间怎么协作", bg=COLORS["surface"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 10, "bold"), anchor="w").pack(fill="x")
        for title, text in (
            ("添加好友", "双方用账号互相添加；管理账号也能看到账户清单。"),
            ("共享任务", "好友接收后保留自己的任务副本，进度和子任务会同步。"),
            ("转交任务", "好友接收后任务归对方，原端自动归档，避免重复负责。"),
        ):
            row = tk.Frame(content, bg=COLORS["surface"])
            row.pack(fill="x", pady=(7, 0))
            tk.Label(row, text="·", bg=COLORS["surface"], fg=COLORS["accent"],
                     font=("Microsoft YaHei UI", 12, "bold")).pack(side="left", padx=(0, 6))
            box = tk.Frame(row, bg=COLORS["surface"])
            box.pack(side="left", fill="x", expand=True)
            tk.Label(box, text=title, bg=COLORS["surface"], fg=COLORS["ink_soft"],
                     font=("Microsoft YaHei UI", 8, "bold"), anchor="w").pack(fill="x")
            tk.Label(box, text=text, bg=COLORS["surface"], fg=COLORS["muted"],
                     font=("Microsoft YaHei UI", 8), anchor="w", justify="left",
                     wraplength=300).pack(fill="x")

    def _set_mode(self, mode):
        self.mode = mode
        self.message = ""
        self.refresh()

    def _submit_login(self):
        account = self.account_var.get().strip()
        password = self.password_var.get()
        if not account or not password:
            self.message = "请填写账号和密码"
            self.refresh()
            return
        self.message = ""
        self.app.collab_connect(
            self.server_var.get().strip(), account, password,
            register=(self.mode == "register"),
            display_name=self.display_var.get().strip(),
        )
        self.refresh()

    def _account_view(self):
        user = self.app.collab_user
        data = self.app.collab_data or {}
        settings = self.app.store.settings()
        self._head("协作网络", "好友、共享任务和接收箱都在这里汇聚。", with_actions=True)

        account, inner = _card(self.body)
        account.pack(fill="x", pady=(0, 10))
        avatar = tk.Canvas(inner, width=38, height=38, bg=COLORS["surface"],
                           highlightthickness=0, bd=0)
        avatar.pack(side="left")
        avatar.create_oval(1, 1, 37, 37, fill=COLORS["dark"], outline=COLORS["dark"])
        avatar.create_text(19, 19, text=(user.get("display_name") or user.get("username") or "?")[:1],
                           fill=COLORS["white"], font=("Microsoft YaHei UI", 13, "bold"))
        info = tk.Frame(inner, bg=COLORS["surface"])
        info.pack(side="left", padx=(10, 0), fill="x", expand=True)
        tk.Label(info, text=user.get("display_name") or user.get("username"),
                 bg=COLORS["surface"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 11, "bold"), anchor="w").pack(fill="x")
        tk.Label(info, text="@" + user.get("username", "") + " · " + (
            settings.get("collab_server") or ""), bg=COLORS["surface"], fg=COLORS["faint"],
            font=("Microsoft YaHei UI", 7), anchor="w").pack(fill="x", pady=(1, 0))
        PillButton(inner, "退出", self.app.collab_logout, kind="ghost",
                   width=44, height=26).pack(side="right")

        stats = tk.Frame(self.body, bg=COLORS["bg"])
        stats.pack(fill="x", pady=(0, 12))
        values = [
            ("好友", len(data.get("friends") or [])),
            ("待接收", data.get("counts", {}).get("pending_offers", 0)),
            ("好友申请", data.get("counts", {}).get("friend_requests", 0)),
        ]
        for label, value in values:
            box = tk.Frame(stats, bg=COLORS["surface"], highlightthickness=1,
                           highlightbackground=COLORS["line"], padx=10, pady=8)
            box.pack(side="left", fill="x", expand=True, padx=(0, 6))
            tk.Label(box, text=str(value), bg=COLORS["surface"], fg=COLORS["ink"],
                     font=("Georgia", 17, "bold")).pack(anchor="w")
            tk.Label(box, text=label, bg=COLORS["surface"], fg=COLORS["faint"],
                     font=("Microsoft YaHei UI", 7)).pack(anchor="w")

        if user.get("role") == "admin":
            self._admin_global_card(data)

        if self.app.collab_error:
            banner = tk.Frame(self.body, bg=COLORS["danger_soft"], padx=10, pady=7)
            banner.pack(fill="x", pady=(0, 10))
            tk.Label(banner, text=truncate(self.app.collab_error, 90), bg=COLORS["danger_soft"],
                     fg=COLORS["danger"], font=("Microsoft YaHei UI", 8),
                     anchor="w", justify="left", wraplength=330).pack(fill="x")

        offers = data.get("offers") or {}
        pending = [o for o in offers.get("inbox", []) if o.get("status") == "pending"]
        if pending:
            tk.Label(self.body, text="等待接收", bg=COLORS["bg"], fg=COLORS["ink_soft"],
                     font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x", pady=(2, 6))
            for offer in pending:
                self._offer_card(offer)

        requests = data.get("requests") or {}
        incoming = requests.get("incoming") or []
        if incoming:
            tk.Label(self.body, text="好友申请", bg=COLORS["bg"], fg=COLORS["ink_soft"],
                     font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x", pady=(4, 6))
            for request in incoming:
                self._request_card(request)

        add, inner = _card(self.body)
        add.pack(fill="x", pady=(4, 10))
        tk.Label(inner, text="添加好友", bg=COLORS["surface"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x", pady=(0, 6))
        row = tk.Frame(inner, bg=COLORS["surface"])
        row.pack(fill="x")
        entry = styled_entry(row, self.friend_var, font=("Microsoft YaHei UI", 9))
        entry.pack(side="left", fill="x", expand=True, ipady=5)
        entry.bind("<Return>", lambda _e: self._add_friend())
        PillButton(row, "发送申请", self._add_friend, kind="soft",
                   width=76, height=32).pack(side="left", padx=(7, 0))
        if self.friend_message:
            tk.Label(inner, text=self.friend_message, bg=COLORS["surface"],
                     fg=COLORS["danger"], font=("Microsoft YaHei UI", 8),
                     anchor="w").pack(fill="x", pady=(5, 0))

        friends = data.get("friends") or []
        tk.Label(self.body, text="好友", bg=COLORS["bg"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x", pady=(4, 6))
        if friends:
            for friend in friends:
                row = tk.Frame(self.body, bg=COLORS["surface"], padx=11, pady=8,
                               highlightthickness=1, highlightbackground=COLORS["line"])
                row.pack(fill="x", pady=(0, 5))
                av = tk.Canvas(row, width=28, height=28, bg=COLORS["surface"],
                               highlightthickness=0, bd=0)
                av.pack(side="left")
                av.create_oval(1, 1, 27, 27, fill=COLORS["accent_soft"], outline=COLORS["accent_soft"])
                av.create_text(14, 14, text=(friend.get("display_name") or "?")[:1],
                               fill=COLORS["accent"], font=("Microsoft YaHei UI", 9, "bold"))
                info = tk.Frame(row, bg=COLORS["surface"])
                info.pack(side="left", fill="x", expand=True, padx=(8, 0))
                tk.Label(info, text=friend.get("display_name") or friend.get("username"),
                         bg=COLORS["surface"], fg=COLORS["ink"],
                         font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x")
                tk.Label(info, text="@" + friend.get("username", ""), bg=COLORS["surface"],
                         fg=COLORS["faint"], font=("Microsoft YaHei UI", 7),
                         anchor="w").pack(fill="x")
                PillButton(row, "聊天", lambda f=friend: self.app.open_friend_chat(f),
                           kind="ghost", width=48, height=28).pack(side="right", padx=(0, 5))
                PillButton(row, "转发任务", lambda f=friend: self.app.open_forward_dialog(friend=f),
                           kind="soft", width=66, height=28).pack(side="right")
        else:
            tk.Label(self.body, text="还没有好友，先在上方添加一个账号。", bg=COLORS["bg"],
                     fg=COLORS["faint"], font=("Microsoft YaHei UI", 8)).pack(fill="x", pady=6)

        sent = offers.get("sent") or []
        if sent:
            tk.Label(self.body, text="我发出的邀请", bg=COLORS["bg"], fg=COLORS["ink_soft"],
                     font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x", pady=(6, 6))
            for offer in sent[:8]:
                row = tk.Frame(self.body, bg=COLORS["surface"], padx=10, pady=7,
                               highlightthickness=1, highlightbackground=COLORS["line_soft"])
                row.pack(fill="x", pady=(0, 4))
                title = (offer.get("task") or {}).get("title") or "任务"
                tk.Label(row, text=truncate(title, 24), bg=COLORS["surface"], fg=COLORS["ink_soft"],
                         font=("Microsoft YaHei UI", 8), anchor="w").pack(side="left")
                status_text, kind = {
                    "pending": ("等待接收", "accent"),
                    "accepted": ("已接收", "mint"),
                    "declined": ("已拒绝", "muted"),
                }.get(offer.get("status"), ("—", "muted"))
                _status_label(row, status_text, kind).pack(side="right")
                tk.Label(row, text=offer.get("to_name") or "", bg=COLORS["surface"],
                         fg=COLORS["faint"], font=("Microsoft YaHei UI", 7)).pack(
                    side="right", padx=(0, 6))
        tk.Frame(self.body, bg=COLORS["bg"], height=14).pack(fill="x")

    def _admin_global_card(self, data):
        card, inner = _card(self.body)
        card.pack(fill="x", pady=(0, 10))
        head = tk.Frame(inner, bg=COLORS["surface"])
        head.pack(fill="x")
        tk.Label(head, text="全局任务视图", bg=COLORS["surface"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        tk.Label(head, text="管理端", bg=COLORS["accent_pale"], fg=COLORS["accent"],
                 font=("Microsoft YaHei UI", 7, "bold"), padx=6, pady=2).pack(
            side="right")
        tk.Label(inner, text="以管理账号登录，可查看所有账户的任务情况；此视图只读。",
                 bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8), anchor="w", justify="left",
                 wraplength=330).pack(fill="x", pady=(4, 8))
        overview = data.get("admin_overview") or {}
        if overview:
            stats = overview.get("stats") or {}
            values = [
                ("账户", stats.get("active_users", 0)),
                ("未归档任务", stats.get("tasks", 0)),
                ("逾期", stats.get("overdue", 0)),
                ("完成率", "%d%%" % int(stats.get("completion", 0))),
            ]
            row = tk.Frame(inner, bg=COLORS["surface"])
            row.pack(fill="x", pady=(0, 9))
            for label, value in values:
                box = tk.Frame(row, bg=COLORS["surface_alt"], padx=7, pady=5)
                box.pack(side="left", fill="x", expand=True, padx=(0, 4))
                tk.Label(box, text=str(value), bg=COLORS["surface_alt"],
                         fg=COLORS["ink"], font=("Georgia", 13, "bold")).pack(anchor="w")
                tk.Label(box, text=label, bg=COLORS["surface_alt"], fg=COLORS["faint"],
                         font=("Microsoft YaHei UI", 7)).pack(anchor="w")
            PillButton(inner, "查看全部账户任务", self.app.open_global_tasks,
                       kind="primary", width=160, height=34).pack(anchor="w")
        else:
            message = data.get("admin_error") or "正在加载全局任务数据…"
            tk.Label(inner, text=message, bg=COLORS["surface"], fg=COLORS["danger"]
                     if data.get("admin_error") else COLORS["faint"],
                     font=("Microsoft YaHei UI", 8), anchor="w",
                     justify="left", wraplength=330).pack(fill="x")
            PillButton(inner, "刷新全局数据", self.app.collab_refresh,
                       kind="soft", width=110, height=30).pack(anchor="w", pady=(7, 0))

    def _offer_card(self, offer):
        card, inner = _card(self.body)
        card.pack(fill="x", pady=(0, 6))
        top = tk.Frame(inner, bg=COLORS["surface"])
        top.pack(fill="x")
        mode = "共享任务" if offer.get("mode") == "share" else "转交任务"
        _status_label(top, mode, "accent" if offer.get("mode") == "share" else "blue").pack(side="left")
        tk.Label(top, text="来自 " + (offer.get("from_name") or offer.get("from_username") or ""),
                 bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 7)).pack(side="left", padx=(7, 0))
        title = (offer.get("task") or {}).get("title") or "任务"
        tk.Label(inner, text=truncate(title, 34), bg=COLORS["surface"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 10, "bold"), anchor="w",
                 justify="left", wraplength=330).pack(fill="x", pady=(6, 2))
        if offer.get("message"):
            tk.Label(inner, text=truncate(offer.get("message"), 70), bg=COLORS["surface"],
                     fg=COLORS["muted"], font=("Microsoft YaHei UI", 8),
                     anchor="w", justify="left", wraplength=330).pack(fill="x")
        row = tk.Frame(inner, bg=COLORS["surface"])
        row.pack(fill="x", pady=(8, 0))
        PillButton(row, "接收", lambda o=offer: self._respond_offer(o["id"], True),
                   kind="primary", width=60, height=30).pack(side="left")
        PillButton(row, "拒绝", lambda o=offer: self._respond_offer(o["id"], False),
                   kind="ghost", width=56, height=30).pack(side="left", padx=(6, 0))

    def _request_card(self, request):
        row = tk.Frame(self.body, bg=COLORS["surface"], padx=11, pady=8,
                       highlightthickness=1, highlightbackground=COLORS["line"])
        row.pack(fill="x", pady=(0, 5))
        info = tk.Frame(row, bg=COLORS["surface"])
        info.pack(side="left", fill="x", expand=True)
        tk.Label(info, text=request.get("display_name") or request.get("username"),
                 bg=COLORS["surface"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x")
        tk.Label(info, text="@" + request.get("username", "") + " 想加你为好友",
                 bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 7), anchor="w").pack(fill="x")
        PillButton(row, "拒绝", lambda r=request: self.app.collab_respond_friend(r["id"], False),
                   kind="ghost", width=50, height=27).pack(side="right", padx=(5, 0))
        PillButton(row, "接受", lambda r=request: self.app.collab_respond_friend(r["id"], True),
                   kind="soft", width=50, height=27).pack(side="right")

    def _add_friend(self):
        username = self.friend_var.get().strip()
        if not username:
            self.friend_message = "请输入对方的账号"
            self.refresh()
            return
        self.friend_message = ""
        self.app.collab_add_friend(username, self._friend_done)
        self.refresh()

    def _friend_done(self, message):
        self.friend_message = message
        self.refresh()

    def _respond_offer(self, offer_id, accept):
        self.app.collab_respond_offer(offer_id, accept)

    def refresh(self):
        yview = self.scroll.canvas.yview()
        for child in list(self.body.winfo_children()):
            child.destroy()
        if self.app.collab_user:
            self._account_view()
        else:
            self._login_view()
        tk.Frame(self.body, bg=COLORS["bg"], height=18).pack(fill="x")
        self.body.update_idletasks()
        self.scroll.refresh()
        target = yview[0] if yview else 0
        self.after_idle(lambda: self.scroll.canvas.yview_moveto(target))


class GlobalTasksModal(Modal):
    """Read-only all-account task view for a management account."""

    FILTERS = (("all", "全部"), ("open", "未完成"), ("overdue", "逾期"),
               ("done", "已完成"))

    def __init__(self, app):
        self.app = app
        data = app.collab_data or {}
        overview = data.get("admin_overview") or {}
        self.all_tasks = [t for t in overview.get("tasks") or [] if not t.get("archived")]
        self.filter = "all"
        self.filter_chips = {}
        self.rows_box = None
        Modal.__init__(self, app, "全局任务", "所有账户的任务情况 · 只读")
        self._build()
        self._render()

    def _build(self):
        body = self.content
        overview = (self.app.collab_data or {}).get("admin_overview") or {}
        stats = overview.get("stats") or {}
        tk.Label(body, text="管理账号可查看所有账户的任务；这里只汇总，不会修改任务。",
                 bg=COLORS["bg"], fg=COLORS["faint"], font=("Microsoft YaHei UI", 8),
                 anchor="w", justify="left", wraplength=340).pack(fill="x", pady=(0, 8))
        summary = "账户 %d · 未归档任务 %d · 逾期 %d · 完成率 %d%%" % (
            stats.get("active_users", 0), stats.get("tasks", 0),
            stats.get("overdue", 0), stats.get("completion", 0))
        tk.Label(body, text=summary, bg=COLORS["accent_pale"], fg=COLORS["accent"],
                 font=("Microsoft YaHei UI", 8, "bold"), anchor="w",
                 padx=9, pady=6).pack(fill="x", pady=(0, 8))

        filters = tk.Frame(body, bg=COLORS["bg"])
        filters.pack(fill="x", pady=(0, 8))
        for key, label in self.FILTERS:
            chip = Chip(filters, label, command=lambda k=key: self._set_filter(k),
                        selected=key == self.filter, height=25,
                        font=("Microsoft YaHei UI", 7))
            chip.pack(side="left", padx=(0, 4))
            self.filter_chips[key] = chip
        self.count_label = tk.Label(body, text="", bg=COLORS["bg"], fg=COLORS["faint"],
                                    font=("Microsoft YaHei UI", 7), anchor="w")
        self.count_label.pack(fill="x", pady=(0, 4))
        self.rows_box = tk.Frame(body, bg=COLORS["bg"])
        self.rows_box.pack(fill="x")
        PillButton(self.footer_right, "关闭", self.force_close, kind="ghost",
                   width=62, height=32).pack(side="right", padx=16)

    def _set_filter(self, key):
        self.filter = key
        for name, chip in self.filter_chips.items():
            chip.set_selected(name == key)
        self._render()

    @staticmethod
    def _due_text(task):
        dt = model.parse_dt(task.get("due"))
        return dt.strftime("%m/%d %H:%M") if dt else "未设截止"

    def _status(self, task):
        if task.get("completed"):
            return "已完成", COLORS["mint"], COLORS["mint_soft"]
        due = model.parse_dt(task.get("due"))
        if due and due < datetime.now():
            return "已逾期", COLORS["danger"], COLORS["danger_soft"]
        return "进行中", COLORS["accent"], COLORS["accent_pale"]

    def _filtered(self):
        tasks = list(self.all_tasks)
        if self.filter == "open":
            tasks = [t for t in tasks if not t.get("completed")]
        elif self.filter == "overdue":
            tasks = [t for t in tasks if not t.get("completed")
                     and model.parse_dt(t.get("due"))
                     and model.parse_dt(t.get("due")) < datetime.now()]
        elif self.filter == "done":
            tasks = [t for t in tasks if t.get("completed")]
        return tasks

    def _render(self):
        for child in list(self.rows_box.winfo_children()):
            child.destroy()
        tasks = self._filtered()
        tasks.sort(key=lambda t: (t.get("display_name") or t.get("username") or "",
                                  t.get("due") or "9999"))
        self.count_label.configure(text="共 %d 条任务" % len(tasks))
        if not tasks:
            tk.Label(self.rows_box, text="没有匹配的任务。", bg=COLORS["bg"],
                     fg=COLORS["faint"], font=("Microsoft YaHei UI", 8)).pack(
                fill="x", pady=18)
            return
        for task in tasks[:200]:
            row = tk.Frame(self.rows_box, bg=COLORS["surface"], padx=10, pady=8,
                           highlightthickness=1, highlightbackground=COLORS["line"])
            row.pack(fill="x", pady=(0, 5))
            head = tk.Frame(row, bg=COLORS["surface"])
            head.pack(fill="x")
            tk.Label(head, text=truncate(task.get("title") or "未命名任务", 30),
                     bg=COLORS["surface"], fg=COLORS["ink"],
                     font=("Microsoft YaHei UI", 9, "bold"), anchor="w",
                     justify="left", wraplength=245).pack(side="left", fill="x", expand=True)
            label, fg, bg = self._status(task)
            tk.Label(head, text=label, bg=bg,
                     fg=fg, font=("Microsoft YaHei UI", 7, "bold"),
                     padx=5, pady=2).pack(side="right", padx=(5, 0))
            account = task.get("display_name") or task.get("username") or "未知账户"
            progress = int(task.get("progress") or 0)
            tk.Label(row, text="%s · @%s" % (account, task.get("username") or ""),
                     bg=COLORS["surface"], fg=COLORS["ink_soft"],
                     font=("Microsoft YaHei UI", 7), anchor="w").pack(fill="x", pady=(3, 0))
            tk.Label(row, text="进度 %d%%  ·  截止 %s  ·  %s" % (
                progress, self._due_text(task), task.get("cycle") or "一次性"),
                bg=COLORS["surface"], fg=COLORS["faint"],
                font=("Microsoft YaHei UI", 7), anchor="w").pack(fill="x", pady=(2, 0))


class FriendChatDialog(Modal):
    def __init__(self, app, friend):
        self.app = app
        self.friend = friend
        self.messages = []
        self._poll_after = None
        super(FriendChatDialog, self).__init__(
            app, "与 %s 聊天" % (friend.get("display_name") or friend.get("username") or "好友"),
            "好友私聊 · 可直接转发任务")
        self._build()
        self._load()
        self._poll_after = self.after(4000, self._poll)

    def _build(self):
        body = self.content
        self.messages_box = tk.Frame(body, bg=COLORS["bg"])
        self.messages_box.pack(fill="both", expand=True)
        self.footer.configure(height=108)
        self.footer_left.pack_configure(fill="x", expand=True, padx=(16, 8), pady=(7, 6))
        tk.Label(self.footer_left, text="消息", bg=COLORS["surface"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 8, "bold"), anchor="w").pack(fill="x")
        self.input = styled_text(self.footer_left, "", height=2)
        self.input.pack(fill="x", pady=(3, 0))
        self.typing = tk.Label(self.footer_left, text="", bg=COLORS["surface"],
                               fg=COLORS["faint"], font=("Microsoft YaHei UI", 7), anchor="w")
        self.typing.pack(fill="x")
        self.footer_right.pack_configure(padx=(0, 12), pady=(18, 6))
        PillButton(self.footer_right, "转发任务", self._forward, kind="soft",
                   width=76, height=32).pack(side="left", padx=(0, 6))
        self.send_btn = PillButton(self.footer_right, "发送", self._send, kind="primary",
                                   width=64, height=34)
        self.send_btn.pack(side="left")

    def _load(self):
        self.app.load_friend_messages(
            self.friend.get("id"), self._render, self._load_failed)

    def _poll(self):
        self._poll_after = None
        if not self.winfo_exists():
            return
        self._load()
        self._poll_after = self.after(4000, self._poll)

    def _render(self, messages):
        if not self.winfo_exists():
            return
        self.messages = messages
        for child in list(self.messages_box.winfo_children()):
            child.destroy()
        if not messages:
            tk.Label(self.messages_box, text="还没有消息，先打个招呼吧。",
                     bg=COLORS["bg"], fg=COLORS["faint"],
                     font=("Microsoft YaHei UI", 8), anchor="w").pack(fill="x", pady=12)
            self.typing.configure(text="")
            return
        me = (self.app.collab_user or {}).get("id")
        for message in messages[-100:]:
            mine = message.get("from_id") == me
            row = tk.Frame(self.messages_box, bg=COLORS["bg"])
            row.pack(fill="x", pady=(0, 6))
            bubble = tk.Frame(row, bg=COLORS["accent_soft"] if mine else COLORS["surface"],
                              padx=10, pady=7)
            bubble.pack(side="right" if mine else "left")
            tk.Label(bubble, text=message.get("body") or "", bg=bubble["bg"],
                     fg=COLORS["ink"], font=("Microsoft YaHei UI", 9),
                     anchor="w", justify="left", wraplength=270).pack(fill="x")
            tk.Label(bubble, text=(message.get("from_name") or message.get("from_username") or "")
                     + "  " + (message.get("created_at") or "")[11:16],
                     bg=bubble["bg"], fg=COLORS["faint"],
                     font=("Microsoft YaHei UI", 7), anchor="w").pack(fill="x", pady=(3, 0))
        self.typing.configure(text="")

    def _load_failed(self, error):
        if self.winfo_exists():
            self.typing.configure(text=truncate(str(error), 60))

    def _send(self):
        text = self.input.get("1.0", "end").strip()
        if not text:
            self.typing.configure(text="请输入消息")
            return
        self.input.delete("1.0", "end")
        self.send_btn.set_disabled(True)
        self.app.send_friend_message(
            self.friend.get("id"), text,
            on_success=lambda _result: self._sent(),
            on_error=self._send_failed)

    def _sent(self):
        if not self.winfo_exists():
            return
        self.send_btn.set_disabled(False)
        self._load()

    def _send_failed(self, error):
        if not self.winfo_exists():
            return
        self.send_btn.set_disabled(False)
        self.typing.configure(text=truncate(str(error), 60))

    def _forward(self):
        self.app.open_forward_dialog(friend=self.friend)

    def force_close(self):
        if self._poll_after is not None:
            try:
                self.after_cancel(self._poll_after)
            except tk.TclError:
                pass
            self._poll_after = None
        super(FriendChatDialog, self).force_close()


class ForwardDialog(Modal):
    def __init__(self, app, task=None, friend=None):
        self.app = app
        self.friend = friend
        self.selected_task = task
        self.selected_tasks = [task] if task is not None else []
        self.selected_friend = friend
        self.mode = "share"
        self.error = ""
        self.sent_offers = ((app.collab_data or {}).get("offers") or {}).get("sent") or []
        super(ForwardDialog, self).__init__(app, "转发任务", "把任务共享给好友，或直接转交负责人")
        self._build()

    def _build(self):
        body = self.content
        data = self.app.collab_data or {}
        friends = data.get("friends") or []
        tasks = self.app.store.active_tasks()
        if self.selected_task is not None:
            card = tk.Frame(body, bg=COLORS["accent_pale"], padx=12, pady=10)
            card.pack(fill="x", pady=(0, 12))
            tk.Label(card, text="要转发的任务", bg=COLORS["accent_pale"],
                     fg=COLORS["accent"], font=("Microsoft YaHei UI", 8, "bold")).pack(anchor="w")
            tk.Label(card, text=self.selected_task.get("title", ""), bg=COLORS["accent_pale"],
                     fg=COLORS["ink"], font=("Microsoft YaHei UI", 11, "bold"),
                     anchor="w", justify="left", wraplength=330).pack(fill="x", pady=(2, 0))
        else:
            tk.Label(body, text="选择要转发的任务（可多选）", bg=COLORS["bg"], fg=COLORS["ink_soft"],
                     font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x", pady=(0, 5))
            self.task_box = tk.Frame(body, bg=COLORS["surface"], highlightthickness=1,
                                     highlightbackground=COLORS["line"])
            self.task_box.pack(fill="x")
            self.task_checks = {}
            if not tasks:
                tk.Label(self.task_box, text="还没有可转发的任务。", bg=COLORS["surface"],
                         fg=COLORS["faint"], font=("Microsoft YaHei UI", 8),
                         padx=10, pady=10).pack(fill="x")
            for task in tasks[:12]:
                row = tk.Frame(self.task_box, bg=COLORS["surface"], padx=9, pady=6)
                row.pack(fill="x")
                check = CheckCircle(row, checked=False,
                                    command=lambda t=task: self._choose_task(t),
                                    size=19, bg=COLORS["surface"], color=COLORS["accent"])
                check.pack(side="left")
                label = tk.Label(row, text=truncate(task.get("title", ""), 36),
                                 bg=COLORS["surface"], fg=COLORS["ink_soft"],
                                 font=("Microsoft YaHei UI", 8), anchor="w")
                label.pack(side="left", padx=(7, 0), fill="x", expand=True)
                row.bind("<Button-1>", lambda _e, t=task: self._choose_task(t))
                label.bind("<Button-1>", lambda _e, t=task: self._choose_task(t))
                self.task_checks[task.get("id")] = check
            gap(body, 12)

        tk.Label(body, text="选择好友", bg=COLORS["bg"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x", pady=(0, 5))
        if not friends:
            EmptyState(body, "还没有好友", "先到协作页添加好友，再转发任务。").pack(fill="x")
        else:
            self.friend_checks = {}
            for friend in friends:
                row = tk.Frame(body, bg=COLORS["surface"], padx=10, pady=7,
                               highlightthickness=1, highlightbackground=COLORS["line"])
                row.pack(fill="x", pady=(0, 5))
                check = CheckCircle(row, checked=(self.friend and self.friend.get("id") == friend.get("id")),
                                    command=lambda f=friend: self._choose_friend(f),
                                    size=19, bg=COLORS["surface"], color=COLORS["accent"])
                check.pack(side="left")
                info = tk.Frame(row, bg=COLORS["surface"])
                info.pack(side="left", padx=(8, 0), fill="x", expand=True)
                tk.Label(info, text=friend.get("display_name") or friend.get("username"),
                         bg=COLORS["surface"], fg=COLORS["ink"],
                         font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x")
                tk.Label(info, text="@" + friend.get("username", ""), bg=COLORS["surface"],
                         fg=COLORS["faint"], font=("Microsoft YaHei UI", 7),
                         anchor="w").pack(fill="x")
                row.bind("<Button-1>", lambda _e, f=friend: self._choose_friend(f))
                self.friend_checks[friend.get("id")] = check
        gap(body, 12)

        tk.Label(body, text="分享方式", bg=COLORS["bg"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x", pady=(0, 5))
        modes = tk.Frame(body, bg=COLORS["bg"])
        modes.pack(fill="x")
        self.mode_chips = {}
        for mode, label in (("share", "共享协作"), ("transfer", "转交任务")):
            chip = Chip(modes, label, command=lambda m=mode: self._set_mode(m),
                        selected=self.mode == mode, height=27,
                        font=("Microsoft YaHei UI", 8))
            chip.pack(side="left", padx=(0, 5))
            self.mode_chips[mode] = chip
        tk.Label(body, text="共享会保留双方副本并同步进度；转交后原端归档，由对方负责。",
                 bg=COLORS["bg"], fg=COLORS["faint"], font=("Microsoft YaHei UI", 7),
                 anchor="w", justify="left", wraplength=330).pack(fill="x", pady=(3, 0))
        gap(body, 10)
        tk.Label(body, text="留言（可选）", bg=COLORS["bg"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x", pady=(0, 4))
        self.message_text = styled_text(body, "", height=2)
        self.message_text.pack(fill="x")
        self.error_label = tk.Label(body, text="", bg=COLORS["bg"], fg=COLORS["danger"],
                                    font=("Microsoft YaHei UI", 8), anchor="w")
        self.error_label.pack(fill="x", pady=(5, 0))
        PillButton(self.footer_right, "取消", self.request_close, kind="ghost",
                   width=62, height=36).pack(side="left", padx=(0, 8), pady=16)
        self.send_btn = PillButton(self.footer_right, "发送邀请", self._send,
                                   kind="primary", width=88, height=36)
        self.send_btn.pack(side="left", pady=16)

    def _already_shared(self, task, friend):
        if not task or not friend:
            return False
        return any(
            str(offer.get("task_id")) == str(task.get("id"))
            and str(offer.get("to_id")) == str(friend.get("id"))
            and offer.get("mode") == "share"
            and offer.get("status") in ("pending", "accepted")
            for offer in self.sent_offers
        )

    def _choose_task(self, task):
        if self._already_shared(task, self.selected_friend):
            self.error_label.configure(text="该任务已共享给此好友，请勿重复共享")
            return
        check = self.task_checks.get(task.get("id"))
        selected = (not check.checked) if check is not None else True
        if check is not None:
            check.set(selected)
        self.selected_tasks = [item for item in self.selected_tasks
                               if item.get("id") != task.get("id")]
        if selected:
            self.selected_tasks.append(task)
        self.selected_task = task if selected else (
            self.selected_tasks[-1] if self.selected_tasks else None)

    def _choose_friend(self, friend):
        self.selected_friend = friend
        for friend_id, check in self.friend_checks.items():
            check.set(friend_id == friend.get("id"))

    def _set_mode(self, mode):
        self.mode = mode
        for key, chip in self.mode_chips.items():
            chip.set_selected(key == mode)

    def _send(self):
        if not self.selected_tasks:
            self.error_label.configure(text="请选择要转发的任务")
            return
        if not self.selected_friend:
            self.error_label.configure(text="请选择好友")
            return
        if self.mode == "share" and any(
                self._already_shared(task, self.selected_friend)
                for task in self.selected_tasks):
            self.error_label.configure(text="该任务已共享给此好友，请勿重复共享")
            return
        self.error_label.configure(text="")
        self.send_btn.set_disabled(True)
        self.send_btn.set_text("发送中…")
        message = self.message_text.get("1.0", "end").strip()
        task_ids = [task.get("id") for task in self.selected_tasks if task.get("id")]
        self.app.forward_tasks_async(
            task_ids,
            self.selected_friend.get("id"),
            self.mode,
            message,
            on_success=self._sent,
            on_error=self._send_failed,
        )

    def _sent(self, results):
        self.set_dirty(False)
        self.force_close()
        count = len(results) if isinstance(results, list) else len(self.selected_tasks)
        self.app.toast("已发送 %d 个任务邀请" % count, "success")

    def _send_failed(self, error):
        self.send_btn.set_disabled(False)
        self.send_btn.set_text("发送邀请")
        self.error_label.configure(text=truncate(str(error), 90))

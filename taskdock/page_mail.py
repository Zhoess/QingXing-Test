# -*- coding: utf-8 -*-
"""DingTalk inbox page and email review modals."""

import tkinter as tk
from tkinter import ttk
from datetime import datetime

from . import analyzer, model
from .constants import COLORS
from .ui_common import (EmptyState, Modal, field_label, gap, mail_time, section_card,
                        separator, status_pill, styled_entry, styled_text, truncate)
from .widgets import CheckCircle, Chip, PillButton, ScrollFrame, SmallIconButton, round_rect


INTENT_META = {
    "new": ("建议新建", COLORS["accent"], COLORS["accent_soft"]),
    "update": ("建议更新", COLORS["blue"], COLORS["blue_soft"]),
    "info": ("仅通知", COLORS["muted"], COLORS["surface_alt"]),
    "linked": ("已关联", COLORS["mint"], COLORS["mint_soft"]),
}


def intent_of(email):
    analysis = email.get("analysis") or {}
    if analysis.get("linked_task_id") or analysis.get("linked_task_ids"):
        return "linked"
    return analysis.get("intent") or "info"


def confidence_label(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "低"
    if value >= 0.75:
        return "高"
    if value >= 0.5:
        return "中"
    return "低"


def linked_tasks_of(store, email):
    analysis = email.get("analysis") or {}
    ids = analysis.get("linked_task_ids") or []
    if not ids and analysis.get("linked_task_id"):
        ids = [analysis["linked_task_id"]]
    result = []
    for task_id in ids:
        task = store.task(task_id)
        if task and task not in result:
            result.append(task)
    return result


class MailPage(tk.Frame):
    def __init__(self, parent, app):
        tk.Frame.__init__(self, parent, bg=COLORS["bg"])
        self.app = app
        self.filter = "all"
        self.scroll = ScrollFrame(self, bg=COLORS["bg"], padding=20)
        self.scroll.pack(fill="both", expand=True)
        self.body = self.scroll.inner
        self.refresh()

    def on_show(self):
        self.refresh()

    def set_filter(self, key):
        self.filter = key
        self.refresh()

    def _filtered(self):
        emails = list(self.app.store.emails)
        if self.filter == "action":
            return [e for e in emails if intent_of(e) in ("new", "update")]
        if self.filter == "linked":
            return [e for e in emails if intent_of(e) == "linked"]
        if self.filter == "unread":
            return [e for e in emails if not e.get("read")]
        return emails

    def refresh(self):
        yview = self.scroll.canvas.yview()
        for child in list(self.body.winfo_children()):
            child.destroy()
        emails = list(self.app.store.emails)
        actionable = [e for e in emails if intent_of(e) in ("new", "update")]
        unread = len([e for e in emails if not e.get("read")])
        settings = self.app.store.settings()

        # Title and actions.
        head = tk.Frame(self.body, bg=COLORS["bg"])
        head.pack(fill="x", pady=(2, 1))
        tk.Label(head, text="钉钉邮件", bg=COLORS["bg"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 15, "bold")).pack(side="left")
        self.sync_btn = PillButton(head, "同步中…" if self.app.syncing else "同步",
                                   self.app.sync_mail, kind="dark", width=72, height=30)
        self.sync_btn.pack(side="right")
        if self.app.syncing:
            self.sync_btn.set_disabled(True)
        PillButton(head, "导入", self.app.import_eml, kind="ghost", width=54,
                   height=30).pack(side="right", padx=(0, 6))
        sub = "只读收件箱 · 最近 %s 天" % settings.get("days", 14)
        if settings.get("last_sync"):
            sub += " · 上次同步 " + mail_time(settings["last_sync"])
        tk.Label(self.body, text=sub, bg=COLORS["bg"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8), anchor="w").pack(fill="x", pady=(1, 12))

        # Connection state.
        if not settings.get("account"):
            card = tk.Frame(self.body, bg=COLORS["accent_pale"], padx=14, pady=13,
                            highlightthickness=1, highlightbackground="#EED6C8")
            card.pack(fill="x", pady=(0, 12))
            tk.Label(card, text="连接钉钉邮箱，让邮件自己走进清单", bg=COLORS["accent_pale"],
                     fg=COLORS["ink"], font=("Microsoft YaHei UI", 10, "bold"),
                     anchor="w").pack(fill="x")
            tk.Label(card, text="读取收件箱并提取截止时间、负责人与待办。解析只在本机进行，写入前由你确认。",
                     bg=COLORS["accent_pale"], fg=COLORS["muted"],
                     font=("Microsoft YaHei UI", 8), wraplength=330,
                     justify="left", anchor="w").pack(fill="x", pady=(4, 9))
            row = tk.Frame(card, bg=COLORS["accent_pale"])
            row.pack(fill="x")
            PillButton(row, "连接邮箱", lambda: self.app.switch_page("settings"),
                       kind="primary", height=34, width=84).pack(side="left")
            PillButton(row, "导入 .eml", self.app.import_eml, kind="ghost",
                       height=34, width=82).pack(side="left", padx=(7, 0))
            tk.Label(card, text="也可以先看下面的示例邮件。", bg=COLORS["accent_pale"],
                     fg=COLORS["faint"], font=("Microsoft YaHei UI", 8),
                     anchor="w").pack(fill="x", pady=(7, 0))
        else:
            account_card = tk.Frame(self.body, bg=COLORS["surface"], padx=13, pady=10,
                                    highlightthickness=1, highlightbackground=COLORS["line"])
            account_card.pack(fill="x", pady=(0, 10))
            avatar = tk.Canvas(account_card, width=30, height=30, bg=COLORS["surface"],
                               highlightthickness=0, bd=0)
            avatar.pack(side="left")
            avatar.create_oval(1, 1, 29, 29, fill=COLORS["dark"], outline=COLORS["dark"])
            avatar.create_text(15, 15, text="钉", fill=COLORS["white"],
                               font=("Microsoft YaHei UI", 10, "bold"))
            info = tk.Frame(account_card, bg=COLORS["surface"])
            info.pack(side="left", padx=(9, 0), fill="x", expand=True)
            tk.Label(info, text=settings.get("account", ""), bg=COLORS["surface"],
                     fg=COLORS["ink_soft"], font=("Microsoft YaHei UI", 9, "bold"),
                     anchor="w").pack(fill="x")
            status = "IMAP 已配置" if self.app.store.has_password() else "缺少专用密码"
            tk.Label(info, text=status, bg=COLORS["surface"], fg=COLORS["faint"],
                     font=("Microsoft YaHei UI", 8), anchor="w").pack(fill="x")
            PillButton(account_card, "设置", lambda: self.app.switch_page("settings"),
                       kind="ghost", width=50, height=28).pack(side="right")
            if settings.get("last_sync_error"):
                banner = tk.Frame(self.body, bg=COLORS["danger_soft"], padx=12, pady=8)
                banner.pack(fill="x", pady=(0, 10))
                tk.Label(banner, text=truncate(settings["last_sync_error"], 92),
                         bg=COLORS["danger_soft"], fg=COLORS["danger"],
                         font=("Microsoft YaHei UI", 8), anchor="w", justify="left",
                         wraplength=336).pack(fill="x")

        if actionable:
            summary = tk.Frame(self.body, bg=COLORS["surface"], padx=13, pady=11,
                               highlightthickness=1, highlightbackground=COLORS["line"])
            summary.pack(fill="x", pady=(0, 12))
            tk.Label(summary, text="已整理出 %d 条任务建议" % len(actionable),
                     bg=COLORS["surface"], fg=COLORS["ink"],
                     font=("Microsoft YaHei UI", 10, "bold"), anchor="w").pack(fill="x")
            tk.Label(summary, text="打开邮件核对，确认后才会写入任务清单。",
                     bg=COLORS["surface"], fg=COLORS["muted"],
                     font=("Microsoft YaHei UI", 8), anchor="w").pack(fill="x", pady=(2, 0))

        ai_ready = bool(self.app.ai_ready())
        ai_card = tk.Frame(self.body,
                           bg=COLORS["mint_soft"] if ai_ready else COLORS["surface"],
                           padx=13, pady=10, highlightthickness=1,
                           highlightbackground=COLORS["line"])
        ai_card.pack(fill="x", pady=(0, 12))
        ai_info = tk.Frame(ai_card, bg=ai_card.cget("bg"))
        ai_info.pack(side="left", fill="x", expand=True)
        tk.Label(ai_info, text="AI 邮件分析",
                 bg=ai_card.cget("bg"), fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x")
        tk.Label(ai_info, text=("已启用：可在邮件详情点「AI 建任务」" if ai_ready
                               else "未启用：配置 API 后可拆分项目、自动生成任务草稿"),
                 bg=ai_card.cget("bg"), fg=COLORS["muted"],
                 font=("Microsoft YaHei UI", 8), anchor="w", justify="left",
                 wraplength=270).pack(fill="x", pady=(2, 0))
        PillButton(ai_card, "AI 设置" if not ai_ready else "设置",
                   self.app.open_ai_settings, kind="primary" if not ai_ready else "ghost",
                   width=68, height=30).pack(side="right", padx=(8, 0))

        # Filter chips.
        chips = tk.Frame(self.body, bg=COLORS["bg"])
        chips.pack(fill="x", pady=(0, 11))
        options = [
            ("all", "全部", len(emails)),
            ("action", "建议处理", len(actionable)),
            ("linked", "已关联", len([e for e in emails if intent_of(e) == "linked"])),
            ("unread", "未读", unread),
        ]
        for key, label, count in options:
            chip = Chip(chips, label, command=lambda k=key: self.set_filter(k),
                        selected=self.filter == key, count=count, height=27,
                        font=("Microsoft YaHei UI", 8))
            chip.pack(side="left", padx=(0, 5))

        filtered = self._filtered()
        if filtered:
            for email in filtered:
                MailCard(self.body, self.app, email).pack(fill="x", pady=(0, 9))
        elif not emails:
            EmptyState(self.body, "收件箱还是空的",
                       "同步钉钉邮箱，或导入一封 .eml 邮件开始解析。",
                       "去连接邮箱", lambda: self.app.switch_page("settings"),
                       icon="mail").pack(fill="x")
        else:
            EmptyState(self.body, "没有这个分组的邮件",
                       "换一个筛选条件看看。",
                       "查看全部", lambda: self.set_filter("all"),
                       icon="mail").pack(fill="x")

        tk.Frame(self.body, bg=COLORS["bg"], height=20).pack(fill="x")
        self.body.update_idletasks()
        self.scroll.refresh()
        target = yview[0] if yview else 0
        self.after_idle(lambda: self.scroll.canvas.yview_moveto(target))


class MailCard(tk.Frame):
    def __init__(self, parent, app, email):
        self.app = app
        self.email = email
        analysis = email.get("analysis") or {}
        linked = bool(analysis.get("linked_task_id") or analysis.get("linked_task_ids"))
        unread = not email.get("read")
        tk.Frame.__init__(self, parent, bg=COLORS["surface"], bd=0,
                          highlightthickness=1, highlightbackground=COLORS["line"])
        if unread:
            strip = tk.Frame(self, bg=COLORS["accent"], width=2)
            strip.pack(side="left", fill="y")
            strip.pack_propagate(False)
        inner = tk.Frame(self, bg=COLORS["surface"], padx=13, pady=11)
        inner.pack(side="left", fill="both", expand=True)

        top = tk.Frame(inner, bg=COLORS["surface"])
        top.pack(fill="x")
        if unread:
            dot = tk.Canvas(top, width=6, height=6, bg=COLORS["surface"],
                            highlightthickness=0, bd=0)
            dot.create_oval(0, 0, 6, 6, fill=COLORS["accent"], outline=COLORS["accent"])
            dot.pack(side="left", padx=(0, 6), pady=(4, 0))
        sender = tk.Label(top, text=truncate(email.get("sender", "未知发件人"), 18),
                          bg=COLORS["surface"], fg=COLORS["ink_soft"],
                          font=("Microsoft YaHei UI", 8, "bold"), anchor="w")
        sender.pack(side="left")
        tk.Label(top, text=mail_time(email.get("date")), bg=COLORS["surface"],
                 fg=COLORS["faint"], font=("Microsoft YaHei UI", 8)).pack(side="right")

        subject = tk.Label(inner, text=truncate(email.get("subject", "（无主题）"), 42),
                           bg=COLORS["surface"], fg=COLORS["ink"],
                           font=("Microsoft YaHei UI", 10, "bold"), anchor="w",
                           justify="left", wraplength=345)
        subject.pack(fill="x", pady=(4, 2))
        snippet = tk.Label(inner, text=truncate(email.get("snippet") or email.get("body", ""), 78),
                           bg=COLORS["surface"], fg=COLORS["muted"],
                           font=("Microsoft YaHei UI", 8), anchor="w", justify="left",
                           wraplength=345)
        snippet.pack(fill="x")

        footer = tk.Frame(inner, bg=COLORS["surface"])
        footer.pack(fill="x", pady=(7, 0))
        intent = intent_of(email)
        label, fg, soft = INTENT_META[intent]
        tk.Label(footer, text=label, bg=soft, fg=fg, font=("Microsoft YaHei UI", 7, "bold"),
                 padx=6, pady=1).pack(side="left")
        if email.get("demo"):
            tk.Label(footer, text="示例", bg=COLORS["surface_alt"], fg=COLORS["faint"],
                     font=("Microsoft YaHei UI", 7), padx=5, pady=1).pack(side="left", padx=(5, 0))
        if linked:
            linked_tasks = linked_tasks_of(app.store, email)
            if linked_tasks:
                suffix = " 等 %d 个任务" % len(linked_tasks) if len(linked_tasks) > 1 else ""
                tk.Label(footer, text="→ " + truncate(linked_tasks[0].get("title", ""), 20) + suffix,
                         bg=COLORS["surface"], fg=COLORS["mint"],
                         font=("Microsoft YaHei UI", 7)).pack(side="left", padx=(6, 0))
        elif analysis.get("matches"):
            prefix = "相近 " if intent == "new" else "→ "
            tk.Label(footer, text=prefix + truncate(analysis["matches"][0].get("title", ""), 19),
                     bg=COLORS["surface"], fg=COLORS["faint"],
                     font=("Microsoft YaHei UI", 7)).pack(side="left", padx=(6, 0))

        for widget in self._descendants(self):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", self._open)

    @staticmethod
    def _descendants(widget):
        items = [widget]
        for child in widget.winfo_children():
            items.extend(MailCard._descendants(child))
        return items

    def _open(self, _event):
        self.app.open_mail_detail(self.email)


class MailDetail(Modal):
    def __init__(self, app, email):
        self.email = email
        self.analysis = email.get("analysis") or {}
        super(MailDetail, self).__init__(app, "邮件详情", "只读 · 本机解析")
        self._build()

    def _build(self):
        body = self.content
        email = self.email
        analysis = self.analysis
        if email.get("demo"):
            tk.Label(body, text="示例邮件", bg=COLORS["surface_alt"], fg=COLORS["faint"],
                     font=("Microsoft YaHei UI", 8), padx=7, pady=2).pack(anchor="w", pady=(0, 7))
        tk.Label(body, text=email.get("subject", "（无主题）"), bg=COLORS["bg"],
                 fg=COLORS["ink"], font=("Microsoft YaHei UI", 15, "bold"),
                 anchor="w", justify="left", wraplength=345).pack(fill="x")
        meta = tk.Frame(body, bg=COLORS["bg"])
        meta.pack(fill="x", pady=(7, 14))
        tk.Label(meta, text="%s  <%s>" % (email.get("sender", ""), email.get("sender_email", "")),
                 bg=COLORS["bg"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 8)).pack(side="left")
        tk.Label(meta, text=mail_time(email.get("date")), bg=COLORS["bg"],
                 fg=COLORS["faint"], font=("Microsoft YaHei UI", 8)).pack(side="right")

        card = tk.Frame(body, bg=COLORS["surface"], highlightthickness=1,
                        highlightbackground=COLORS["line"])
        card.pack(fill="x", pady=(0, 14))
        top = tk.Frame(card, bg=COLORS["surface"], padx=13, pady=10)
        top.pack(fill="x")
        tk.Label(top, text="任务建议", bg=COLORS["surface"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        tk.Label(top, text="可信度 " + confidence_label(analysis.get("confidence")),
                 bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8)).pack(side="right")
        tk.Frame(card, bg=COLORS["line_soft"], height=1).pack(fill="x")

        inner = tk.Frame(card, bg=COLORS["surface"], padx=13, pady=11)
        inner.pack(fill="x")
        intent = analysis.get("intent") or "info"
        label, fg, soft = INTENT_META.get(intent, INTENT_META["info"])
        tk.Label(inner, text=label, bg=soft, fg=fg, font=("Microsoft YaHei UI", 8, "bold"),
                 padx=7, pady=2).pack(anchor="w")
        linked_tasks = linked_tasks_of(self.app.store, self.email)
        if linked_tasks:
            tk.Label(inner, text="这封邮件已关联到 %d 个任务" % len(linked_tasks),
                     bg=COLORS["surface"], fg=COLORS["mint"],
                     font=("Microsoft YaHei UI", 9, "bold"), anchor="w",
                     justify="left", wraplength=330).pack(fill="x", pady=(7, 0))
            for linked_task in linked_tasks[:5]:
                label = tk.Label(
                    inner, text="· " + truncate(linked_task.get("title", "任务"), 28),
                    bg=COLORS["surface"], fg=COLORS["accent"],
                    font=("Microsoft YaHei UI", 8), anchor="w", cursor="hand2")
                label.pack(fill="x", padx=(6, 0), pady=(2, 0))
                label.bind("<Button-1>", lambda _e, task=linked_task: self._open_linked(task))
        elif intent == "info":
            tk.Label(inner, text="没有发现明确的待办动作，暂时不需要新建任务。",
                     bg=COLORS["surface"], fg=COLORS["muted"],
                     font=("Microsoft YaHei UI", 9), anchor="w", justify="left",
                     wraplength=330).pack(fill="x", pady=(7, 0))
        else:
            tk.Label(inner, text=analysis.get("title") or email.get("subject", ""),
                     bg=COLORS["surface"], fg=COLORS["ink"],
                     font=("Microsoft YaHei UI", 10, "bold"), anchor="w",
                     justify="left", wraplength=330).pack(fill="x", pady=(7, 0))
            if analysis.get("requirement"):
                tk.Label(inner, text=analysis["requirement"], bg=COLORS["surface"],
                         fg=COLORS["muted"], font=("Microsoft YaHei UI", 8),
                         anchor="w", justify="left", wraplength=330).pack(fill="x", pady=(3, 0))
            facts = tk.Frame(inner, bg=COLORS["surface"])
            facts.pack(fill="x", pady=(7, 0))
            if analysis.get("due"):
                dt = model.parse_dt(analysis["due"])
                if dt:
                    tk.Label(facts, text="截止 " + dt.strftime("%m/%d %H:%M"),
                             bg=COLORS["amber_soft"], fg=COLORS["amber"],
                             font=("Microsoft YaHei UI", 8, "bold"), padx=6, pady=1).pack(side="left")
            if analysis.get("owner"):
                tk.Label(facts, text="负责人 " + analysis["owner"], bg=COLORS["surface_alt"],
                         fg=COLORS["ink_soft"], font=("Microsoft YaHei UI", 8),
                         padx=6, pady=1).pack(side="left", padx=(5, 0))
            if analysis.get("progress") is not None:
                tk.Label(facts, text="进度 %d%%" % analysis["progress"], bg=COLORS["blue_soft"],
                         fg=COLORS["blue"], font=("Microsoft YaHei UI", 8),
                         padx=6, pady=1).pack(side="left", padx=(5, 0))
            if analysis.get("done_hint"):
                tk.Label(facts, text="邮件称已交付", bg=COLORS["mint_soft"], fg=COLORS["mint"],
                         font=("Microsoft YaHei UI", 8), padx=6, pady=1).pack(side="left", padx=(5, 0))

            matches = analysis.get("matches") or []
            if matches and not analysis.get("linked_task_id"):
                tk.Frame(inner, bg=COLORS["line_soft"], height=1).pack(fill="x", pady=(9, 7))
                tk.Label(inner, text="可能相关的任务", bg=COLORS["surface"], fg=COLORS["faint"],
                         font=("Microsoft YaHei UI", 8, "bold"), anchor="w").pack(fill="x")
                for match in matches[:2]:
                    row = tk.Frame(inner, bg=COLORS["surface"])
                    row.pack(fill="x", pady=(3, 0))
                    tk.Label(row, text="· " + truncate(match.get("title", ""), 24),
                             bg=COLORS["surface"], fg=COLORS["ink_soft"],
                             font=("Microsoft YaHei UI", 8), anchor="w").pack(side="left")
                    tk.Label(row, text="%d%%" % int(match.get("score", 0) * 100),
                             bg=COLORS["surface"], fg=COLORS["faint"],
                             font=("Microsoft YaHei UI", 8)).pack(side="right")

        tk.Label(body, text="邮件正文", bg=COLORS["bg"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x", pady=(0, 6))
        body_label = tk.Label(
            body, text=email.get("body", "") or "（无正文）", bg=COLORS["surface_alt"],
            fg=COLORS["ink_soft"], font=("Microsoft YaHei UI", 9), anchor="nw",
            justify="left", wraplength=348, padx=12, pady=10,
            highlightthickness=1, highlightbackground=COLORS["line"],
        )
        body_label.pack(fill="x")
        tk.Frame(body, bg=COLORS["bg"], height=16).pack(fill="x")

        # Footer actions.
        linked_tasks = linked_tasks_of(self.app.store, self.email)
        linked_task = linked_tasks[0] if linked_tasks else None
        projects = analysis.get("projects") or []
        if projects:
            self.add_footer_button("查看任务", self._open_ai_summary,
                                   kind="primary", width=82)
            self.add_footer_button("复扫", self._rescan_mail, kind="ghost", width=56)
            if linked_tasks:
                self.add_footer_button("取消关联", self._unlink, kind="ghost", width=76)
            else:
                self.add_footer_button("关联已有", lambda: self.app.open_link_dialog(self.email),
                                       kind="ghost", width=76)
        elif linked_tasks:
            if len(linked_tasks) > 1:
                self.add_footer_button(
                    "查看全部 %d 个" % len(linked_tasks), self._open_all_linked,
                    kind="primary", width=100)
            else:
                self.add_footer_button(
                    "查看任务", lambda: self._open_linked(linked_task),
                    kind="primary")
            self.add_footer_button("取消关联", self._unlink, kind="ghost", width=76)
        else:
            is_update = analysis.get("intent") == "update" and analysis.get("matches")
            if is_update:
                self.add_footer_button(
                    "更新任务", lambda: self.app.apply_mail_update(self.email),
                    kind="primary", width=88)
            if self.app.ai_ready():
                self.add_footer_button(
                    "AI 建任务", lambda: self.app.ai_create_task_from_email(self.email),
                    kind="ghost" if is_update else "primary", width=82)
            else:
                self.add_footer_button(
                    "AI 建任务", lambda: self.app.ai_create_task_from_email(self.email),
                    kind="ghost", width=82)
            if analysis.get("intent") == "new":
                self.add_footer_button(
                    "创建任务", lambda: self.app.create_task_from_email(self.email),
                    kind="ghost" if self.app.ai_ready() else "primary", width=90)
            elif not is_update:
                self.add_footer_button(
                    "转为任务", lambda: self.app.create_task_from_email(self.email),
                    kind="ghost", width=82)
        if not projects:
            if not linked_task:
                self.add_footer_button("关联已有", lambda: self.app.open_link_dialog(self.email),
                                       kind="ghost", width=76)
            else:
                self.add_footer_button("重新关联", lambda: self.app.open_link_dialog(self.email),
                                       kind="ghost", width=76)
        read_btn = PillButton(self.footer_left, "标记未读", self._mark_unread,
                              kind="ghost", width=68, height=34)
        read_btn.pack(pady=17)

    def _open_linked(self, task):
        self.force_close()
        self.app.open_task_view(task)

    def _open_all_linked(self):
        linked = linked_tasks_of(self.app.store, self.email)
        if not linked:
            return
        ids = [task["id"] for task in linked]
        self.force_close()
        self.app.show_tasks(ids, "这封邮件关联的 %d 个任务" % len(ids))

    def _open_ai_summary(self):
        self.force_close()
        AIProjectSummaryDialog(self.app, self.email)

    def _rescan_mail(self):
        email = self.email
        self.force_close()
        self.app.rescan_email(email)

    def _unlink(self):
        self.app.confirm(
            "取消邮件关联？",
            "任务和邮件都会保留，只是不再互相关联。",
            "取消关联",
            lambda: self.app.unlink_email_from_task(self.email),
        )

    def _mark_unread(self):
        self.email["read"] = False
        self.app.store.save()
        self.force_close()

    def force_close(self):
        super(MailDetail, self).force_close()
        self.app.refresh()


class AIProjectReviewDialog(Modal):
    """Review AI-split projects and choose how each one lands in the task list."""

    ACTIONS = (("new", "新建任务"), ("update", "追加到现有"),
               ("subtask", "作为子任务"), ("ignore", "忽略"))

    def __init__(self, app, email, analysis):
        self.app = app
        self.email = email
        self.analysis = analysis
        email["analysis"] = analysis
        self.projects = list(analysis.get("projects") or [])
        self.tasks = [task for task in app.store.tasks if not task.get("archived")]
        self.rows = []
        Modal.__init__(self, app, "AI 项目梳理",
                      "检查项目并选择处理方式；执行后仍可在任务清单中编辑")
        self._build()

    def _build(self):
        body = self.content
        tk.Label(body, text=self.analysis.get("email_summary") or
                 "AI 从这封邮件中整理了以下项目：",
                 bg=COLORS["bg"], fg=COLORS["muted"],
                 font=("Microsoft YaHei UI", 8), anchor="w", justify="left",
                 wraplength=340).pack(fill="x", pady=(0, 10))
        for index, project in enumerate(self.projects, 1):
            self._project_card(body, index, project)
        PillButton(self.footer_left, "取消", self.force_close, kind="ghost",
                   width=58, height=32).pack(side="left", padx=16)
        PillButton(self.footer_right, "全部执行", self._apply, kind="primary",
                   width=88, height=34).pack(side="right", padx=16)

    def _project_card(self, parent, index, project):
        card = tk.Frame(parent, bg=COLORS["surface"], padx=11, pady=9,
                        highlightthickness=1, highlightbackground=COLORS["line"])
        card.pack(fill="x", pady=(0, 8))
        head = tk.Frame(card, bg=COLORS["surface"])
        head.pack(fill="x")
        tk.Label(head, text="项目 %02d  %s" % (index, project.get("title") or "未命名项目"),
                 bg=COLORS["surface"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 9, "bold"), anchor="w",
                 justify="left", wraplength=285).pack(side="left", fill="x", expand=True)
        tk.Label(head, text="可信度 " + confidence_label(project.get("confidence")),
                 bg=COLORS["surface_alt"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 7), padx=5, pady=1).pack(side="right")
        if project.get("summary"):
            tk.Label(card, text=project["summary"], bg=COLORS["surface"],
                     fg=COLORS["muted"], font=("Microsoft YaHei UI", 8),
                     anchor="w", justify="left", wraplength=330).pack(fill="x", pady=(4, 0))
        if project.get("requirement"):
            tk.Label(card, text=truncate(project["requirement"], 420),
                     bg=COLORS["surface"], fg=COLORS["ink_soft"],
                     font=("Microsoft YaHei UI", 8), anchor="w",
                     justify="left", wraplength=330).pack(fill="x", pady=(3, 0))
        facts = []
        if project.get("status"):
            facts.append("状态 " + project["status"])
        if project.get("contract_amount"):
            facts.append("金额 " + project["contract_amount"])
        if project.get("owner"):
            facts.append("负责人 " + project["owner"])
        due = model.parse_dt(project.get("due"))
        if due:
            facts.append("截止 " + due.strftime("%m/%d %H:%M"))
        if project.get("match_reason"):
            facts.append(project["match_reason"])
        if facts:
            tk.Label(card, text=" · ".join(facts), bg=COLORS["surface"],
                     fg=COLORS["faint"], font=("Microsoft YaHei UI", 7),
                     anchor="w", justify="left", wraplength=330).pack(fill="x", pady=(3, 0))
        if project.get("next_action"):
            tk.Label(card, text="下一步：" + truncate(project["next_action"], 120),
                     bg=COLORS["surface"], fg=COLORS["ink_soft"],
                     font=("Microsoft YaHei UI", 7), anchor="w",
                     justify="left", wraplength=330).pack(fill="x", pady=(3, 0))

        action_row = tk.Frame(card, bg=COLORS["surface"])
        action_row.pack(fill="x", pady=(7, 0))
        default_action = project.get("relation") or "new"
        if default_action not in ("new", "update", "subtask"):
            default_action = "ignore"
        if default_action in ("update", "subtask") and not self.tasks:
            default_action = "new"
        target_var = tk.StringVar()
        target_map = {}
        for task in self.tasks:
            label = "%s  (%s)" % (truncate(task.get("title", "任务"), 18),
                                  task.get("owner") or "待指派")
            target_map[label] = task.get("id")
            if task.get("id") == project.get("target_task_id"):
                target_var.set(label)
        if not target_var.get() and self.tasks:
            target_var.set(next(iter(target_map)))
        row_state = {"project": project, "action": default_action,
                     "target_var": target_var, "target_map": target_map}
        self.rows.append(row_state)
        action_chips = {}
        for key, label in self.ACTIONS:
            chip = Chip(action_row, label, command=lambda k=key, r=row_state: self._select_action(r, k),
                        selected=key == default_action, height=24,
                        font=("Microsoft YaHei UI", 7))
            chip.pack(side="left", padx=(0, 3))
            action_chips[key] = chip
        row_state["chips"] = action_chips
        parent_row = tk.Frame(card, bg=COLORS["surface"])
        parent_row.pack(fill="x", pady=(5, 0))
        tk.Label(parent_row, text="父任务", bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 7), width=5, anchor="w").pack(side="left")
        combo = ttk.Combobox(parent_row, textvariable=target_var,
                             values=list(target_map.keys()), state="readonly",
                             width=14, font=("Microsoft YaHei UI", 7))
        combo.pack(side="left", padx=(2, 0))
        row_state["combo"] = combo
        PillButton(parent_row, "选父任务", lambda r=row_state: self._choose_parent(r),
                   kind="soft", width=64, height=24).pack(side="left", padx=(5, 0))
        parent_label = tk.Label(card, text="父任务：未选择", bg=COLORS["surface"],
                                fg=COLORS["faint"], font=("Microsoft YaHei UI", 7),
                                anchor="w", wraplength=330)
        parent_label.pack(fill="x", pady=(4, 0))
        row_state["parent_label"] = parent_label
        changes = project.get("changes") or []
        if changes or project.get("suggest_subtask"):
            diff = tk.Frame(card, bg=COLORS["surface_alt"], padx=8, pady=6,
                            highlightthickness=1, highlightbackground=COLORS["line_soft"])
            diff.pack(fill="x", pady=(6, 0))
            tk.Label(diff, text="与上一期任务的差异", bg=COLORS["surface_alt"],
                     fg=COLORS["accent"], font=("Microsoft YaHei UI", 7, "bold"),
                     anchor="w").pack(fill="x")
            for change in changes:
                tk.Label(diff, text="• " + change, bg=COLORS["surface_alt"],
                         fg=COLORS["ink_soft"], font=("Microsoft YaHei UI", 7),
                         anchor="w", justify="left", wraplength=310).pack(fill="x", pady=(2, 0))
            if project.get("suggest_subtask"):
                hint = project.get("subtask_title") or "把上述差异新增为子任务"
                tk.Label(diff, text="AI 建议：" + hint, bg=COLORS["surface_alt"],
                         fg=COLORS["ink_soft"], font=("Microsoft YaHei UI", 7, "bold"),
                         anchor="w", justify="left", wraplength=310).pack(fill="x", pady=(4, 0))
            diff_var = tk.BooleanVar(value=False)
            row_state["diff_var"] = diff_var
            tk.Checkbutton(
                diff, text="将差异添加为子任务", variable=diff_var,
                command=lambda r=row_state: self._toggle_diff_subtask(r),
                bg=COLORS["surface_alt"], fg=COLORS["accent"],
                activebackground=COLORS["surface_alt"], activeforeground=COLORS["accent"],
                selectcolor=COLORS["surface"], font=("Microsoft YaHei UI", 7),
                anchor="w").pack(fill="x", pady=(4, 0))
        self._sync_action(row_state)

    def _choose_parent(self, row):
        ParentTaskDialog(self.app, lambda task: self._set_parent(row, task))

    def _set_parent(self, row, task):
        label = "%s  (%s)" % (truncate(task.get("title", "任务"), 18),
                              task.get("owner") or "待指派")
        if label in row["target_map"] and row["target_map"][label] != task.get("id"):
            label += " #%s" % str(task.get("id"))[:5]
        row["target_map"][label] = task.get("id")
        row["combo"].configure(values=list(row["target_map"].keys()))
        row["target_var"].set(label)
        row["parent_label"].configure(text="父任务：" + label, fg=COLORS["accent"])
        self._select_action(row, "subtask")

    def _select_action(self, row, action):
        row["action"] = action
        for key, chip in row["chips"].items():
            chip.set_selected(key == action)
        if row.get("diff_var") is not None:
            row["diff_var"].set(action == "subtask")
        self._sync_action(row)

    def _toggle_diff_subtask(self, row):
        if row.get("diff_var") is not None and row["diff_var"].get():
            self._select_action(row, "subtask")
        elif row["action"] == "subtask":
            self._select_action(row, "new")

    def _sync_action(self, row):
        needs_target = row["action"] in ("update", "subtask")
        if needs_target and not row["target_map"]:
            row["action"] = "new"
            for key, chip in row["chips"].items():
                chip.set_selected(key == "new")
            if row.get("diff_var") is not None:
                row["diff_var"].set(False)
            needs_target = False
        if needs_target:
            if not row["combo"].winfo_ismapped():
                row["combo"].pack(side="left", padx=(5, 0))
            row["combo"].configure(state="readonly")
        else:
            row["combo"].pack_forget()

    def _apply(self):
        linked_ids = []
        created = updated = subadded = 0
        for row in self.rows:
            project = row["project"]
            action = row["action"]
            if action == "ignore":
                continue
            target_id = row["target_map"].get(row["target_var"].get())
            target = self.app.store.task(target_id) if target_id else None
            if action == "new":
                owner_name, owner_username = self.app.resolve_ai_owner(project.get("owner"))
                task = model.create_task(
                    title=project.get("title") or "AI 邮件项目",
                    requirement=project.get("requirement") or "",
                    due=project.get("due"),
                    owner=owner_name,
                    owner_username=owner_username,
                )
                task["source_email_id"] = self.email.get("id")
                self.app.store.add_task(task)
                project["task_id"] = task["id"]
                project["applied_action"] = "new"
                project["applied_at"] = model.iso(model.now())
                project["ignored"] = False
                linked_ids.append(task["id"])
                created += 1
            elif action == "update" and target:
                note = "AI 邮件补充：%s" % (project.get("requirement") or project.get("summary") or "")
                model.add_note(target, note[:1000], email_id=self.email.get("id"))
                project["task_id"] = target["id"]
                project["applied_action"] = "update"
                project["applied_at"] = model.iso(model.now())
                project["ignored"] = False
                linked_ids.append(target["id"])
                updated += 1
            elif action == "subtask" and target:
                owner_name, owner_username = self.app.resolve_ai_owner(project.get("owner"))
                model.add_subtask(
                    target,
                    project.get("subtask_title") or project.get("title") or "AI 子任务",
                    due=project.get("due"),
                    owner=owner_name, owner_username=owner_username,
                    requirement=analyzer.ai_subtask_requirement(project),
                )
                model.add_note(target, "AI 邮件分析新增子任务：%s" % (
                    project.get("requirement") or project.get("summary") or ""),
                    email_id=self.email.get("id"))
                project["task_id"] = target["id"]
                project["applied_action"] = "subtask"
                project["applied_at"] = model.iso(model.now())
                project["ignored"] = False
                linked_ids.append(target["id"])
                subadded += 1
            elif action == "ignore":
                project["ignored"] = True
                project["applied_action"] = "ignore"
                project["applied_at"] = model.iso(model.now())
        if linked_ids:
            linked_ids = list(dict.fromkeys(linked_ids))
            self.app.store.link_email_many(
                self.email.get("id"), linked_ids,
                note="AI 邮件关联：%s" % truncate(self.email.get("subject", ""), 30))
        self.app.store.save()
        self.app.refresh()
        self.force_close()
        parts = []
        if created:
            parts.append("新建 %d 个任务" % created)
        if updated:
            parts.append("追加到 %d 个任务" % updated)
        if subadded:
            parts.append("新增 %d 个子任务" % subadded)
        AIProjectSummaryDialog(self.app, self.email)
        self.app.toast.show("、".join(parts) if parts else "未执行任何项目", "success", 3600)


class ParentTaskDialog(Modal):
    """Search and choose a parent task for an AI project."""

    def __init__(self, app, callback, exclude_id=None):
        self.app = app
        self.callback = callback
        self.exclude_id = exclude_id
        self.tasks = [task for task in app.store.active_tasks()
                      if not task.get("archived") and task.get("id") != exclude_id]
        Modal.__init__(self, app, "选择父任务", "选中后，AI 项目会作为该任务的子任务")
        self._build()

    def _build(self):
        Body = self.content
        search_row = tk.Frame(Body, bg=COLORS["surface"], padx=9, pady=6,
                              highlightthickness=1, highlightbackground=COLORS["line"])
        search_row.pack(fill="x", pady=(0, 9))
        tk.Label(search_row, text="⌕", bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 11, "bold")).pack(side="left")
        self.search_var = tk.StringVar()
        entry = tk.Entry(search_row, textvariable=self.search_var, bd=0,
                         bg=COLORS["surface"], fg=COLORS["ink"],
                         insertbackground=COLORS["ink"],
                         font=("Microsoft YaHei UI", 9), highlightthickness=0)
        entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.search_var.trace_add("write", lambda *_args: self._render())
        self.list_frame = tk.Frame(Body, bg=COLORS["bg"])
        self.list_frame.pack(fill="both", expand=True)
        PillButton(self.footer_left, "取消", self.force_close, kind="ghost",
                   width=58, height=32).pack(side="left", padx=16)
        self._render()

    def _render(self):
        for child in self.list_frame.winfo_children():
            child.destroy()
        query = self.search_var.get().strip().lower()
        tasks = [task for task in self.tasks if not query or query in (
            str(task.get("title") or "") + " " + str(task.get("owner") or "")).lower()]
        if not tasks:
            tk.Label(self.list_frame, text="没有可选的父任务", bg=COLORS["bg"],
                     fg=COLORS["faint"], font=("Microsoft YaHei UI", 9)).pack(anchor="w")
            return
        for task in tasks:
            row = tk.Frame(self.list_frame, bg=COLORS["surface"], padx=10, pady=8,
                           highlightthickness=1, highlightbackground=COLORS["line"])
            row.pack(fill="x", pady=(0, 5))
            text = tk.Frame(row, bg=COLORS["surface"])
            text.pack(side="left", fill="x", expand=True)
            tk.Label(text, text=truncate(task.get("title") or "未命名任务", 32),
                     bg=COLORS["surface"], fg=COLORS["ink"],
                     font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x")
            tk.Label(text, text="负责人 %s · %s" % (
                task.get("owner") or "待指派", task.get("cycle") or "一次性"),
                bg=COLORS["surface"], fg=COLORS["faint"],
                font=("Microsoft YaHei UI", 7), anchor="w").pack(fill="x", pady=(2, 0))
            PillButton(row, "选择", lambda t=task: self._choose(t), kind="soft",
                       width=44, height=26).pack(side="right", padx=(7, 0))

    def _choose(self, task):
        callback = self.callback
        self.force_close()
        if callback:
            callback(task)


class AIProjectSummaryDialog(Modal):

    def __init__(self, app, email):
        self.app = app
        self.email = email
        self.analysis = email.get("analysis") or {}
        Modal.__init__(self, app, "AI 任务清单", "这封邮件已创建和未创建的项目")
        self._build_footer()
        self._render()

    def _build_footer(self):
        PillButton(self.footer_left, "关闭", self.force_close, kind="ghost",
                   width=58, height=32).pack(side="left", padx=16)
        PillButton(self.footer_left, "重新分析", self._rescan, kind="ghost",
                   width=76, height=32).pack(side="left", padx=(0, 6))
        self.tasklist_btn = PillButton(self.footer_right, "查看任务清单",
                                       self._show_tasks, kind="primary",
                                       width=100, height=34)
        self.tasklist_btn.pack(side="right", padx=16)

    def _rescan(self):
        email = self.email
        self.force_close()
        self.app.rescan_email(email)

    def _projects(self):
        return [p for p in (self.analysis.get("projects") or []) if isinstance(p, dict)]

    def _task(self, project):
        task_id = project.get("task_id")
        return self.app.store.task(task_id) if task_id else None

    def _render(self):
        for child in list(self.content.winfo_children()):
            child.destroy()
        projects = self._projects()
        pending = [p for p in projects if not p.get("ignored") and not p.get("task_id")]
        created = [p for p in projects if p.get("task_id")]
        ignored = [p for p in projects if p.get("ignored") and not p.get("task_id")]
        if not projects:
            EmptyState(self.content, "这封邮件还没有 AI 项目",
                       "在邮件详情点「AI 建任务」生成项目清单。").pack(fill="x")
            return
        summary = tk.Frame(self.content, bg=COLORS["surface"], padx=12, pady=10,
                           highlightthickness=1, highlightbackground=COLORS["line"])
        summary.pack(fill="x", pady=(0, 12))
        for label, value, color in (
                ("已创建 / 已处理", len(created), COLORS["mint"]),
                ("未创建", len(pending), COLORS["accent"]),
                ("已忽略", len(ignored), COLORS["faint"])):
            box = tk.Frame(summary, bg=COLORS["surface"])
            box.pack(side="left", expand=True, fill="x")
            tk.Label(box, text=str(value), bg=COLORS["surface"], fg=color,
                     font=("Microsoft YaHei UI", 14, "bold")).pack()
            tk.Label(box, text=label, bg=COLORS["surface"], fg=COLORS["faint"],
                     font=("Microsoft YaHei UI", 7)).pack()
        if pending:
            self._section("待创建", "AI 推荐但还没有落到任务清单的项目", pending, False)
        if created:
            self._section("已创建 / 已处理", "已写入任务清单的项目", created, True)
        if ignored:
            self._section("已忽略", "不会创建任务的项目", ignored, False, ignored_section=True)

    def _section(self, title, subtitle, projects, created, ignored_section=False):
        tk.Label(self.content, text="%s · %d" % (title, len(projects)),
                 bg=COLORS["bg"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 10, "bold"), anchor="w").pack(
            fill="x", pady=(6, 1))
        tk.Label(self.content, text=subtitle, bg=COLORS["bg"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 7), anchor="w").pack(fill="x", pady=(0, 6))
        for project in projects:
            self._project_card(project, created, ignored_section)

    def _project_card(self, project, created, ignored_section=False):
        card = tk.Frame(self.content, bg=COLORS["surface"], padx=11, pady=9,
                        highlightthickness=1, highlightbackground=COLORS["line"])
        card.pack(fill="x", pady=(0, 7))
        head = tk.Frame(card, bg=COLORS["surface"])
        head.pack(fill="x")
        tk.Label(head, text=project.get("title") or "未命名项目",
                 bg=COLORS["surface"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 9, "bold"), anchor="w",
                 justify="left", wraplength=270).pack(side="left", fill="x", expand=True)
        badge_text = "已创建" if created else ("已忽略" if ignored_section else "待创建")
        badge_color = COLORS["mint"] if created else (
            COLORS["faint"] if ignored_section else COLORS["accent"])
        task = self._task(project)
        if created and task is None:
            badge_text = "任务已删除"
            badge_color = COLORS["amber"]
        tk.Label(head, text=badge_text, bg=COLORS["surface_alt"], fg=badge_color,
                 font=("Microsoft YaHei UI", 7), padx=5, pady=1).pack(side="right")
        if project.get("summary"):
            tk.Label(card, text=truncate(project["summary"], 150), bg=COLORS["surface"],
                     fg=COLORS["muted"], font=("Microsoft YaHei UI", 8),
                     anchor="w", justify="left", wraplength=330).pack(fill="x", pady=(3, 0))
        if project.get("requirement"):
            tk.Label(card, text=truncate(project["requirement"], 420),
                     bg=COLORS["surface"], fg=COLORS["ink_soft"],
                     font=("Microsoft YaHei UI", 7), anchor="w",
                     justify="left", wraplength=330).pack(fill="x", pady=(3, 0))
        facts = []
        if project.get("status"):
            facts.append(project["status"])
        if project.get("contract_amount"):
            facts.append("金额 " + project["contract_amount"])
        if project.get("owner"):
            facts.append("负责人 " + project["owner"])
        due = model.parse_dt(project.get("due"))
        if due:
            facts.append("截止 " + due.strftime("%m/%d %H:%M"))
        if facts:
            tk.Label(card, text=" · ".join(facts), bg=COLORS["surface"],
                     fg=COLORS["faint"], font=("Microsoft YaHei UI", 7),
                     anchor="w", justify="left", wraplength=330).pack(fill="x", pady=(3, 0))
        task = self._task(project)
        action_row = tk.Frame(card, bg=COLORS["surface"])
        action_row.pack(fill="x", pady=(7, 0))
        if task is not None:
            tk.Label(action_row, text="关联任务：" + truncate(task.get("title", ""), 24),
                     bg=COLORS["surface"], fg=COLORS["faint"],
                     font=("Microsoft YaHei UI", 7), anchor="w").pack(side="left", fill="x", expand=True)
            PillButton(action_row, "查看", lambda: self._open_task(task),
                       kind="ghost", width=48, height=25).pack(side="right")
        elif created:
            tk.Label(action_row, text="原任务已删除；这里永久保留 AI 处理记录",
                     bg=COLORS["surface"], fg=COLORS["amber"],
                     font=("Microsoft YaHei UI", 7), anchor="w", justify="left",
                     wraplength=280).pack(side="left", fill="x", expand=True)
        elif ignored_section:
            tk.Label(action_row, text="已忽略，不会创建任务", bg=COLORS["surface"],
                     fg=COLORS["faint"], font=("Microsoft YaHei UI", 7)).pack(side="left")
            PillButton(action_row, "恢复", lambda: self._restore(project),
                       kind="ghost", width=48, height=25).pack(side="right")
        else:
            action = project.get("relation") or "new"
            label = "新建任务" if action == "new" else (
                "追加到现有" if action == "update" else "作为子任务")
            PillButton(action_row, label, lambda: self._apply_project(project),
                       kind="primary", width=86, height=27).pack(side="right")
            PillButton(action_row, "忽略", lambda: self._ignore(project),
                       kind="ghost", width=44, height=27).pack(side="right", padx=(0, 5))
        if not ignored_section:
            sub_row = tk.Frame(card, bg=COLORS["surface"])
            sub_row.pack(fill="x", pady=(5, 0))
            PillButton(sub_row, "设为现有任务的子任务", lambda: self._add_as_subtask(project),
                       kind="soft", width=148, height=25).pack(side="right")
            card.bind("<Button-3>", lambda event, p=project: self._project_menu(event, p))

    def _project_menu(self, event, project):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="设为现有任务的子任务",
                         command=lambda: self._add_as_subtask(project))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _add_as_subtask(self, project):
        task = self._task(project)
        self.force_close()
        if task is not None:
            self.app.choose_parent_for_task(task)
        else:
            self.app.choose_parent_for_ai_project(project, self.email)

    def _link(self, task_ids):
        ids = []
        for project in self._projects():
            value = project.get("task_id")
            if value and value not in ids:
                ids.append(value)
        for task_id in task_ids:
            if task_id and task_id not in ids:
                ids.append(task_id)
        if ids:
            self.app.store.link_email_many(
                self.email.get("id"), ids,
                note="AI 邮件关联：%s" % truncate(self.email.get("subject", ""), 30))
        self.app.store.save()

    def _mark(self, project, action, task_id):
        project["task_id"] = task_id
        project["applied_action"] = action
        project["applied_at"] = model.iso(model.now())
        project["ignored"] = False

    def _apply_project(self, project):
        action = project.get("relation") or "new"
        target = self.app.store.task(project.get("target_task_id")) if project.get("target_task_id") else None
        if action in ("update", "subtask") and target is None:
            action = "new"
        if action == "new":
            owner_name, owner_username = self.app.resolve_ai_owner(project.get("owner"))
            task = model.create_task(
                title=project.get("title") or "AI 邮件项目",
                requirement=project.get("requirement") or "",
                due=project.get("due"),
                owner=owner_name,
                owner_username=owner_username,
            )
            task["source_email_id"] = self.email.get("id")
            self.app.store.add_task(task)
            self._mark(project, "new", task["id"])
            self._link([task["id"]])
            message = "已创建任务"
        elif action == "update" and target:
            model.add_note(target, "AI 邮件补充：%s" % (
                project.get("requirement") or project.get("summary") or "")[:1000],
                email_id=self.email.get("id"))
            self._mark(project, "update", target["id"])
            self._link([target["id"]])
            message = "已追加到现有任务"
        elif action == "subtask" and target:
            owner_name, owner_username = self.app.resolve_ai_owner(project.get("owner"))
            model.add_subtask(target,
                              project.get("subtask_title") or project.get("title") or "AI 子任务",
                              due=project.get("due"), owner=owner_name,
                              owner_username=owner_username,
                              requirement=analyzer.ai_subtask_requirement(project))
            model.add_note(target, "AI 邮件分析新增子任务：%s" % (
                project.get("requirement") or project.get("summary") or ""),
                email_id=self.email.get("id"))
            self._mark(project, "subtask", target["id"])
            self._link([target["id"]])
            message = "已添加为子任务"
        else:
            return
        self.app.store.save()
        self.app.refresh()
        self._render()
        self.app.toast.show(message, "success", 2600)

    def _ignore(self, project):
        project["ignored"] = True
        project["applied_action"] = "ignore"
        project["applied_at"] = model.iso(model.now())
        self.app.store.save()
        self._render()

    def _restore(self, project):
        project["ignored"] = False
        project.pop("applied_at", None)
        self.app.store.save()
        self._render()

    def _open_task(self, task):
        self.app.open_task_view(task)

    def _show_tasks(self):
        ids = [p.get("task_id") for p in self._projects() if self._task(p) is not None]
        if not ids:
            self.app.toast.show("还没有已创建的任务", "info")
            return
        self.force_close()
        self.app.show_tasks(ids, "这封邮件的 AI 任务，共 %d 个" % len(ids))


class MessageDialog(Modal):
    """Incoming task message from the admin terminal."""

    QUICK_REPLIES = ("收到", "马上处理", "稍后回复")

    def __init__(self, app, messages):
        self.app = app
        self.messages = list(messages or [])
        Modal.__init__(self, app, "管理员消息", "任务沟通")
        self._build()

    def _build(self):
        body = self.content
        for message in self.messages:
            card = tk.Frame(body, bg=COLORS["surface"], padx=12, pady=10,
                            highlightthickness=1, highlightbackground=COLORS["line"])
            card.pack(fill="x", pady=(0, 10))
            head = tk.Frame(card, bg=COLORS["surface"])
            head.pack(fill="x")
            tk.Label(head, text=message.get("from_name") or message.get("from_username") or "管理员",
                     bg=COLORS["surface"], fg=COLORS["ink"],
                     font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(side="left")
            tk.Label(head, text=message.get("created_at", "")[:16].replace("T", " "),
                     bg=COLORS["surface"], fg=COLORS["faint"],
                     font=("Microsoft YaHei UI", 7)).pack(side="right")
            if message.get("task_title"):
                tk.Label(card, text="关于：" + truncate(message["task_title"], 40),
                         bg=COLORS["accent_pale"], fg=COLORS["accent"],
                         font=("Microsoft YaHei UI", 8), anchor="w",
                         padx=6, pady=3).pack(fill="x", pady=(5, 0))
            tk.Label(card, text=message.get("body") or "", bg=COLORS["surface"],
                     fg=COLORS["ink_soft"], font=("Microsoft YaHei UI", 10),
                     anchor="w", justify="left", wraplength=330).pack(
                fill="x", pady=(7, 0))
        tk.Label(body, text="快速回复", bg=COLORS["bg"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x", pady=(2, 5))
        quick_row = tk.Frame(body, bg=COLORS["bg"])
        quick_row.pack(fill="x", pady=(0, 10))
        for text in self.QUICK_REPLIES:
            Chip(quick_row, text, command=lambda value=text: self._quick(value),
                 selected=False, height=26, font=("Microsoft YaHei UI", 8)).pack(
                side="left", padx=(0, 5))
        tk.Label(body, text="回复内容", bg=COLORS["bg"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x", pady=(0, 5))
        self.reply_text = styled_text(body, "", height=4)
        self.reply_text.pack(fill="x")
        self.error = tk.Label(body, text="", bg=COLORS["bg"], fg=COLORS["danger"],
                              font=("Microsoft YaHei UI", 8), anchor="w")
        self.error.pack(fill="x", pady=(6, 0))
        PillButton(self.footer_left, "关闭", self.force_close, kind="ghost",
                   width=58, height=32).pack(side="left", padx=16)
        PillButton(self.footer_right, "发送回复", self._send, kind="primary",
                   width=88, height=34).pack(side="right", padx=16)

    def _latest(self):
        return self.messages[-1] if self.messages else {}

    def _send(self):
        text = self.reply_text.get("1.0", "end").strip()
        if not text:
            self.error.configure(text="请输入回复内容")
            return
        self.app.reply_message(self._latest().get("id"), text)
        self.force_close()

    def _quick(self, text):
        self.app.reply_message(self._latest().get("id"), text)
        self.force_close()

    def force_close(self):
        if getattr(self.app, "_message_dialog", None) is self:
            self.app._message_dialog = None
        Modal.force_close(self)


class MessageInboxDialog(Modal):
    """Read-only temporary message inbox for the client."""

    def __init__(self, app):
        self.app = app
        Modal.__init__(self, app, "临时对话", "查看管理员发来的任务消息")
        self._build()

    def _build(self):
        self.list_frame = tk.Frame(self.content, bg=COLORS["bg"])
        self.list_frame.pack(fill="both", expand=True)
        tk.Label(self.list_frame, text="正在加载消息…", bg=COLORS["bg"],
                 fg=COLORS["faint"], font=("Microsoft YaHei UI", 9)).pack(anchor="w")
        PillButton(self.footer_left, "关闭", self.force_close, kind="ghost",
                   width=58, height=32).pack(side="left", padx=16)
        self.app.load_message_threads(self._loaded, self._error)

    def _clear(self):
        for child in self.list_frame.winfo_children():
            child.destroy()

    def _error(self, exc):
        self._clear()
        tk.Label(self.list_frame, text=truncate(str(exc), 100), bg=COLORS["bg"],
                 fg=COLORS["danger"], font=("Microsoft YaHei UI", 9)).pack(anchor="w")

    def _loaded(self, data):
        self._clear()
        threads = data.get("threads") or []
        if not threads:
            tk.Label(self.list_frame, text="还没有任务消息。管理员发来消息后会显示在这里。",
                     bg=COLORS["bg"], fg=COLORS["faint"],
                     font=("Microsoft YaHei UI", 9), wraplength=330).pack(anchor="w")
            return
        read_ids = []
        for thread in threads:
            card = tk.Frame(self.list_frame, bg=COLORS["surface"], padx=11, pady=9,
                            highlightthickness=1, highlightbackground=COLORS["line"])
            card.pack(fill="x", pady=(0, 8))
            head = tk.Frame(card, bg=COLORS["surface"])
            head.pack(fill="x")
            tk.Label(head, text=thread.get("task_title") or "任务对话",
                     bg=COLORS["surface"], fg=COLORS["ink"],
                     font=("Microsoft YaHei UI", 9, "bold"), anchor="w",
                     wraplength=250).pack(side="left", fill="x", expand=True)
            if thread.get("unread"):
                tk.Label(head, text="%d 条未读" % thread["unread"], bg=COLORS["danger_soft"],
                         fg=COLORS["danger"], font=("Microsoft YaHei UI", 7, "bold"),
                         padx=5, pady=1).pack(side="right")
            for message in (thread.get("messages") or [])[-3:]:
                line = tk.Frame(card, bg=COLORS["surface"])
                line.pack(fill="x", pady=(4, 0))
                tk.Label(line, text=(message.get("from_name") or message.get("from_username") or "管理员") + "：",
                         bg=COLORS["surface"], fg=COLORS["muted"],
                         font=("Microsoft YaHei UI", 8, "bold")).pack(side="left", anchor="n")
                tk.Label(line, text=truncate(message.get("body") or "", 90),
                         bg=COLORS["surface"], fg=COLORS["ink_soft"],
                         font=("Microsoft YaHei UI", 8), anchor="w", justify="left",
                         wraplength=260).pack(side="left", fill="x", expand=True)
                if message.get("to_id") == (self.app.collab_user or {}).get("id") and not message.get("read_at"):
                    read_ids.append(message.get("id"))
            tk.Label(card, text=(thread.get("latest_at") or "")[:16].replace("T", " "),
                     bg=COLORS["surface"], fg=COLORS["faint"],
                     font=("Microsoft YaHei UI", 7), anchor="e").pack(fill="x", pady=(4, 0))
        if read_ids:
            client = self.app._collab_client()
            if client:
                self.app.run_async(lambda: client.messages_read([i for i in read_ids if i]),
                                   None, None)

    def force_close(self):
        if getattr(self.app, "_message_dialog", None) is self:
            self.app._message_dialog = None
        Modal.force_close(self)


class LinkTaskDialog(Modal):
    def __init__(self, app, email):
        self.email = email
        super(LinkTaskDialog, self).__init__(app, "关联到任务", "选择一条任务接收这封邮件的更新")
        self._build()

    def _build(self):
        body = self.content
        card = tk.Frame(body, bg=COLORS["surface"], padx=12, pady=10,
                        highlightthickness=1, highlightbackground=COLORS["line"])
        card.pack(fill="x", pady=(0, 13))
        tk.Label(card, text="当前邮件", bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8)).pack(anchor="w")
        tk.Label(card, text=truncate(self.email.get("subject", ""), 36), bg=COLORS["surface"],
                 fg=COLORS["ink_soft"], font=("Microsoft YaHei UI", 9, "bold"),
                 anchor="w", justify="left", wraplength=330).pack(fill="x", pady=(2, 0))

        tasks = model.sort_tasks(self.app.store.tasks)
        if not tasks:
            EmptyState(body, "还没有可关联的任务", "先创建一条任务，再回来关联邮件。").pack(fill="x")
            return
        tk.Label(body, text="选择任务", bg=COLORS["bg"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x", pady=(0, 6))
        for task in tasks:
            row = tk.Frame(body, bg=COLORS["surface"], padx=12, pady=9,
                           highlightthickness=1, highlightbackground=COLORS["line"])
            row.pack(fill="x", pady=(0, 6))
            info = tk.Frame(row, bg=COLORS["surface"])
            info.pack(side="left", fill="x", expand=True)
            tk.Label(info, text=truncate(task.get("title", ""), 28), bg=COLORS["surface"],
                     fg=COLORS["ink"], font=("Microsoft YaHei UI", 9, "bold"),
                     anchor="w").pack(fill="x")
            tk.Label(info, text="%s · %s · 子任务 %d/%d" % (
                task.get("owner") or "待指派", model.due_text(task),
                model.subtask_stats(task)[0], model.subtask_stats(task)[1]),
                bg=COLORS["surface"], fg=COLORS["faint"],
                font=("Microsoft YaHei UI", 8), anchor="w").pack(fill="x", pady=(1, 0))
            PillButton(row, "关联", lambda t=task: self._link(t), kind="soft",
                       width=50, height=28).pack(side="right", padx=(6, 0))
        PillButton(self.footer_right, "取消", self.request_close, kind="ghost",
                   width=62, height=36).pack(side="left", pady=16)

    def _link(self, task):
        self.app.link_email_to_task(self.email, task)

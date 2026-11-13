# -*- coding: utf-8 -*-
"""Task list page, summary hero and the task editor."""

import copy
import calendar
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from datetime import datetime, timedelta

from . import model
from .constants import COLORS, CYCLES, FILTERS, status_meta
from .date_picker import DateTimeField
from .owner_picker import OwnerField
from .ui_common import EmptyState, Modal, field_label, gap, section_card, styled_entry, styled_text, truncate
from .widgets import (CheckCircle, Chip, PillButton, ProgressSlider, ScrollFrame,
                      SmallIconButton, round_rect)


class HeroCard(tk.Canvas):
    def __init__(self, parent, data, width=382, height=150):
        tk.Canvas.__init__(self, parent, width=width, height=height,
                           bg=COLORS["bg"], highlightthickness=0, bd=0)
        self.width = width
        self.height = height
        self._draw(data)

    def _draw(self, data):
        c = self
        round_rect(c, 1, 1, self.width - 1, self.height - 1, 18,
                   fill=COLORS["dark"], outline=COLORS["dark"])
        # Quiet decorative arcs.
        c.create_oval(244, -52, 426, 118, outline=COLORS["dark_line"], width=1)
        c.create_oval(282, -20, 390, 82, outline=COLORS["dark_line"], width=1)
        c.create_oval(330, 96, 398, 164, outline=COLORS["dark_line"], width=1)

        now = datetime.now()
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        c.create_text(20, 19, anchor="w", text="%d月%d日  ·  %s" % (
            now.month, now.day, weekdays[now.weekday()]),
            fill="#A8B4AD", font=("Microsoft YaHei UI", 8))
        if data["total"] == 0:
            line1, line2 = "从第一件小事", "开始吧。"
        elif data["active"] == 0:
            line1, line2 = "清单已经清空，", "享受这份轻松。"
        elif data["overdue"]:
            line1, line2 = "先处理那件", "已经逾期的事。"
        elif data["today"]:
            line1, line2 = "今天有 %d 件事" % data["today"], "等你收尾。"
        else:
            line1, line2 = "还有 %d 件事" % data["active"], "值得被完成。"
        c.create_text(20, 48, anchor="w", text=line1, fill="#F5F1E8",
                      font=("Microsoft YaHei UI", 15, "bold"))
        c.create_text(20, 73, anchor="w", text=line2, fill="#F5F1E8",
                      font=("Microsoft YaHei UI", 15, "bold"))

        percent = data["percent"]
        cx, cy, radius = 311, 70, 34
        c.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                      outline=COLORS["dark_line"], width=6)
        if percent > 0:
            c.create_arc(cx - radius, cy - radius, cx + radius, cy + radius,
                         start=90, extent=-percent * 3.6, style="arc",
                         outline=COLORS["accent"], width=6)
        c.create_text(cx, cy - 2, text="%d%%" % percent, fill=COLORS["white"],
                      font=("Georgia", 14, "bold"))
        c.create_text(cx, cy + 18, text="总完成度", fill="#A8B4AD",
                      font=("Microsoft YaHei UI", 7))

        # Bottom status line.
        y = 128
        stats = [
            ("进行中", data["doing"], "#9CC3D3"),
            ("今日到期", data["today"], "#E8BE7B"),
            ("已逾期", data["overdue"], "#E69A8E"),
        ]
        x = 20
        for label, value, color in stats:
            c.create_oval(x, y - 3, x + 6, y + 3, fill=color, outline=color)
            text = "%s %d" % (label, value)
            c.create_text(x + 12, y, anchor="w", text=text, fill="#D8DED9",
                          font=("Microsoft YaHei UI", 8))
            x += 78 if label != "今日到期" else 88
        c.create_text(self.width - 18, y, anchor="e",
                      text="%d 项任务" % data["total"], fill="#89978F",
                      font=("Microsoft YaHei UI", 8))


class ChipStrip(tk.Frame):
    """One-line chip row that scrolls horizontally with the mouse wheel."""

    def __init__(self, parent, bg):
        tk.Frame.__init__(self, parent, bg=bg)
        self.canvas = tk.Canvas(self, height=30, bg=bg, highlightthickness=0, bd=0)
        self.canvas.pack(fill="x", expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._sync)
        self.canvas.bind("<Configure>", self._sync)
        self.canvas.bind("<MouseWheel>", self._wheel)

    def _sync(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _wheel(self, event):
        self.canvas.xview_scroll(-2 if event.delta > 0 else 2, "units")
        return "break"

    def bind_wheel(self, widget):
        widget.bind("<MouseWheel>", self._wheel, add="+")


class TaskCard(tk.Frame):
    def __init__(self, parent, app, task, manage=False, selected=False, on_select=None):
        self.app = app
        self.task = task
        self.manage = bool(manage)
        self.selected = bool(selected)
        self.on_select = on_select
        self._press_x = None
        self._press_y = None
        self._dragged = False
        status = model.status_of(task)
        meta = status_meta(status)
        accent = meta["color"]
        self.lost = bool(task.get("lost"))
        self.card_bg = COLORS["danger_soft"] if self.lost else COLORS["surface"]
        self.card_alt = COLORS["danger_soft"] if self.lost else COLORS["surface_alt"]
        tk.Frame.__init__(self, parent, bg=self.card_bg, bd=0,
                          highlightthickness=1,
                          highlightbackground=COLORS["accent"] if selected else COLORS["line"])
        self.pack_propagate(True)
        strip = tk.Frame(self, bg=accent, width=3)
        strip.pack(side="left", fill="y")
        strip.pack_propagate(False)
        self.inner = tk.Frame(self, bg=self.card_bg, padx=14, pady=12)
        self.inner.pack(side="left", fill="both", expand=True)

        title_row = tk.Frame(self.inner, bg=self.card_bg)
        title_row.pack(fill="x")
        dot = tk.Canvas(title_row, width=7, height=7, bg=self.card_bg,
                        highlightthickness=0, bd=0)
        dot.create_oval(0, 0, 7, 7, fill=accent, outline=accent)
        dot.pack(side="left", padx=(1, 7), pady=(7, 0))
        title = tk.Label(title_row, text=task.get("title", "未命名任务"),
                         bg=self.card_bg,
                         fg=COLORS["danger"] if self.lost else (COLORS["muted"] if status == "done" else COLORS["ink"]),
                         font=("Microsoft YaHei UI", 11, "bold"),
                         anchor="w", justify="left", wraplength=285)
        title.pack(side="left", fill="x", expand=True)

        chevron = None
        self.select_check = None
        if self.manage:
            self.select_check = CheckCircle(
                title_row, checked=self.selected, command=self._toggle_select,
                size=20, bg=self.card_bg, color=COLORS["accent"])
            self.select_check.pack(side="right", padx=(5, 0), pady=(1, 0))
            self.select_check._no_open = True
        else:
            chevron = tk.Label(title_row, text="›", bg=self.card_bg,
                               fg=COLORS["faint"], font=("Microsoft YaHei UI", 14))
            chevron.pack(side="right", padx=(4, 0), pady=(2, 0))

        requirement = task.get("requirement") or ""
        req = None
        if requirement:
            req = tk.Label(self.inner, text=truncate(requirement, 68),
                           bg=self.card_bg, fg=COLORS["danger"] if self.lost else COLORS["muted"],
                           font=("Microsoft YaHei UI", 9), anchor="w",
                           justify="left", wraplength=330)
            req.pack(fill="x", pady=(5, 0))

        meta_row = tk.Frame(self.inner, bg=self.card_bg)
        meta_row.pack(fill="x", pady=(9, 0))
        cycle = tk.Label(meta_row, text=task.get("cycle") or "一次性",
                         bg=self.card_alt, fg=COLORS["ink_soft"],
                         font=("Microsoft YaHei UI", 8), padx=6, pady=1)
        cycle.pack(side="left")
        due_color = COLORS["danger"] if model.due_tone(task) == "danger" else (
            COLORS["amber"] if model.due_tone(task) == "amber" else COLORS["muted"]
        )
        due_bg = COLORS["danger_soft"] if model.due_tone(task) == "danger" else (
            COLORS["amber_soft"] if model.due_tone(task) == "amber" else COLORS["surface_alt"]
        )
        due = tk.Label(meta_row, text=model.due_text(task), bg=due_bg, fg=due_color,
                       font=("Microsoft YaHei UI", 8, "bold"), padx=6, pady=1)
        due.pack(side="left", padx=(5, 0))
        owner_text = task.get("owner") or "待指派"
        owner = tk.Label(meta_row, text="负责人  " + owner_text,
                         bg=self.card_bg, fg=COLORS["faint"],
                         font=("Microsoft YaHei UI", 8))
        owner.pack(side="left", padx=(7, 0))

        tags = model.clean_tags(task.get("tags"))
        if tags:
            tag_row = tk.Frame(self.inner, bg=self.card_bg)
            tag_row.pack(fill="x", pady=(7, 0))
            for tag in tags:
                label, color, soft = model.TAG_META[tag]
                tk.Label(tag_row, text=label, bg=COLORS[soft], fg=COLORS[color],
                         font=("Microsoft YaHei UI", 7, "bold"), padx=6, pady=1).pack(
                    side="left", padx=(0, 4))

        progress_row = tk.Frame(self.inner, bg=self.card_bg)
        progress_row.pack(fill="x", pady=(10, 0))
        bar = tk.Canvas(progress_row, width=128, height=8, bg=self.card_bg,
                        highlightthickness=0, bd=0)
        bar.pack(side="left", pady=(5, 0))
        value = int(task.get("progress") or 0)
        round_rect(bar, 0, 1, 128, 7, 3, fill=COLORS["line_soft"], outline=COLORS["line_soft"])
        if value > 0:
            fill_w = max(6, int(128 * value / 100.0))
            round_rect(bar, 0, 1, fill_w, 7, 3, fill=accent, outline=accent)
        pct = tk.Label(progress_row, text="%d%%" % value, bg=self.card_bg,
                       fg=COLORS["ink_soft"], font=("Microsoft YaHei UI", 9, "bold"))
        pct.pack(side="left", padx=(8, 0), pady=(1, 0))
        done_count, total_count = model.subtask_stats(task)
        self.subtask_btn = PillButton(
            progress_row,
            "子任务 %d/%d" % (done_count, total_count) if total_count else "子任务 0",
            command=self._toggle_subtasks, kind="soft", width=70, height=23,
            font=("Microsoft YaHei UI", 7))
        self.subtask_btn.pack(side="right", padx=(5, 4), pady=(0, 1))
        self.complete_btn = PillButton(
            progress_row, "恢复" if task.get("completed") else "完成",
            command=self._toggle_complete,
            kind="ghost" if task.get("completed") else "soft",
            width=42, height=23, font=("Microsoft YaHei UI", 7))
        self.complete_btn.pack(side="right", pady=(0, 1))
        self.lost_btn = PillButton(
            progress_row, "恢复" if task.get("lost") else "流失",
            command=self._toggle_lost,
            kind="ghost" if task.get("lost") else "danger",
            width=42, height=23, font=("Microsoft YaHei UI", 7))
        self.lost_btn.pack(side="right", padx=(0, 5), pady=(0, 1))

        self.subtask_panel = tk.Frame(self.inner, bg=self.card_bg)
        self.subtask_panel.pack_forget()
        self.subtasks_open = False
        self._set_subtask_label(False)

        # Swipe hint sits above the card while the pointer drags left.
        self.hint = tk.Label(self, text="继续左拉", bg=COLORS["danger"],
                             fg=COLORS["white"], font=("Microsoft YaHei UI", 8, "bold"),
                             padx=8, pady=3)

        clickable = [self, strip, self.inner, title_row, dot, title,
                     meta_row, cycle, due, owner, progress_row, bar, pct]
        if req is not None:
            clickable.append(req)
        if chevron is not None:
            clickable.append(chevron)
        for widget in clickable:
            widget.configure(cursor="hand2")
            widget.bind("<ButtonPress-1>", self._press, add="+")
            widget.bind("<B1-Motion>", self._motion, add="+")
            widget.bind("<ButtonRelease-1>", self._release, add="+")
            widget.bind("<Button-3>", self._menu, add="+")

    def _toggle_complete(self):
        self.app.toggle_task_complete(self.task)

    def _toggle_lost(self):
        self.app.toggle_task_lost(self.task)

    def _toggle_subtasks(self):
        if self.subtasks_open:
            self.subtask_panel.pack_forget()
            self.subtasks_open = False
            self._set_subtask_label(False)
            return
        for child in list(self.subtask_panel.winfo_children()):
            child.destroy()
        subs = self.task.get("subtasks") or []
        if not subs:
            tk.Label(self.subtask_panel, text="暂无子任务", bg=self.card_bg,
                     fg=COLORS["faint"], font=("Microsoft YaHei UI", 8),
                     anchor="w", padx=4, pady=6).pack(fill="x")
        for sub in subs:
            row = tk.Frame(self.subtask_panel, bg=self.card_bg)
            row.pack(fill="x", pady=(4, 0))
            mark = "✓" if sub.get("done") else "○"
            tk.Label(row, text=mark, bg=self.card_bg,
                     fg=COLORS["mint"] if sub.get("done") else COLORS["faint"],
                     font=("Microsoft YaHei UI", 8, "bold"), width=2).pack(side="left")
            wrap = tk.Frame(row, bg=self.card_bg)
            wrap.pack(side="left", fill="x", expand=True)
            font = tkfont.Font(family="Microsoft YaHei UI", size=8,
                               overstrike=bool(sub.get("done")))
            tk.Label(wrap, text=sub.get("title", ""), bg=self.card_bg,
                     fg=COLORS["faint"] if sub.get("done") else COLORS["ink_soft"],
                     font=font, anchor="w", justify="left",
                     wraplength=250).pack(fill="x")
            if sub.get("requirement"):
                tk.Label(wrap, text=sub["requirement"], bg=self.card_bg,
                         fg=COLORS["faint"], font=("Microsoft YaHei UI", 7),
                         anchor="w", justify="left", wraplength=250).pack(fill="x")
            meta = []
            if sub.get("owner"):
                meta.append("负责人 " + sub["owner"])
            due = model.parse_dt(sub.get("due"))
            if due:
                meta.append("截止 " + due.strftime("%m/%d %H:%M"))
            tk.Label(wrap, text=" · ".join(meta) if meta else "未设置负责人/时间",
                     bg=self.card_bg, fg=COLORS["faint"],
                     font=("Microsoft YaHei UI", 7), anchor="w").pack(fill="x")
        self.subtask_panel.pack(fill="x", pady=(8, 0))
        self.subtasks_open = True
        self._set_subtask_label(True)

    def _set_subtask_label(self, open_):
        done, total = model.subtask_stats(self.task)
        base = "子任务 %d/%d" % (done, total) if total else "子任务 0"
        self.subtask_btn.set_text(base + (" ▴" if open_ else " ▾"))

    def _menu(self, event):
        menu = tk.Menu(self, tearoff=0)
        if self.manage:
            menu.add_command(label="选择 / 取消选择", command=self._toggle_select)
        else:
            menu.add_command(label="查看任务", command=self._open)
            menu.add_command(label="编辑任务", command=self._edit)
            menu.add_command(label="恢复任务" if self.task.get("completed") else "标记完成",
                             command=self._toggle_complete)
            menu.add_command(label="恢复流失" if self.task.get("lost") else "标记流失",
                             command=self._toggle_lost)
            menu.add_command(label="转为现有任务的子任务",
                             command=lambda: self.app.choose_parent_for_task(self.task))
            if self.app.collab_user:
                menu.add_command(label="转发给好友",
                                 command=lambda: self.app.open_forward_dialog(task=self.task))
            menu.add_separator()
            menu.add_command(label="删除任务", command=lambda: self.app.confirm_delete_task(self.task))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _press(self, event):
        self._press_x = event.x_root
        self._press_y = event.y_root
        self._dragged = False

    def _motion(self, event):
        if self.manage or self._press_x is None:
            return
        dx = event.x_root - self._press_x
        dy = abs(event.y_root - self._press_y)
        if dx < -24 and -dx > dy:
            self._dragged = True
            text = "松手删除" if dx < -70 else "继续左拉"
            self.hint.configure(text=text)
            self.hint.place(relx=1.0, x=-8, y=8, anchor="ne")
            tk.Misc.lift(self.hint)
            self.configure(highlightbackground=COLORS["danger"])

    def _release(self, event):
        if self.manage:
            self._toggle_select()
            return
        dx = event.x_root - (self._press_x if self._press_x is not None else event.x_root)
        dragged = self._dragged
        self._hide_hint()
        self._press_x = None
        self._press_y = None
        self._dragged = False
        if dragged:
            if dx < -70:
                self.app.confirm_delete_task(self.task)
            return
        self._open()

    def _hide_hint(self):
        try:
            self.hint.place_forget()
        except Exception:
            pass
        self.configure(highlightbackground=COLORS["accent"] if self.selected else COLORS["line"])

    def _toggle_select(self):
        if self.on_select:
            self.on_select(self.task.get("id"))

    def set_selected(self, selected):
        self.selected = bool(selected)
        if self.select_check is not None:
            self.select_check.set(self.selected)
        self.configure(highlightbackground=COLORS["accent"] if self.selected else COLORS["line"])

    def _open(self):
        if self.manage:
            self._toggle_select()
        else:
            self.app.open_task_view(self.task)

    def _edit(self):
        if self.manage:
            self._toggle_select()
        else:
            self.app.open_task_editor(self.task)


class LostReasonDialog(Modal):
    """Ask for a reason before marking a task as lost."""

    QUICK_REASONS = ("客户取消", "预算取消", "竞标失败", "需求变更", "长期无进展")

    def __init__(self, app, task, on_submit):
        self.app = app
        self.task = task
        self.on_submit = on_submit
        Modal.__init__(self, app, "标记流失", "填写流失原因，管理端可以查看")
        self._build()

    def _build(self):
        body = self.content
        tk.Label(body, text=self.task.get("title") or "未命名任务",
                 bg=COLORS["bg"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 11, "bold"), anchor="w",
                 justify="left", wraplength=330).pack(fill="x", pady=(0, 8))
        tk.Label(body, text="快速选择", bg=COLORS["bg"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 8, "bold"), anchor="w").pack(fill="x")
        quick = tk.Frame(body, bg=COLORS["bg"])
        quick.pack(fill="x", pady=(5, 10))
        for text in self.QUICK_REASONS:
            Chip(quick, text, command=lambda value=text: self._quick(value),
                 height=25, font=("Microsoft YaHei UI", 8)).pack(
                side="left", padx=(0, 5), pady=(0, 4))
        tk.Label(body, text="流失原因", bg=COLORS["bg"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 8, "bold"), anchor="w").pack(fill="x")
        self.reason_text = styled_text(body, "", height=5)
        self.reason_text.pack(fill="x", pady=(5, 0))
        self.error = tk.Label(body, text="", bg=COLORS["bg"], fg=COLORS["danger"],
                              font=("Microsoft YaHei UI", 8), anchor="w")
        self.error.pack(fill="x", pady=(5, 0))
        PillButton(self.footer_left, "取消", self.force_close, kind="ghost",
                   width=58, height=32).pack(side="left", padx=16)
        PillButton(self.footer_right, "确认流失", self._submit, kind="danger",
                   width=88, height=34).pack(side="right", padx=16)

    def _quick(self, text):
        self.reason_text.delete("1.0", "end")
        self.reason_text.insert("1.0", text)
        self.reason_text.focus_set()

    def _submit(self):
        reason = self.reason_text.get("1.0", "end").strip()
        if not reason:
            self.error.configure(text="请填写流失原因")
            return
        callback = self.on_submit
        self.force_close()
        if callback:
            callback(reason)


class TaskView(Modal):
    """Read-only task detail. Editing is explicit through the edit button."""

    def __init__(self, app, task):
        self.task_data = task
        Modal.__init__(self, app, "查看任务", "只读视图 · 点击「编辑任务」后才能修改")
        self._build()

    def _build(self):
        task = self.task_data
        body = self.content
        meta = status_meta(model.status_of(task))
        top = tk.Frame(body, bg=COLORS["bg"])
        top.pack(fill="x")
        tk.Label(top, text=task.get("title") or "未命名任务", bg=COLORS["bg"],
                 fg=COLORS["ink"], font=("Microsoft YaHei UI", 14, "bold"),
                 anchor="w", justify="left", wraplength=330).pack(
            side="left", fill="x", expand=True)
        tk.Label(top, text=meta["label"], bg=meta["soft"], fg=meta["color"],
                 font=("Microsoft YaHei UI", 8, "bold"), padx=7, pady=3).pack(
            side="right", padx=(6, 0))
        tags = model.clean_tags(task.get("tags"))
        if tags:
            tag_row = tk.Frame(body, bg=COLORS["bg"])
            tag_row.pack(fill="x", pady=(8, 0))
            for tag in tags:
                label, color, soft = model.TAG_META[tag]
                tk.Label(tag_row, text=label, bg=COLORS[soft], fg=COLORS[color],
                         font=("Microsoft YaHei UI", 8, "bold"), padx=7, pady=2).pack(
                    side="left", padx=(0, 5))

        requirement = task.get("requirement") or "未填写要求 / 交付标准"
        tk.Label(body, text=requirement, bg=COLORS["surface"], fg=COLORS["muted"],
                 font=("Microsoft YaHei UI", 9), anchor="w", justify="left",
                 wraplength=340, padx=12, pady=10).pack(fill="x", pady=(12, 10))

        if task.get("lost"):
            reason_card = tk.Frame(body, bg=COLORS["danger_soft"], padx=12, pady=9,
                                   highlightthickness=1,
                                   highlightbackground=COLORS["danger"])
            reason_card.pack(fill="x", pady=(0, 10))
            tk.Label(reason_card, text="流失原因", bg=COLORS["danger_soft"],
                     fg=COLORS["danger"], font=("Microsoft YaHei UI", 8, "bold"),
                     anchor="w").pack(fill="x")
            tk.Label(reason_card, text=task.get("lost_reason") or "未填写",
                     bg=COLORS["danger_soft"], fg=COLORS["ink_soft"],
                     font=("Microsoft YaHei UI", 9), anchor="w", justify="left",
                     wraplength=315).pack(fill="x", pady=(4, 0))

        info = tk.Frame(body, bg=COLORS["bg"])
        info.pack(fill="x", pady=(0, 10))
        start = model.parse_dt(task.get("start"))
        due = model.parse_dt(task.get("due"))
        fields = [
            ("周期", task.get("cycle") or "一次性"),
            ("开始", start.strftime("%Y-%m-%d %H:%M") if start else "未设置"),
            ("结束 / 截止", due.strftime("%Y-%m-%d %H:%M") if due else "未设置"),
            ("负责人", (task.get("owner") or "待指派") + (
                "  @" + task["owner_username"] if task.get("owner_username") else "")),
        ]
        lost_at = model.parse_dt(task.get("lost_at"))
        if task.get("lost") and lost_at:
            fields.append(("流失时间", lost_at.strftime("%Y-%m-%d %H:%M")))
        for index, (label, value) in enumerate(fields):
            row = tk.Frame(info, bg=COLORS["surface"], padx=10, pady=7)
            row.pack(fill="x", pady=(0, 4))
            tk.Label(row, text=label, bg=COLORS["surface"], fg=COLORS["faint"],
                     font=("Microsoft YaHei UI", 8), width=8, anchor="w").pack(side="left")
            tk.Label(row, text=value, bg=COLORS["surface"], fg=COLORS["ink_soft"],
                     font=("Microsoft YaHei UI", 9), anchor="w").pack(side="left", fill="x", expand=True)

        head = tk.Frame(body, bg=COLORS["bg"])
        head.pack(fill="x", pady=(4, 6))
        tk.Label(head, text="子任务", bg=COLORS["bg"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        done, total = model.subtask_stats(task)
        tk.Label(head, text="%d / %d 已完成" % (done, total), bg=COLORS["bg"],
                 fg=COLORS["faint"], font=("Microsoft YaHei UI", 8)).pack(side="right")
        subs = task.get("subtasks") or []
        if not subs:
            tk.Label(body, text="暂无子任务", bg=COLORS["surface"], fg=COLORS["faint"],
                     font=("Microsoft YaHei UI", 8), padx=12, pady=10).pack(fill="x")
        for sub in subs:
            row = tk.Frame(body, bg=COLORS["surface"], padx=10, pady=7,
                           highlightthickness=1, highlightbackground=COLORS["line_soft"])
            row.pack(fill="x", pady=(0, 4))
            tk.Label(row, text="✓" if sub.get("done") else "○", bg=COLORS["surface"],
                     fg=COLORS["mint"] if sub.get("done") else COLORS["faint"],
                     font=("Microsoft YaHei UI", 9, "bold"), width=2).pack(side="left")
            wrap = tk.Frame(row, bg=COLORS["surface"])
            wrap.pack(side="left", fill="x", expand=True)
            font = tkfont.Font(family="Microsoft YaHei UI", size=9,
                               overstrike=bool(sub.get("done")))
            tk.Label(wrap, text=sub.get("title", ""), bg=COLORS["surface"],
                     fg=COLORS["faint"] if sub.get("done") else COLORS["ink_soft"],
                     font=font, anchor="w", justify="left", wraplength=300).pack(fill="x")
            if sub.get("requirement"):
                tk.Label(wrap, text=sub["requirement"], bg=COLORS["surface"],
                         fg=COLORS["faint"], font=("Microsoft YaHei UI", 7),
                         anchor="w", justify="left", wraplength=300).pack(fill="x")
            extra = []
            if sub.get("owner"):
                extra.append("负责人 " + sub["owner"])
            sub_due = model.parse_dt(sub.get("due"))
            if sub_due:
                extra.append("截止 " + sub_due.strftime("%m/%d %H:%M"))
            tk.Label(wrap, text=" · ".join(extra) if extra else "未设置负责人/时间",
                     bg=COLORS["surface"], fg=COLORS["faint"],
                     font=("Microsoft YaHei UI", 7), anchor="w").pack(fill="x", pady=(2, 0))

        PillButton(self.footer_left, "关闭", self.force_close, kind="ghost",
                   width=48, height=32).pack(side="left", padx=12)
        PillButton(self.footer_left,
                   "恢复任务" if task.get("completed") else "标记完成",
                   self._toggle_complete, kind="soft", width=78, height=32).pack(
            side="left", padx=(0, 6))
        PillButton(self.footer_left,
                   "恢复流失" if task.get("lost") else "标记流失",
                   self._toggle_lost,
                   kind="ghost" if task.get("lost") else "danger",
                   width=78, height=32).pack(side="left", padx=(0, 6))
        PillButton(self.footer_right, "编辑任务", self._edit, kind="primary",
                   width=78, height=34).pack(side="right", padx=12)

    def _toggle_complete(self):
        if self.app.toggle_task_complete(self.task_data):
            self.force_close()

    def _toggle_lost(self):
        task = self.task_data
        self.force_close()
        self.app.toggle_task_lost(task)

    def _edit(self):
        task = self.task_data
        self.force_close()
        self.app.open_task_editor(task)


class TasksPage(tk.Frame):
    def __init__(self, parent, app):
        tk.Frame.__init__(self, parent, bg=COLORS["bg"])
        self.app = app
        self.filter = "all"
        self.date_filter = None
        self.manage = False
        self.selected = set()
        self.cards = {}
        self.subset_ids = None
        self.subset_note = ""
        self.scroll = ScrollFrame(self, bg=COLORS["bg"], padding=20, scrollbar=True)
        self.scroll.pack(fill="both", expand=True)
        self.body = self.scroll.inner
        self.search_bar = tk.Frame(self, bg=COLORS["surface"], padx=10, pady=6,
                                   highlightthickness=1, highlightbackground=COLORS["line"])
        self.search_bar.pack(fill="x", padx=20, pady=(10, 0), before=self.scroll)
        tk.Label(self.search_bar, text="⌕", bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 12, "bold")).pack(side="left", padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            self.search_bar, textvariable=self.search_var, bd=0,
            bg=COLORS["surface"], fg=COLORS["ink"], insertbackground=COLORS["ink"],
            font=("Microsoft YaHei UI", 9), highlightthickness=0)
        self.search_entry.pack(side="left", fill="x", expand=True)
        tk.Label(self.search_bar, text="搜索任务 / 负责人", bg=COLORS["surface"],
                 fg=COLORS["faint"], font=("Microsoft YaHei UI", 8)).pack(
            side="left", padx=(4, 0))
        SmallIconButton(self.search_bar, "×", self.clear_search,
                        bg=COLORS["surface"], size=22, fg=COLORS["faint"]).pack(
            side="right", padx=(4, 0))
        self.search_var.trace_add("write", self._on_search_changed)
        self.search_query = ""
        self._search_after = None
        self.add_btn = PillButton(self, "＋  新建任务", self.app.new_task,
                                  kind="primary", height=44, width=124)
        self.add_btn.place(relx=1.0, rely=1.0, x=-20, y=-18, anchor="se")
        self._build_manage_bar()
        self.refresh()

    def _build_manage_bar(self):
        self.manage_bar = tk.Frame(self, bg=COLORS["surface"], bd=0,
                                   highlightthickness=1, highlightbackground=COLORS["line"])
        inner = tk.Frame(self.manage_bar, bg=COLORS["surface"])
        inner.pack(fill="x", padx=10, pady=8)
        self.manage_count = tk.Label(inner, text="已选 0 项", bg=COLORS["surface"],
                                     fg=COLORS["ink_soft"], font=("Microsoft YaHei UI", 9, "bold"))
        self.manage_count.pack(side="left")
        self.exit_btn = PillButton(inner, "完成", self.exit_manage, kind="ghost",
                                   width=48, height=30)
        self.exit_btn.pack(side="right", padx=(6, 0))
        self.delete_btn = PillButton(inner, "删除所选", self.delete_selected,
                                     kind="danger", width=80, height=30, disabled=True)
        self.delete_btn.pack(side="right", padx=(6, 0))
        self.select_all_btn = PillButton(inner, "全选", self.toggle_select_all,
                                         kind="ghost", width=52, height=30)
        self.select_all_btn.pack(side="right")
        self.manage_bar.place_forget()

    def on_show(self):
        self.refresh()

    def show_subset(self, task_ids, note=""):
        self.subset_ids = set(task_ids or [])
        self.subset_note = note
        self.filter = "all"
        self.date_filter = None
        self.manage = False
        self.selected.clear()
        self.refresh()
        self.scroll.canvas.yview_moveto(0)

    def clear_subset(self):
        self.subset_ids = None
        self.subset_note = ""
        self.refresh()

    def set_filter(self, key):
        self.filter = key
        if self.manage:
            self.selected.clear()
        self.refresh()

    def _on_search_changed(self, *_args):
        if self._search_after is not None:
            try:
                self.after_cancel(self._search_after)
            except tk.TclError:
                pass
        self._search_after = self.after(180, self._apply_search)

    def _apply_search(self):
        self._search_after = None
        query = self.search_var.get().strip().lower()
        if query == self.search_query:
            return
        self.search_query = query
        self.refresh()

    def clear_search(self):
        self.search_var.set("")
        self._apply_search()
        self.search_entry.focus_set()

    def _search_filtered(self, tasks):
        query = self.search_query
        if not query:
            return list(tasks)
        result = []
        for task in tasks:
            tags = " ".join(model.TAG_META.get(tag, ("",))[0] for tag in (task.get("tags") or []))
            subtasks = " ".join((sub.get("title") or "") for sub in (task.get("subtasks") or []))
            text = " ".join([
                str(task.get("title") or ""),
                str(task.get("requirement") or ""),
                str(task.get("owner") or ""),
                str(task.get("owner_username") or ""),
                tags,
                subtasks,
            ]).lower()
            if query in text:
                result.append(task)
        return result

    def _date_filtered(self, tasks):
        if not self.date_filter:
            return list(tasks)
        start = model.parse_dt(self.date_filter.get("start"))
        end = model.parse_dt(self.date_filter.get("end"))
        if not start or not end:
            return list(tasks)
        result = []
        for task in tasks:
            task_start = model.parse_dt(task.get("start"))
            task_due = model.parse_dt(task.get("due"))
            if not task_start and not task_due:
                continue
            task_start = task_start or task_due
            task_due = task_due or task_start
            if task_start <= end and task_due >= start:
                result.append(task)
        return result

    def open_date_filter(self):
        DateFilterDialog(self.app, self.date_filter, self.apply_date_filter)

    def apply_date_filter(self, value):
        self.date_filter = value
        if self.manage:
            self.selected.clear()
        self.refresh()

    def clear_date_filter(self):
        self.date_filter = None
        if self.manage:
            self.selected.clear()
        self.refresh()

    def enter_manage(self):
        if not self.app.store.tasks:
            self.app.toast("还没有任务可以管理", "info")
            return
        self.manage = True
        self.selected.clear()
        self.refresh()

    def exit_manage(self):
        self.manage = False
        self.selected.clear()
        self.refresh()

    def toggle_select(self, task_id):
        if task_id in self.selected:
            self.selected.discard(task_id)
        else:
            self.selected.add(task_id)
        card = self.cards.get(task_id)
        if card is not None:
            card.set_selected(task_id in self.selected)
        self._update_manage_bar()

    def _visible_task_ids(self):
        tasks = self._date_filtered(self.app.store.tasks)
        tasks = self._search_filtered(tasks)
        return [t.get("id") for t in model.filter_tasks(tasks, self.filter)]

    def toggle_select_all(self):
        visible = self._visible_task_ids()
        if visible and all(task_id in self.selected for task_id in visible):
            for task_id in visible:
                self.selected.discard(task_id)
        else:
            self.selected.update(visible)
        for task_id, card in self.cards.items():
            card.set_selected(task_id in self.selected)
        self._update_manage_bar()

    def _update_manage_bar(self):
        count = len(self.selected)
        self.manage_count.configure(text="已选 %d 项" % count)
        visible = self._visible_task_ids()
        all_selected = bool(visible) and all(task_id in self.selected for task_id in visible)
        self.select_all_btn.set_text("取消" if all_selected else "全选")
        self.delete_btn.set_disabled(count == 0)

    def delete_selected(self):
        ids = list(self.selected)
        if not ids:
            self.app.toast("先选择要删除的任务", "warn")
            return

        def remove():
            self.app.delete_tasks(ids)

        self.app.confirm(
            "删除所选任务？",
            "将删除 %d 个任务及其子任务，关联的邮件不会被删除。此操作无法撤销。" % len(ids),
            "删除",
            remove,
            danger=True,
        )

    def clear_all(self):
        tasks = self.app.store.active_tasks()
        if not tasks:
            self.app.toast("任务清单已经是空的", "info")
            return

        def remove():
            self.app.delete_tasks([t.get("id") for t in tasks])

        self.app.confirm(
            "清空全部任务？",
            "共 %d 个任务，任务下的子任务和跟进记录会全部删除；邮件保留。此操作无法撤销。"
            % len(tasks),
            "全部删除",
            remove,
            danger=True,
        )

    def refresh(self):
        yview = self.scroll.canvas.yview()
        all_tasks = self.app.store.active_tasks()
        if self.subset_ids is not None:
            tasks = [task for task in all_tasks if task.get("id") in self.subset_ids]
            if not tasks:
                self.subset_ids = None
        else:
            tasks = all_tasks
        tasks = self._search_filtered(tasks)
        valid_ids = {t.get("id") for t in tasks}
        self.selected &= valid_ids
        if not tasks:
            self.manage = False
        for child in list(self.body.winfo_children()):
            child.destroy()
        self.cards = {}
        if self.subset_ids is not None:
            banner = tk.Frame(self.body, bg=COLORS["accent_pale"], padx=12, pady=9,
                              highlightthickness=1, highlightbackground="#EED6C8")
            banner.pack(fill="x", pady=(0, 12))
            tk.Label(banner, text=self.subset_note or "筛选结果",
                     bg=COLORS["accent_pale"], fg=COLORS["ink"],
                     font=("Microsoft YaHei UI", 9, "bold"), anchor="w",
                     justify="left", wraplength=260).pack(side="left", fill="x", expand=True)
            PillButton(banner, "全部任务", self.clear_subset, kind="ghost",
                       width=66, height=26).pack(side="right", padx=(6, 0))
        data = model.counts(tasks)
        hero = HeroCard(self.body, data)
        hero.pack(fill="x", pady=(0, 18))

        head = tk.Frame(self.body, bg=COLORS["bg"])
        head.pack(fill="x", pady=(0, 8))
        tk.Label(head, text="任务清单", bg=COLORS["bg"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 13, "bold")).pack(side="left")
        if not self.manage:
            if tasks:
                PillButton(head, "清空", self.clear_all, kind="danger",
                           width=44, height=24).pack(side="right", padx=(4, 0), pady=(1, 0))
                PillButton(head, "管理", self.enter_manage, kind="ghost",
                           width=44, height=24).pack(side="right", padx=(4, 0), pady=(1, 0))
                PillButton(head, "状态更新", self.app.update_task_status, kind="ghost",
                           width=72, height=24).pack(side="right", padx=(4, 0), pady=(1, 0))
            tk.Label(head, text="%d 项 · 向左拖动删除" % len(tasks), bg=COLORS["bg"],
                     fg=COLORS["faint"], font=("Microsoft YaHei UI", 8)).pack(
                side="right", padx=(0, 7), pady=(4, 0))

        chips = ChipStrip(self.body, bg=COLORS["bg"])
        chips.pack(fill="x", pady=(0, 8))
        date_tasks = self._date_filtered(tasks)
        for key, label in FILTERS:
            count = len(model.filter_tasks(date_tasks, key))
            chip = Chip(chips.inner, label, command=lambda k=key: self.set_filter(k),
                        selected=self.filter == key, count=count, height=27,
                        font=("Microsoft YaHei UI", 8))
            chip.pack(side="left", padx=(0, 5))
            chips.bind_wheel(chip)

        date_row = tk.Frame(self.body, bg=COLORS["bg"])
        date_row.pack(fill="x", pady=(0, 12))
        PillButton(date_row, "日期范围", self.open_date_filter, kind="soft",
                   width=82, height=27).pack(side="left")
        if self.date_filter:
            tk.Label(date_row, text=self.date_filter.get("label", "已筛选"),
                     bg=COLORS["accent_pale"], fg=COLORS["accent"],
                     font=("Microsoft YaHei UI", 8, "bold"),
                     padx=7, pady=3).pack(side="left", padx=(6, 0))
            SmallIconButton(date_row, "×", self.clear_date_filter,
                            bg=COLORS["bg"], size=24, fg=COLORS["faint"]).pack(
                side="left", padx=(2, 0))
        else:
            tk.Label(date_row, text="按年 / 月 / 日跨度筛选", bg=COLORS["bg"],
                     fg=COLORS["faint"], font=("Microsoft YaHei UI", 8)).pack(
                side="left", padx=(7, 0))

        filtered = model.sort_tasks(model.filter_tasks(date_tasks, self.filter))
        if filtered:
            for task in filtered:
                card = TaskCard(self.body, self.app, task, manage=self.manage,
                                selected=task.get("id") in self.selected,
                                on_select=self.toggle_select)
                card.pack(fill="x", pady=(0, 9))
                self.cards[task.get("id")] = card
        elif self.search_query:
            EmptyState(self.body, "没有搜到任务",
                       "试试任务标题、要求、负责人或标签。",
                       "清除搜索", self.clear_search).pack(fill="x")
        elif not tasks:
            EmptyState(self.body, "还没有任务", "把邮件里的待办，变成一条可跟踪的清单。").pack(fill="x")
        elif self.date_filter:
            EmptyState(self.body, "日期范围内没有任务",
                       "换一个年 / 月 / 日跨度，或清除日期筛选。",
                       "清除日期筛选", self.clear_date_filter).pack(fill="x")
        else:
            EmptyState(self.body, "这个分组是空的", "换一个筛选条件，或者开始一件新任务。",
                       "查看全部任务", lambda: self.set_filter("all")).pack(fill="x")

        tk.Frame(self.body, bg=COLORS["bg"], height=116 if self.manage else 76).pack(fill="x")
        if self.manage:
            self.add_btn.place_forget()
            self.manage_bar.place(relx=0.5, rely=1.0, y=-12, anchor="s", width=384)
            tk.Misc.lift(self.manage_bar)
            self._update_manage_bar()
        else:
            self.manage_bar.place_forget()
            self.add_btn.place(relx=1.0, rely=1.0, x=-20, y=-18, anchor="se")
            tk.Misc.lift(self.add_btn)
        self.body.update_idletasks()
        self.scroll.refresh()
        target = yview[0] if yview else 0
        self.after_idle(lambda: self.scroll.canvas.yview_moveto(target))



class TaskEditor(Modal):
    def __init__(self, app, task=None, prefill=None, on_saved=None, on_close=None):
        self.app = app
        self.is_new = task is None
        self.on_saved = on_saved
        self.on_close = on_close
        if task is not None:
            self.task = copy.deepcopy(task)
        else:
            prefill = prefill or {}
            due_dt = (model.now() + timedelta(days=7)).replace(hour=18, minute=0)
            due = prefill.get("due") or model.iso(due_dt)
            start = prefill.get("start") or model.iso(model.now())
            self.task = model.create_task(
                title=prefill.get("title") or "",
                requirement=prefill.get("requirement") or "",
                cycle=prefill.get("cycle") or "一次性",
                start=start,
                due=due,
                owner=prefill.get("owner") or "",
                owner_username=prefill.get("owner_username") or "",
                progress=prefill.get("progress") or 0,
            )
            self.task["source_email_id"] = prefill.get("source_email_id")
        self.source_email_id = self.task.get("source_email_id")
        self._initial_title = (self.task.get("title") or "") if not self.is_new else (
            (prefill or {}).get("title") or ""
        )
        super(TaskEditor, self).__init__(
            app,
            "新建任务" if self.is_new else "编辑任务",
            "子任务全部完成，任务才能完成",
        )
        self._build()
        self._track_dirty()
        self.set_dirty(False)

    # ------------------------------------------------------------------ build
    def _build(self):
        body = self.content
        self.title_var = tk.StringVar(value=self._initial_title)
        self.req_text = styled_text(body, self.task.get("requirement") or "", height=8)
        self.cycle_var = tk.StringVar(value=self.task.get("cycle") or "一次性")
        self.start_var = tk.StringVar(value=self._fmt(self.task.get("start")))
        self.due_var = tk.StringVar(value=self._fmt(self.task.get("due")))
        self.progress_var = tk.IntVar(value=int(self.task.get("progress") or 0))

        # Source email banner.
        if self.source_email_id:
            source = self.app.store.email(self.source_email_id)
            if source:
                banner = tk.Frame(body, bg=COLORS["accent_pale"], padx=10, pady=7)
                banner.pack(fill="x", pady=(0, 12))
                tk.Label(banner, text="来自邮件", bg=COLORS["accent_pale"],
                         fg=COLORS["accent"], font=("Microsoft YaHei UI", 8, "bold")).pack(side="left")
                tk.Label(banner, text=truncate(source.get("subject", ""), 28),
                         bg=COLORS["accent_pale"], fg=COLORS["ink_soft"],
                         font=("Microsoft YaHei UI", 8)).pack(side="left", padx=(7, 0))
                tk.Label(banner, text="只读来源", bg=COLORS["accent_pale"],
                         fg=COLORS["faint"], font=("Microsoft YaHei UI", 7)).pack(
                    side="right")

        field_label(body, "任务名称").pack(fill="x", pady=(0, 5))
        title_entry = styled_entry(body, self.title_var, font=("Microsoft YaHei UI", 12, "bold"))
        title_entry.pack(fill="x", ipady=7)
        gap(body, 13)

        field_label(body, "要求 / 交付标准").pack(fill="x", pady=(0, 5))
        self.req_text.pack(fill="x")
        gap(body, 13)

        field_label(body, "周期").pack(fill="x", pady=(0, 6))
        cycle_row = tk.Frame(body, bg=COLORS["bg"])
        cycle_row.pack(fill="x")
        self.cycle_chips = {}
        for cycle in CYCLES:
            chip = Chip(cycle_row, cycle, command=lambda c=cycle: self._select_cycle(c),
                        selected=self.cycle_var.get() == cycle, height=28,
                        font=("Microsoft YaHei UI", 8))
            chip.pack(side="left", padx=(0, 5))
            self.cycle_chips[cycle] = chip
        gap(body, 13)

        field_label(body, "时间安排", "开始与结束时间").pack(fill="x", pady=(0, 5))
        time_grid = tk.Frame(body, bg=COLORS["bg"])
        time_grid.pack(fill="x")
        time_grid.grid_columnconfigure(0, weight=1)
        time_grid.grid_columnconfigure(1, weight=1)
        start_box = tk.Frame(time_grid, bg=COLORS["bg"])
        start_box.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        due_box = tk.Frame(time_grid, bg=COLORS["bg"])
        due_box.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        tk.Label(start_box, text="开始", bg=COLORS["bg"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(0, 3))
        self.start_field = DateTimeField(start_box, self.app, self.start_var,
                                         "选择开始时间", bg=COLORS["bg"])
        self.start_field.pack(fill="x")
        tk.Label(due_box, text="结束 / 截止", bg=COLORS["bg"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(0, 3))
        self.due_field = DateTimeField(due_box, self.app, self.due_var,
                                       "选择结束时间", bg=COLORS["bg"])
        self.due_field.pack(fill="x")

        quick = tk.Frame(body, bg=COLORS["bg"])
        quick.pack(fill="x", pady=(7, 0))
        tk.Label(quick, text="截止快捷设置", bg=COLORS["bg"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8)).pack(side="left", padx=(0, 6))
        for label, days in (("今天 18:00", 0), ("明天 18:00", 1), ("+7 天", 7)):
            chip = Chip(quick, label, command=lambda d=days: self._quick_due(d),
                        height=24, font=("Microsoft YaHei UI", 8))
            chip.pack(side="left", padx=(0, 5))
        self.time_error = tk.Label(body, text="", bg=COLORS["bg"], fg=COLORS["danger"],
                                   font=("Microsoft YaHei UI", 8), anchor="w")
        self.time_error.pack(fill="x", pady=(4, 0))
        gap(body, 11)

        field_label(body, "跟踪负责人", "从账户中选择").pack(fill="x", pady=(0, 5))
        self.owner_field = OwnerField(
            body, self.app,
            self.task.get("owner") or "",
            self.task.get("owner_username") or "",
        )
        self.owner_field.pack(fill="x")

        gap(body, 15)
        tk.Label(body, text="任务标签", bg=COLORS["bg"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x", pady=(0, 5))
        tag_row = tk.Frame(body, bg=COLORS["bg"])
        tag_row.pack(fill="x")
        self.tag_chips = {}
        current_tags = model.clean_tags(self.task.get("tags"))
        for key in model.TAG_KEYS:
            label = model.TAG_META[key][0]
            chip = Chip(tag_row, label, command=lambda k=key: self._toggle_tag(k),
                        selected=key in current_tags, height=26,
                        font=("Microsoft YaHei UI", 8))
            chip.pack(side="left", padx=(0, 5))
            self.tag_chips[key] = chip

        gap(body, 15)
        progress_head = tk.Frame(body, bg=COLORS["bg"])
        progress_head.pack(fill="x")
        tk.Label(progress_head, text="当前进度", bg=COLORS["bg"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")
        self.progress_pct = tk.Label(progress_head, text="%d%%" % self.progress_var.get(),
                                     bg=COLORS["bg"], fg=COLORS["accent"],
                                     font=("Microsoft YaHei UI", 12, "bold"))
        self.progress_pct.pack(side="right")
        self.progress_slider = ProgressSlider(
            body, value=self.progress_var.get(), command=self._on_progress,
            bg=COLORS["bg"], width=344,
            limit=100 if model.all_subtasks_done(self.task) else 99,
        )
        self.progress_slider.pack(fill="x", pady=(5, 0))
        self.progress_hint = tk.Label(body, text="", bg=COLORS["bg"], fg=COLORS["faint"],
                                      font=("Microsoft YaHei UI", 8), anchor="w")
        self.progress_hint.pack(fill="x", pady=(2, 0))
        self._update_progress_hint()

        gap(body, 15)
        sub_head = tk.Frame(body, bg=COLORS["bg"])
        sub_head.pack(fill="x")
        tk.Label(sub_head, text="子任务", bg=COLORS["bg"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")
        self.sub_count = tk.Label(sub_head, text="", bg=COLORS["bg"], fg=COLORS["faint"],
                                  font=("Microsoft YaHei UI", 8))
        self.sub_count.pack(side="right")
        tk.Label(body, text="所有子任务完成后，任务才能完成", bg=COLORS["bg"],
                 fg=COLORS["faint"], font=("Microsoft YaHei UI", 8), anchor="w").pack(
            fill="x", pady=(2, 7))
        self.sub_box = tk.Frame(body, bg=COLORS["surface"], highlightthickness=1,
                                highlightbackground=COLORS["line"])
        self.sub_box.pack(fill="x")
        self._render_subtasks()

        add_row = tk.Frame(body, bg=COLORS["bg"])
        add_row.pack(fill="x", pady=(8, 0))
        PillButton(add_row, "＋ 添加子任务", self._add_subtask, kind="soft",
                   width=124, height=34).pack(side="left")

        notes = self.task.get("notes") or []
        if notes:
            gap(body, 16)
            tk.Label(body, text="跟进记录", bg=COLORS["bg"], fg=COLORS["ink_soft"],
                     font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x")
            note_card = tk.Frame(body, bg=COLORS["surface"], padx=11, pady=8,
                                 highlightthickness=1, highlightbackground=COLORS["line"])
            note_card.pack(fill="x", pady=(6, 0))
            for note in notes[-4:]:
                row = tk.Frame(note_card, bg=COLORS["surface"])
                row.pack(fill="x", pady=2)
                tk.Label(row, text=truncate(note.get("text", ""), 56), bg=COLORS["surface"],
                         fg=COLORS["muted"], font=("Microsoft YaHei UI", 8),
                         anchor="w", justify="left", wraplength=275).pack(side="left")
                date = model.parse_dt(note.get("at"))
                tk.Label(row, text=date.strftime("%m/%d") if date else "", bg=COLORS["surface"],
                         fg=COLORS["faint"], font=("Microsoft YaHei UI", 7)).pack(side="right")

        tk.Frame(body, bg=COLORS["bg"], height=24).pack(fill="x")

        # Footer buttons.
        if not self.is_new:
            delete = PillButton(self.footer_left, "删除", self._delete,
                                kind="ghost", width=54, height=34)
            delete.configure()
            delete.pack(side="left", pady=17)
            if self.app.collab_user:
                PillButton(self.footer_left, "转发", self._forward, kind="ghost",
                           width=54, height=34).pack(side="left", padx=(6, 0), pady=17)
        PillButton(self.footer_right, "取消", self.request_close, kind="ghost",
                   width=62, height=36).pack(side="left", padx=(0, 8), pady=16)
        PillButton(self.footer_right, "保存任务", self._save, kind="primary",
                   width=92, height=36).pack(side="left", pady=16)

    @staticmethod
    def _fmt(value):
        dt = model.parse_dt(value)
        return dt.strftime("%Y-%m-%d %H:%M") if dt else ""

    def _track_dirty(self):
        for var in (self.title_var, self.cycle_var, self.start_var, self.due_var,
                    self.owner_field.var):
            var.trace_add("write", lambda *_: self.set_dirty(True))
        self.req_text.bind("<<Modified>>", self._text_modified)
        self.req_text.edit_modified(False)

    def _text_modified(self, _event=None):
        if self.req_text.edit_modified():
            self.set_dirty(True)
            self.req_text.edit_modified(False)

    # --------------------------------------------------------------- controls
    def _select_cycle(self, cycle):
        self.cycle_var.set(cycle)
        for key, chip in self.cycle_chips.items():
            chip.set_selected(key == cycle)
        self.set_dirty(True)

    def _quick_due(self, days):
        dt = (model.now() + timedelta(days=days)).replace(hour=18, minute=0)
        if days == 0 and dt <= model.now():
            dt = model.now() + timedelta(hours=2)
        self.due_var.set(dt.strftime("%Y-%m-%d %H:%M"))
        self.set_dirty(True)

    def _on_progress(self, value, released=False):
        value = min(int(value), self.progress_slider.limit)
        self.progress_var.set(value)
        self.progress_pct.configure(text="%d%%" % value)
        self.progress_slider.set(value)
        self._update_progress_hint()
        self.set_dirty(True)

    def _update_progress_hint(self):
        done, total = model.subtask_stats(self.task)
        if total == 0:
            text = "没有子任务，可直接设为 100% 完成任务"
        elif done == total:
            text = "全部子任务已完成，可设为 100%"
        else:
            text = "已完成 %d/%d 个子任务；未全部完成时最高 99%%" % (done, total)
        self.progress_hint.configure(text=text)

    def _render_subtasks(self):
        for child in list(self.sub_box.winfo_children()):
            child.destroy()
        subs = self.task.get("subtasks") or []
        if not subs:
            tk.Label(self.sub_box, text="暂无子任务，可在下方添加。", bg=COLORS["surface"],
                     fg=COLORS["faint"], font=("Microsoft YaHei UI", 8),
                     anchor="w", padx=12, pady=12).pack(fill="x")
        for index, sub in enumerate(subs):
            row = tk.Frame(self.sub_box, bg=COLORS["surface"])
            row.pack(fill="x")
            if index > 0:
                tk.Frame(row, bg=COLORS["line_soft"], height=1).pack(fill="x", side="top")
            line = tk.Frame(row, bg=COLORS["surface"], padx=9, pady=7)
            line.pack(fill="x")
            check = CheckCircle(line, checked=bool(sub.get("done")),
                                command=lambda sid=sub["id"]: self._toggle_sub(sid),
                                size=20, bg=COLORS["surface"],
                                color=COLORS["mint"])
            check.pack(side="left", pady=(1, 0))
            content = tk.Frame(line, bg=COLORS["surface"])
            content.pack(side="left", fill="x", expand=True, padx=(7, 3))
            font = tkfont.Font(family="Microsoft YaHei UI", size=9,
                               overstrike=bool(sub.get("done")))
            label = tk.Label(content, text=sub.get("title", ""), bg=COLORS["surface"],
                             fg=COLORS["faint"] if sub.get("done") else COLORS["ink_soft"],
                             font=font, anchor="w", justify="left", wraplength=230)
            label.pack(fill="x", anchor="w")
            meta = []
            if sub.get("owner"):
                handle = (" @" + sub.get("owner_username")) if sub.get("owner_username") else ""
                meta.append("负责人 " + sub["owner"] + handle)
            if sub.get("due"):
                due_dt = model.parse_dt(sub.get("due"))
                if due_dt:
                    meta.append("截止 " + due_dt.strftime("%m/%d %H:%M"))
            meta_label = tk.Label(
                content,
                text=" · ".join(meta) if meta else "点击设置负责人与时间",
                bg=COLORS["surface"], fg=COLORS["faint"],
                font=("Microsoft YaHei UI", 7), anchor="w")
            meta_label.pack(fill="x", pady=(2, 0))
            edit = tk.Label(line, text="编辑", bg=COLORS["surface"], fg=COLORS["accent"],
                            font=("Microsoft YaHei UI", 8), cursor="hand2")
            edit.pack(side="right", padx=(2, 3))
            edit.bind("<Button-1>", lambda _e, sid=sub["id"]: self._edit_subtask(sid))
            remove = SmallIconButton(line, "×", lambda sid=sub["id"]: self._remove_sub(sid),
                                     bg=COLORS["surface"], size=24, fg=COLORS["faint"])
            remove.pack(side="right")
            for widget in (content, label, meta_label):
                widget.bind("<Button-1>", lambda _e, sid=sub["id"]: self._edit_subtask(sid))
        done, total = model.subtask_stats(self.task)
        self.sub_count.configure(text="%d / %d 已完成" % (done, total) if total else "0 项")

    def _toggle_sub(self, subtask_id):
        model.toggle_subtask(self.task, subtask_id)
        self._after_subtask_change()

    def _add_subtask(self):
        SubtaskDialog(self.app, None, self._save_subtask)

    def _edit_subtask(self, subtask_id):
        sub = next((s for s in self.task.get("subtasks", []) if s.get("id") == subtask_id), None)
        if sub:
            SubtaskDialog(self.app, sub, self._save_subtask)

    def _save_subtask(self, data, existing_id=None):
        if existing_id:
            for sub in self.task.get("subtasks", []):
                if sub.get("id") == existing_id:
                    sub.update(data)
                    break
        else:
            sub = model.add_subtask(
                self.task, data.get("title"), data.get("start"), data.get("due"),
                data.get("owner"), data.get("owner_username"),
                requirement=data.get("requirement") or "")
            if sub:
                sub["done"] = bool(data.get("done"))
                if sub["done"]:
                    sub["done_at"] = model.iso(model.now())
        self._after_subtask_change()

    def _remove_sub(self, subtask_id):
        model.remove_subtask(self.task, subtask_id)
        self._after_subtask_change()

    def _after_subtask_change(self):
        if self.task.get("completed") and not model.all_subtasks_done(self.task):
            self.task["completed"] = False
        limit = 100 if model.all_subtasks_done(self.task) else 99
        self.progress_slider.set_limit(limit)
        value = min(int(self.progress_var.get()), limit)
        self.progress_var.set(value)
        self.progress_slider.set(value)
        self.progress_pct.configure(text="%d%%" % value)
        self._render_subtasks()
        self._update_progress_hint()
        self.set_dirty(True)

    # ------------------------------------------------------------------- save
    def _toggle_tag(self, key):
        chip = self.tag_chips.get(key)
        if chip is None:
            return
        chip.set_selected(not chip.selected)
        self.set_dirty(True)

    def _validate_and_commit(self):
        title = self.title_var.get().strip()
        if not title:
            self.app.toast("请填写任务名称", "warn")
            return False
        start = model.parse_dt(self.start_var.get())
        due = model.parse_dt(self.due_var.get())
        if not start or not due:
            self.time_error.configure(text="时间格式不对，请用 2026-11-05 18:00")
            return False
        if due < start:
            self.time_error.configure(text="结束时间不能早于开始时间")
            return False
        self.time_error.configure(text="")
        self.task["title"] = title
        self.task["requirement"] = self.req_text.get("1.0", "end").strip()
        self.task["cycle"] = self.cycle_var.get() or "一次性"
        self.task["start"] = model.iso(start)
        self.task["due"] = model.iso(due)
        owner_name, owner_username = self.owner_field.get()
        self.task["owner"] = owner_name.strip()
        self.task["owner_username"] = owner_username.strip()
        self.task["tags"] = [key for key, chip in self.tag_chips.items() if chip.selected]
        value = int(self.progress_var.get())
        if value >= 100 and not model.all_subtasks_done(self.task):
            value = 99
            self.app.toast("还有子任务未完成，进度已保存为 99%", "warn")
        model.set_progress(self.task, value)
        self.task["updated_at"] = model.iso(model.now())
        return True

    def _save(self):
        if not self._validate_and_commit():
            return
        if (not self.is_new and self.task.get("share_group_id")
                and self.app.collab_user and not self.app.push_shared_task(self.task)):
            return
        store = self.app.store
        if self.is_new:
            store.add_task(self.task)
        else:
            for i, existing in enumerate(store.tasks):
                if existing.get("id") == self.task.get("id"):
                    store.tasks[i] = self.task
                    break
            else:
                store.tasks.append(self.task)
            store.save()
        if self.source_email_id:
            store.link_email(self.source_email_id, self.task["id"],
                             note="由邮件创建：%s" % self._source_subject())
        self.set_dirty(False)
        self.force_close()
        self.app.refresh()
        self.app.schedule_collab_sync()
        if self.on_saved:
            self.on_saved(self.task)
        self.app.toast("任务已创建" if self.is_new else "任务已保存", "success")

    def _forward(self):
        if self.dirty:
            self.app.toast("请先保存任务再转发", "warn")
            return
        task = self.app.store.task(self.task.get("id"))
        if task:
            self.app.open_forward_dialog(task=task)

    def _source_subject(self):
        email = self.app.store.email(self.source_email_id)
        return truncate(email.get("subject", "邮件"), 30) if email else "邮件"

    def _delete(self):
        if self.is_new:
            return

        def remove():
            self.app.store.delete_task(self.task.get("id"))
            self.set_dirty(False)
            self.force_close()
            self.app.refresh()
            self.app.schedule_collab_sync()
            self.app.toast("任务已删除", "info")

        self.app.confirm("删除这个任务？", "任务及其子任务将一并删除，无法撤销。",
                         "删除", remove, danger=True)

    def force_close(self):
        callback = getattr(self, "on_close", None)
        super(TaskEditor, self).force_close()
        if callback:
            callback()


class SubtaskDialog(tk.Toplevel):
    """Small modal for a subtask's title, schedule and owner."""

    def __init__(self, app, subtask, callback):
        tk.Toplevel.__init__(self, app)
        self.app = app
        self.subtask = subtask or {}
        self.callback = callback
        self.overrideredirect(True)
        self.configure(bg=COLORS["line"])
        self.attributes("-topmost", True)
        self.transient(app)
        self._build()
        self._place()
        self.deiconify()
        self.lift()
        self.after(20, self._raise)
        self.bind("<Escape>", lambda _e: self.close())

    def _raise(self):
        try:
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
        except Exception:
            pass

    def _place(self):
        self.update_idletasks()
        width, height = 372, 500
        x = self.app.winfo_x() + max(8, (self.app.W - width) // 2)
        y = self.app.winfo_y() + max(20, (self.app.H - height) // 2 - 20)
        self.geometry("%dx%d+%d+%d" % (width, height, x, y))

    def _build(self):
        shell = tk.Frame(self, bg=COLORS["surface"])
        shell.pack(fill="both", expand=True, padx=1, pady=1)
        header = tk.Frame(shell, bg=COLORS["surface"], height=50)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="编辑子任务" if self.subtask else "新建子任务",
                 bg=COLORS["surface"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 11, "bold")).pack(side="left", padx=14)
        SmallIconButton(header, "×", self.close, bg=COLORS["surface"],
                        size=30).pack(side="right", padx=(0, 8), pady=10)
        tk.Frame(shell, bg=COLORS["line_soft"], height=1).pack(fill="x")

        body = tk.Frame(shell, bg=COLORS["surface"], padx=16, pady=12)
        body.pack(fill="both", expand=True)
        field_label(body, "子任务标题", bg=COLORS["surface"]).pack(fill="x", pady=(0, 5))
        self.title_var = tk.StringVar(value=self.subtask.get("title", ""))
        styled_entry(body, self.title_var, font=("Microsoft YaHei UI", 10)).pack(
            fill="x", ipady=6)
        gap(body, 9)

        field_label(body, "子任务内容", "填写具体要求或差异点", bg=COLORS["surface"]).pack(
            fill="x", pady=(0, 5))
        self.content_text = styled_text(body, self.subtask.get("requirement", ""), height=3)
        self.content_text.pack(fill="x")
        gap(body, 10)

        field_label(body, "时间安排", "点击选择", bg=COLORS["surface"]).pack(
            fill="x", pady=(0, 5))
        grid = tk.Frame(body, bg=COLORS["surface"])
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        left = tk.Frame(grid, bg=COLORS["surface"])
        left.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        right = tk.Frame(grid, bg=COLORS["surface"])
        right.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        tk.Label(left, text="开始", bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(0, 3))
        self.start_var = tk.StringVar(value=self.subtask.get("start") or "")
        self.start_field = DateTimeField(left, self.app, self.start_var,
                                         "选择子任务开始时间")
        self.start_field.pack(fill="x")
        tk.Label(right, text="结束 / 截止", bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(0, 3))
        self.due_var = tk.StringVar(value=self.subtask.get("due") or "")
        self.due_field = DateTimeField(right, self.app, self.due_var,
                                       "选择子任务结束时间")
        self.due_field.pack(fill="x")
        gap(body, 11)

        field_label(body, "子任务负责人", "从账户中选择", bg=COLORS["surface"]).pack(
            fill="x", pady=(0, 5))
        self.owner_field = OwnerField(
            body, self.app,
            self.subtask.get("owner") or "",
            self.subtask.get("owner_username") or "",
        )
        self.owner_field.pack(fill="x")
        gap(body, 10)

        done_row = tk.Frame(body, bg=COLORS["surface"])
        done_row.pack(fill="x")
        self.done_var = tk.BooleanVar(value=bool(self.subtask.get("done")))
        check = CheckCircle(done_row, checked=self.done_var.get(),
                            command=self._toggle_done, size=20,
                            bg=COLORS["surface"], color=COLORS["mint"])
        check.pack(side="left")
        tk.Label(done_row, text="已完成这个子任务", bg=COLORS["surface"],
                 fg=COLORS["ink_soft"], font=("Microsoft YaHei UI", 9)).pack(
            side="left", padx=(7, 0))
        self.done_check = check
        self.error = tk.Label(body, text="", bg=COLORS["surface"], fg=COLORS["danger"],
                              font=("Microsoft YaHei UI", 8), anchor="w",
                              justify="left", wraplength=330)
        self.error.pack(fill="x", pady=(8, 0))

        footer = tk.Frame(shell, bg=COLORS["surface"], height=58)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        tk.Frame(shell, bg=COLORS["line_soft"], height=1).pack(side="bottom", fill="x")
        PillButton(footer, "取消", self.close, kind="ghost", width=62,
                   height=34).pack(side="right", padx=(6, 14), pady=12)
        PillButton(footer, "保存子任务", self._save, kind="primary", width=92,
                   height=34).pack(side="right", pady=12)

    def _toggle_done(self):
        self.done_var.set(not self.done_var.get())
        self.done_check.set(self.done_var.get())

    def _save(self):
        title = self.title_var.get().strip()
        if not title:
            self.error.configure(text="请填写子任务标题")
            return
        start = model.parse_dt(self.start_var.get())
        due = model.parse_dt(self.due_var.get())
        if start and due and due < start:
            self.error.configure(text="子任务结束时间不能早于开始时间")
            return
        owner, owner_username = self.owner_field.get()
        data = {
            "title": title,
            "requirement": self.content_text.get("1.0", "end").strip(),
            "start": model.iso(start) if start else None,
            "due": model.iso(due) if due else None,
            "owner": owner.strip(),
            "owner_username": owner_username.strip(),
            "done": bool(self.done_var.get()),
        }
        callback = self.callback
        existing_id = self.subtask.get("id")
        self.close()
        callback(data, existing_id)

    def close(self):
        self.destroy()


class DateFilterDialog(tk.Toplevel):
    """Year / month / day span filter for the task list."""

    UNITS = (("year", "按年"), ("month", "按月"), ("day", "按日"))

    def __init__(self, app, current, callback):
        tk.Toplevel.__init__(self, app)
        self.app = app
        self.callback = callback
        self.current = current or {}
        self.unit = self.current.get("unit") or "month"
        self.unit_chips = {}
        self.form = None
        self.error = None
        self.overrideredirect(True)
        self.configure(bg=COLORS["line"])
        self.attributes("-topmost", True)
        self.transient(app)
        self._build()
        self._render_form()
        self.lift()
        self._place()
        self.after(20, self._raise)
        self.bind("<Escape>", lambda _e: self.close())

    def _raise(self):
        try:
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
        except Exception:
            pass

    def _build(self):
        shell = tk.Frame(self, bg=COLORS["surface"])
        shell.pack(fill="both", expand=True, padx=1, pady=1)
        header = tk.Frame(shell, bg=COLORS["surface"], height=50)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="筛选日期", bg=COLORS["surface"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 11, "bold")).pack(side="left", padx=14)
        SmallIconButton(header, "×", self.close, bg=COLORS["surface"],
                        size=30).pack(side="right", padx=(0, 8), pady=10)
        tk.Frame(shell, bg=COLORS["line_soft"], height=1).pack(fill="x")

        body = tk.Frame(shell, bg=COLORS["surface"], padx=16, pady=12)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="选择筛选跨度", bg=COLORS["surface"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x", pady=(0, 6))
        tabs = tk.Frame(body, bg=COLORS["surface"])
        tabs.pack(fill="x", pady=(0, 12))
        for key, label in self.UNITS:
            chip = Chip(tabs, label, command=lambda k=key: self._switch_unit(k),
                        selected=key == self.unit, height=28,
                        font=("Microsoft YaHei UI", 8))
            chip.pack(side="left", padx=(0, 5))
            self.unit_chips[key] = chip
        self.form = tk.Frame(body, bg=COLORS["surface"])
        self.form.pack(fill="x")
        self.error = tk.Label(body, text="", bg=COLORS["surface"], fg=COLORS["danger"],
                              font=("Microsoft YaHei UI", 8), anchor="w",
                              justify="left", wraplength=320)
        self.error.pack(fill="x", pady=(8, 0))

        footer = tk.Frame(shell, bg=COLORS["surface"], height=58)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        tk.Frame(shell, bg=COLORS["line_soft"], height=1).pack(side="bottom", fill="x")
        PillButton(footer, "取消", self.close, kind="ghost", width=58,
                   height=32).pack(side="right", padx=(6, 14), pady=12)
        PillButton(footer, "应用筛选", self._apply, kind="primary", width=82,
                   height=32).pack(side="right", pady=12)
        PillButton(footer, "清除", self._clear, kind="ghost", width=52,
                   height=32).pack(side="left", padx=14, pady=12)

    def _place(self):
        self.update_idletasks()
        self.app.update_idletasks()
        width, height = 360, 410
        ax = self.app.winfo_rootx() or self.app.winfo_x()
        ay = self.app.winfo_rooty() or self.app.winfo_y()
        if not ax and not ay:
            ax = max(0, (self.winfo_screenwidth() - width) // 2)
            ay = max(0, (self.winfo_screenheight() - height) // 2)
        x = ax + max(8, (self.app.W - width) // 2)
        y = ay + max(24, (self.app.H - height) // 2)
        self.geometry("%dx%d+%d+%d" % (width, height, x, y))

    def _default_dates(self):
        now = datetime.now()
        current = self.current or {}
        if current.get("unit") == self.unit:
            start = model.parse_dt(current.get("start"))
            end = model.parse_dt(current.get("end"))
            if start and end:
                return start, end
        if self.unit == "year":
            return (datetime(now.year, 1, 1),
                    datetime(now.year, 12, 31, 23, 59))
        if self.unit == "month":
            last = calendar.monthrange(now.year, now.month)[1]
            return (datetime(now.year, now.month, 1),
                    datetime(now.year, now.month, last, 23, 59))
        return (now.replace(hour=0, minute=0, second=0, microsecond=0),
                now.replace(hour=23, minute=59, second=0, microsecond=0))

    def _switch_unit(self, unit):
        if unit == self.unit:
            return
        self.unit = unit
        for key, chip in self.unit_chips.items():
            chip.set_selected(key == unit)
        self._render_form()

    def _render_form(self):
        for child in list(self.form.winfo_children()):
            child.destroy()
        self.error.configure(text="")
        start, end = self._default_dates()
        if self.unit == "year":
            self._render_year(start, end)
        elif self.unit == "month":
            self._render_month(start, end)
        else:
            self._render_day(start, end)

    def _combo(self, parent, variable, values, width=5):
        box = ttk.Combobox(parent, textvariable=variable, values=values,
                           state="readonly", width=width, font=("Consolas", 9))
        box.pack(side="left", padx=(5, 0))
        return box

    def _render_year(self, start, end):
        tk.Label(self.form, text="从", bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8)).pack(side="left")
        years = [str(y) for y in range(datetime.now().year - 10,
                                       datetime.now().year + 11)]
        self.y1 = tk.StringVar(value=str(start.year))
        self._combo(self.form, self.y1, years, 6)
        tk.Label(self.form, text="到", bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8)).pack(side="left", padx=(8, 0))
        self.y2 = tk.StringVar(value=str(end.year))
        self._combo(self.form, self.y2, years, 6)
        tk.Label(self.form, text="年", bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8)).pack(side="left", padx=(5, 0))

    def _render_month(self, start, end):
        years = [str(y) for y in range(datetime.now().year - 10,
                                       datetime.now().year + 11)]
        months = ["%02d 月" % m for m in range(1, 13)]
        row1 = tk.Frame(self.form, bg=COLORS["surface"])
        row1.pack(fill="x", pady=(0, 5))
        tk.Label(row1, text="从", bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8)).pack(side="left")
        self.my1 = tk.StringVar(value=str(start.year))
        self._combo(row1, self.my1, years, 6)
        self.mm1 = tk.StringVar(value="%02d 月" % start.month)
        self._combo(row1, self.mm1, months, 5)
        row2 = tk.Frame(self.form, bg=COLORS["surface"])
        row2.pack(fill="x")
        tk.Label(row2, text="到", bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8)).pack(side="left")
        self.my2 = tk.StringVar(value=str(end.year))
        self._combo(row2, self.my2, years, 6)
        self.mm2 = tk.StringVar(value="%02d 月" % end.month)
        self._combo(row2, self.mm2, months, 5)

    def _render_day(self, start, end):
        row = tk.Frame(self.form, bg=COLORS["surface"])
        row.pack(fill="x")
        left = tk.Frame(row, bg=COLORS["surface"])
        left.pack(side="left", fill="x", expand=True, padx=(0, 4))
        right = tk.Frame(row, bg=COLORS["surface"])
        right.pack(side="left", fill="x", expand=True, padx=(4, 0))
        tk.Label(left, text="从", bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(0, 3))
        self.d1 = tk.StringVar(value=start.strftime("%Y-%m-%d 00:00"))
        DateTimeField(left, self.app, self.d1, "选择开始日期").pack(fill="x")
        tk.Label(right, text="到", bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(0, 3))
        self.d2 = tk.StringVar(value=end.strftime("%Y-%m-%d 23:59"))
        DateTimeField(right, self.app, self.d2, "选择结束日期").pack(fill="x")

    def _apply(self):
        try:
            if self.unit == "year":
                y1, y2 = int(self.y1.get()), int(self.y2.get())
                start = datetime(y1, 1, 1)
                end = datetime(y2, 12, 31, 23, 59)
                label = ("%d 年" % y1) if y1 == y2 else ("%d–%d 年" % (y1, y2))
            elif self.unit == "month":
                y1, y2 = int(self.my1.get()), int(self.my2.get())
                m1 = int(self.mm1.get()[:2])
                m2 = int(self.mm2.get()[:2])
                start = datetime(y1, m1, 1)
                end = datetime(y2, m2, calendar.monthrange(y2, m2)[1], 23, 59)
                if (y1, m1) == (y2, m2):
                    label = "%d-%02d" % (y1, m1)
                else:
                    label = "%d-%02d ~ %d-%02d" % (y1, m1, y2, m2)
            else:
                start = model.parse_dt(self.d1.get())
                end = model.parse_dt(self.d2.get())
                if not start or not end:
                    raise ValueError("请选择完整的开始和结束日期")
                start = start.replace(hour=0, minute=0, second=0, microsecond=0)
                end = end.replace(hour=23, minute=59, second=0, microsecond=0)
                if start.date() == end.date():
                    label = start.strftime("%Y-%m-%d")
                else:
                    label = "%s ~ %s" % (start.strftime("%Y-%m-%d"),
                                         end.strftime("%Y-%m-%d"))
            if start > end:
                raise ValueError("开始日期不能晚于结束日期")
        except (ValueError, TypeError) as exc:
            self.error.configure(text=str(exc) or "请选择有效日期")
            return
        callback = self.callback
        value = {
            "unit": self.unit,
            "start": start.strftime("%Y-%m-%d %H:%M"),
            "end": end.strftime("%Y-%m-%d %H:%M"),
            "label": label,
        }
        self.close()
        callback(value)

    def _clear(self):
        callback = self.callback
        self.close()
        callback(None)

    def close(self):
        self.destroy()



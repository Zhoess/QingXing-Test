# -*- coding: utf-8 -*-
"""Click-only date/time picker used by the task and subtask editors."""

import calendar
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import ttk

from .constants import COLORS
from .model import parse_dt
from .widgets import Chip, PillButton, SmallIconButton


def open_datetime_picker(app, initial, title, callback, parent=None):
    DateTimePicker(app, initial, title, callback, parent=parent)


class DateTimeField(tk.Frame):
    def __init__(self, parent, app, variable, title="选择时间", bg=None):
        bg = bg or COLORS["surface"]
        tk.Frame.__init__(self, parent, bg=bg, bd=0, highlightthickness=1,
                          highlightbackground=COLORS["line"], cursor="hand2")
        self.app = app
        self.variable = variable
        self.title = title
        self.value_label = tk.Label(self, text="", bg=bg, fg=COLORS["ink_soft"],
                                    font=("Consolas", 9), anchor="w", cursor="hand2")
        self.value_label.pack(side="left", fill="x", expand=True, padx=(9, 2), pady=7)
        self.icon = tk.Label(self, text="▦", bg=bg, fg=COLORS["accent"],
                             font=("Segoe UI Symbol", 11), cursor="hand2")
        self.icon.pack(side="right", padx=(2, 8))
        for widget in (self, self.value_label, self.icon):
            widget.bind("<Button-1>", self._pick)
        self.variable.trace_add("write", lambda *_: self._refresh())
        self._refresh()

    def _refresh(self):
        dt = parse_dt(self.variable.get())
        text = dt.strftime("%Y-%m-%d  %H:%M") if dt else "点击选择时间"
        self.value_label.configure(text=text,
                                   fg=COLORS["ink_soft"] if dt else COLORS["faint"])

    def _pick(self, _event=None):
        open_datetime_picker(self.app, self.variable.get(), self.title,
                             self._set_value, parent=self.winfo_toplevel())

    def _set_value(self, value):
        self.variable.set(value)

    def set(self, value):
        self.variable.set(value)


class DateTimePicker(tk.Toplevel):
    def __init__(self, app, initial, title, callback, parent=None):
        tk.Toplevel.__init__(self, app)
        self.app = app
        self.parent = parent or app
        self.callback = callback
        self.title_text = title
        self.overrideredirect(True)
        self.configure(bg=COLORS["line"])
        self.attributes("-topmost", True)
        self.transient(self.parent)
        self.selected = parse_dt(initial) or (datetime.now().replace(
            minute=0, second=0, microsecond=0) + timedelta(hours=1))
        self.view_year = self.selected.year
        self.view_month = self.selected.month
        self.view_mode = "day"
        self.decade_start = (self.view_year // 12) * 12
        self._build()
        self._place()
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.bind("<Escape>", lambda _e: self.close())
        self.after(20, self._focus)

    def _focus(self):
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _place(self):
        self.update_idletasks()
        width, height = 338, 468
        base = self.parent
        x = base.winfo_rootx() + max(8, (base.winfo_width() - width) // 2)
        y = base.winfo_rooty() + max(24, (base.winfo_height() - height) // 2 - 30)
        self.geometry("%dx%d+%d+%d" % (width, height, x, y))

    def _build(self):
        self.shell = tk.Frame(self, bg=COLORS["surface"])
        self.shell.pack(fill="both", expand=True, padx=1, pady=1)
        header = tk.Frame(self.shell, bg=COLORS["surface"], height=48)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text=self.title_text, bg=COLORS["surface"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 11, "bold")).pack(side="left", padx=14)
        SmallIconButton(header, "×", self.close, bg=COLORS["surface"],
                        size=30).pack(side="right", padx=(0, 8), pady=9)
        tk.Frame(self.shell, bg=COLORS["line_soft"], height=1).pack(fill="x")

        body = tk.Frame(self.shell, bg=COLORS["surface"], padx=14, pady=10)
        body.pack(fill="both", expand=True)
        nav = tk.Frame(body, bg=COLORS["surface"])
        nav.pack(fill="x", pady=(0, 7))
        SmallIconButton(nav, "‹", lambda: self._shift_view(-1),
                        bg=COLORS["surface"], size=28).pack(side="left")
        self.month_label = tk.Label(nav, text="", bg=COLORS["surface"], fg=COLORS["ink"],
                                    font=("Microsoft YaHei UI", 10, "bold"),
                                    cursor="hand2")
        self.month_label.pack(side="left", expand=True)
        self.month_label.bind("<Button-1>", lambda _e: self._drill_down())
        SmallIconButton(nav, "›", lambda: self._shift_view(1),
                        bg=COLORS["surface"], size=28).pack(side="right")

        self.calendar_holder = tk.Frame(body, bg=COLORS["surface"])
        self.calendar_holder.pack(fill="x")
        self.calendar_area = tk.Frame(self.calendar_holder, bg=COLORS["surface"])
        self.calendar_area.pack(fill="x")
        week = tk.Frame(self.calendar_area, bg=COLORS["surface"])
        week.pack(fill="x")
        for index, label in enumerate(("一", "二", "三", "四", "五", "六", "日")):
            tk.Label(week, text=label, bg=COLORS["surface"], fg=COLORS["faint"],
                     font=("Microsoft YaHei UI", 8)).grid(
                row=0, column=index, sticky="nsew", pady=(0, 3))
            week.grid_columnconfigure(index, weight=1)

        self.days_frame = tk.Frame(self.calendar_area, bg=COLORS["surface"])
        self.days_frame.pack(fill="x")
        for index in range(7):
            self.days_frame.grid_columnconfigure(index, weight=1)
        self.day_buttons = []
        for index in range(42):
            button = tk.Button(
                self.days_frame, text="", bd=0, relief="flat",
                bg=COLORS["surface"], fg=COLORS["ink_soft"],
                activebackground=COLORS["accent_soft"], activeforeground=COLORS["accent"],
                font=("Microsoft YaHei UI", 9), width=3, height=1,
                highlightthickness=0, cursor="hand2",
            )
            button.grid(row=index // 7, column=index % 7, sticky="nsew", padx=1, pady=1)
            self.day_buttons.append(button)

        self.month_frame = tk.Frame(self.calendar_holder, bg=COLORS["surface"])
        self.year_frame = tk.Frame(self.calendar_holder, bg=COLORS["surface"])
        for frame in (self.month_frame, self.year_frame):
            for index in range(4):
                frame.grid_columnconfigure(index, weight=1)
            for index in range(3):
                frame.grid_rowconfigure(index, weight=1)

        tk.Frame(body, bg=COLORS["line_soft"], height=1).pack(fill="x", pady=(10, 8))
        time_row = tk.Frame(body, bg=COLORS["surface"])
        time_row.pack(fill="x")
        tk.Label(time_row, text="时间", bg=COLORS["surface"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")
        self.hour_var = tk.StringVar(value="%02d" % self.selected.hour)
        self.minute_var = tk.StringVar(value="%02d" % (self.selected.minute // 15 * 15))
        self.hour_box = ttk.Combobox(time_row, textvariable=self.hour_var, width=3,
                                     state="readonly", values=["%02d" % i for i in range(24)],
                                     font=("Consolas", 9))
        self.hour_box.pack(side="left", padx=(12, 3))
        tk.Label(time_row, text=":", bg=COLORS["surface"], fg=COLORS["muted"]).pack(side="left")
        self.minute_box = ttk.Combobox(time_row, textvariable=self.minute_var, width=3,
                                       state="readonly",
                                       values=["00", "15", "30", "45"],
                                       font=("Consolas", 9))
        self.minute_box.pack(side="left", padx=(3, 8))
        for label in ("09:00", "14:00", "18:00"):
            Chip(time_row, label, command=lambda v=label: self._quick_time(v),
                 height=23, font=("Microsoft YaHei UI", 7)).pack(side="left", padx=(0, 3))

        self.summary = tk.Label(body, text="", bg=COLORS["surface"], fg=COLORS["accent"],
                                font=("Microsoft YaHei UI", 9, "bold"), anchor="w")
        self.summary.pack(fill="x", pady=(10, 7))
        footer = tk.Frame(self.shell, bg=COLORS["surface"], height=56)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        tk.Frame(self.shell, bg=COLORS["line_soft"], height=1).pack(side="bottom", fill="x")
        PillButton(footer, "取消", self.close, kind="ghost", width=64,
                   height=34).pack(side="right", padx=(6, 12), pady=10)
        PillButton(footer, "确定", self._confirm, kind="primary", width=64,
                   height=34).pack(side="right", pady=10)
        PillButton(footer, "今天", self._today, kind="ghost", width=52,
                   height=34).pack(side="left", padx=12, pady=10)
        self._render_view()

    def _render_view(self):
        self.calendar_area.pack_forget()
        self.month_frame.pack_forget()
        self.year_frame.pack_forget()
        if self.view_mode == "day":
            self.calendar_area.pack(fill="x")
            self._render_month()
        elif self.view_mode == "month":
            self.month_frame.pack(fill="x", pady=(4, 0))
            self._render_months()
        else:
            self.year_frame.pack(fill="x", pady=(4, 0))
            self._render_years()
        self._update_title()

    def _update_title(self):
        if self.view_mode == "day":
            text = "%d 年 %02d 月  ▾" % (self.view_year, self.view_month)
        elif self.view_mode == "month":
            text = "%d 年  ▾" % self.view_year
        else:
            text = "%d – %d 年" % (self.decade_start, self.decade_start + 11)
        self.month_label.configure(text=text)

    def _drill_down(self):
        if self.view_mode == "day":
            self.view_mode = "month"
        elif self.view_mode == "month":
            self.view_mode = "year"
            self.decade_start = (self.view_year // 12) * 12
        self._render_view()

    def _shift_view(self, delta):
        if self.view_mode == "day":
            self._shift_month(delta)
        elif self.view_mode == "month":
            self.view_year += delta
            self._render_view()
        else:
            self.decade_start += delta * 12
            self._render_view()

    def _render_months(self):
        for child in list(self.month_frame.winfo_children()):
            child.destroy()
        for month in range(1, 13):
            selected = month == self.view_month
            button = tk.Button(
                self.month_frame, text="%d 月" % month, bd=0, relief="flat",
                bg=COLORS["accent"] if selected else COLORS["surface"],
                fg=COLORS["white"] if selected else COLORS["ink_soft"],
                activebackground=COLORS["accent_soft"],
                activeforeground=COLORS["accent"],
                font=("Microsoft YaHei UI", 9), height=2, highlightthickness=0,
                cursor="hand2", command=lambda m=month: self._choose_month(m),
            )
            button.grid(row=(month - 1) // 4, column=(month - 1) % 4,
                        sticky="nsew", padx=2, pady=2)

    def _render_years(self):
        for child in list(self.year_frame.winfo_children()):
            child.destroy()
        for offset in range(12):
            year = self.decade_start + offset
            selected = year == self.view_year
            button = tk.Button(
                self.year_frame, text=str(year), bd=0, relief="flat",
                bg=COLORS["accent"] if selected else COLORS["surface"],
                fg=COLORS["white"] if selected else COLORS["ink_soft"],
                activebackground=COLORS["accent_soft"],
                activeforeground=COLORS["accent"],
                font=("Microsoft YaHei UI", 9), height=2, highlightthickness=0,
                cursor="hand2", command=lambda y=year: self._choose_year(y),
            )
            button.grid(row=offset // 4, column=offset % 4,
                        sticky="nsew", padx=2, pady=2)

    def _choose_month(self, month):
        self.view_month = month
        last = calendar.monthrange(self.view_year, month)[1]
        self.selected = self.selected.replace(
            year=self.view_year, month=month, day=min(self.selected.day, last))
        self.view_mode = "day"
        self._render_view()

    def _choose_year(self, year):
        self.view_year = year
        last = calendar.monthrange(year, self.view_month)[1]
        self.selected = self.selected.replace(
            year=year, day=min(self.selected.day, last))
        self.view_mode = "month"
        self._render_view()

    def _render_month(self):
        weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(
            self.view_year, self.view_month)
        cells = []
        for week in weeks:
            cells.extend(week)
        while len(cells) < 42:
            cells.append(0)
        today = datetime.now().date()
        for button, day in zip(self.day_buttons, cells):
            if not day:
                button.configure(text="", state="disabled", bg=COLORS["surface"],
                                 command=lambda: None)
                continue
            selected = (day == self.selected.day and self.view_year == self.selected.year
                        and self.view_month == self.selected.month)
            is_today = (day == today.day and self.view_year == today.year
                        and self.view_month == today.month)
            button.configure(
                text=str(day), state="normal",
                bg=COLORS["accent"] if selected else COLORS["surface"],
                fg=COLORS["white"] if selected else (
                    COLORS["accent"] if is_today else COLORS["ink_soft"]),
                command=lambda d=day: self._choose_day(d),
            )
        self._update_summary()

    def _choose_day(self, day):
        self.selected = self.selected.replace(year=self.view_year, month=self.view_month, day=day)
        self._render_month()

    def _shift_month(self, delta):
        month = self.view_month + delta
        year = self.view_year
        if month < 1:
            month, year = 12, year - 1
        elif month > 12:
            month, year = 1, year + 1
        self.view_year, self.view_month = year, month
        last = calendar.monthrange(year, month)[1]
        self.selected = self.selected.replace(year=year, month=month, day=min(self.selected.day, last))
        self._render_month()
        self._update_title()

    def _today(self):
        now = datetime.now()
        self.selected = self.selected.replace(
            year=now.year, month=now.month, day=now.day)
        self.view_year, self.view_month = now.year, now.month
        self.view_mode = "day"
        self._render_view()

    def _quick_time(self, value):
        hour, minute = value.split(":")
        self.hour_var.set(hour)
        self.minute_var.set(minute)
        self._update_summary()

    def _update_summary(self):
        try:
            hour = int(self.hour_var.get())
            minute = int(self.minute_var.get())
        except ValueError:
            hour, minute = 18, 0
        self.selected = self.selected.replace(hour=hour, minute=minute)
        self.summary.configure(text="已选择  " + self.selected.strftime("%Y-%m-%d  %H:%M"))

    def _confirm(self):
        self._update_summary()
        value = self.selected.strftime("%Y-%m-%d %H:%M")
        callback = self.callback
        self.close()
        if callback:
            callback(value)

    def close(self):
        self.destroy()

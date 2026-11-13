# -*- coding: utf-8 -*-
"""Common modal, toast and form helpers."""

import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime

from .constants import COLORS, FONTS
from .model import parse_dt
from .widgets import PillButton, ScrollFrame, SmallIconButton, round_rect


def truncate(text, limit):
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def mail_time(value):
    dt = parse_dt(value)
    if not dt:
        return ""
    now = datetime.now()
    if dt.date() == now.date():
        return "今天 %s" % dt.strftime("%H:%M")
    if (now.date() - dt.date()).days == 1:
        return "昨天 %s" % dt.strftime("%H:%M")
    return dt.strftime("%m/%d")


def section_card(parent, bg=None):
    card = tk.Frame(parent, bg=COLORS["surface"], bd=0,
                   highlightthickness=1, highlightbackground=COLORS["line"])
    inner = tk.Frame(card, bg=COLORS["surface"], padx=16, pady=14)
    inner.pack(fill="both", expand=True)
    return card, inner


def field_label(parent, text, hint="", bg=None):
    bg = bg or COLORS["surface"]
    row = tk.Frame(parent, bg=bg)
    tk.Label(row, text=text, bg=bg, fg=COLORS["ink_soft"],
             font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(side="left")
    if hint:
        tk.Label(row, text=hint, bg=bg, fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8), anchor="w").pack(side="left", padx=(7, 0))
    return row


def styled_entry(parent, textvariable=None, bg=None, font=None, show=None,
                 width=20, justify="left"):
    bg = bg or COLORS["surface"]
    entry = tk.Entry(
        parent, textvariable=textvariable, bg=bg, fg=COLORS["ink"],
        insertbackground=COLORS["accent"], relief="flat", bd=0,
        highlightthickness=1, highlightbackground=COLORS["line"],
        highlightcolor=COLORS["accent"], font=font or ("Microsoft YaHei UI", 10),
        show=show, width=width, justify=justify,
    )
    return entry


def styled_text(parent, value="", bg=None, height=3, font=None):
    bg = bg or COLORS["surface"]
    text = tk.Text(
        parent, bg=bg, fg=COLORS["ink"], insertbackground=COLORS["accent"],
        relief="flat", bd=0, highlightthickness=1,
        highlightbackground=COLORS["line"], highlightcolor=COLORS["accent"],
        font=font or ("Microsoft YaHei UI", 10), height=height, width=1,
        wrap="word", padx=9, pady=7, spacing1=1, spacing3=2,
    )
    text.insert("1.0", value or "")
    return text


def status_pill(parent, status, bg=None):
    from .constants import status_meta

    meta = status_meta(status)
    return tk.Label(
        parent, text=meta["label"], bg=meta["soft"], fg=meta["color"],
        font=("Microsoft YaHei UI", 8, "bold"), padx=8, pady=2,
    )


def separator(parent, bg=None, pady=0):
    frame = tk.Frame(parent, bg=COLORS["line_soft"], height=1)
    frame.pack(fill="x", pady=pady)
    return frame


def gap(parent, height=12):
    frame = tk.Frame(parent, bg=parent.cget("bg"), height=height)
    frame.pack(fill="x")
    return frame


class Modal(tk.Frame):
    def __init__(self, app, title, subtitle=""):
        tk.Frame.__init__(self, app, bg=COLORS["bg"], bd=0, highlightthickness=0)
        self.app = app
        self.dirty = False
        self._closing = False
        self.place(x=1, y=1, width=app.W - 2, height=app.H - 2)
        self.lift()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = tk.Frame(self, bg=COLORS["surface"], height=58)
        header.grid(row=0, column=0, sticky="ew")
        header.pack_propagate(False)
        self.header = header
        self.back = SmallIconButton(header, "‹", self.request_close, bg=COLORS["surface"],
                                    size=34, fg=COLORS["ink_soft"])
        self.back.pack(side="left", padx=(10, 4))
        title_box = tk.Frame(header, bg=COLORS["surface"])
        title_box.pack(side="left", fill="y")
        self.title_label = tk.Label(title_box, text=title, bg=COLORS["surface"],
                                    fg=COLORS["ink"], font=("Microsoft YaHei UI", 12, "bold"))
        self.title_label.pack(anchor="w", pady=(8 if subtitle else 0, 0))
        subtitle_label = None
        if subtitle:
            subtitle_label = tk.Label(title_box, text=subtitle, bg=COLORS["surface"],
                                      fg=COLORS["faint"], font=("Microsoft YaHei UI", 8))
            subtitle_label.pack(anchor="w")
        self.close_btn = SmallIconButton(header, "×", self.request_close,
                                         bg=COLORS["surface"], size=32)
        self.close_btn.pack(side="right", padx=(4, 10))
        tk.Frame(self, bg=COLORS["line"], height=1).grid(row=0, column=0, sticky="sew")
        for widget in (header, title_box, self.title_label):
            widget.bind("<ButtonPress-1>", app._start_drag)
            widget.bind("<B1-Motion>", app._do_drag)
            widget.bind("<ButtonRelease-1>", app._end_drag)
        if subtitle_label is not None:
            subtitle_label.bind("<ButtonPress-1>", app._start_drag)
            subtitle_label.bind("<B1-Motion>", app._do_drag)
            subtitle_label.bind("<ButtonRelease-1>", app._end_drag)

        self.scroll = ScrollFrame(self, bg=COLORS["bg"], padding=20)
        self.scroll.grid(row=1, column=0, sticky="nsew")
        self.content = self.scroll.inner

        self.footer = tk.Frame(self, bg=COLORS["surface"], height=68)
        self.footer.grid(row=2, column=0, sticky="ew")
        self.footer.pack_propagate(False)
        tk.Frame(self, bg=COLORS["line"], height=1).grid(row=2, column=0, sticky="new")
        self.footer_left = tk.Frame(self.footer, bg=COLORS["surface"])
        self.footer_left.pack(side="left", padx=16)
        self.footer_right = tk.Frame(self.footer, bg=COLORS["surface"])
        self.footer_right.pack(side="right", padx=16)
        app.register_modal(self)

    def add_footer_button(self, text, command, kind="ghost", width=None, side="right"):
        parent = self.footer_right if side == "right" else self.footer_left
        button = PillButton(parent, text, command, kind=kind, width=width, height=36)
        button.pack(side="left", padx=(8, 0) if side == "right" else (0, 8), pady=16)
        return button

    def set_dirty(self, value=True):
        self.dirty = bool(value)

    def request_close(self):
        if self._closing:
            return
        if self.dirty:
            self.app.confirm(
                "放弃未保存的修改？",
                "当前编辑内容还没有保存，关闭后会丢失。",
                "放弃修改",
                self.force_close,
                danger=True,
            )
        else:
            self.force_close()

    def force_close(self):
        self._closing = True
        self.app.unregister_modal(self)
        self.destroy()


class Toast(object):
    def __init__(self, app):
        self.app = app
        self.current = None
        self.after_id = None

    def __call__(self, text, kind="info", duration=2600):
        self.show(text, kind, duration)

    def show(self, text, kind="info", duration=2600):
        self.hide()
        palette = {
            "info": (COLORS["dark"], COLORS["white"]),
            "success": (COLORS["mint"], COLORS["white"]),
            "error": (COLORS["danger"], COLORS["white"]),
            "warn": (COLORS["amber"], COLORS["white"]),
        }
        fill, fg = palette.get(kind, palette["info"])
        width = 350
        canvas = tk.Canvas(self.app, width=width, height=44, bg=COLORS["bg"],
                           highlightthickness=0, bd=0)
        font = tkfont.Font(family="Microsoft YaHei UI", size=9)
        text_id = canvas.create_text(width / 2, 22, text=text, fill=fg, font=font,
                                     width=width - 34, justify="center")
        bbox = canvas.bbox(text_id)
        height = max(42, (bbox[3] - bbox[1]) + 22)
        canvas.configure(height=height)
        round_rect(canvas, 1, 1, width - 1, height - 1, 12, fill=fill, outline=fill)
        canvas.tag_raise(text_id)
        canvas.place(relx=0.5, y=self.app.H - 78, anchor="s")
        tk.Misc.lift(canvas)
        self.current = canvas
        self.after_id = self.app.after(duration, self.hide)

    def hide(self):
        if self.after_id:
            try:
                self.app.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None
        if self.current is not None:
            try:
                self.current.destroy()
            except Exception:
                pass
            self.current = None


class EmptyState(tk.Frame):
    def __init__(self, parent, title, message, action_text=None, command=None,
                 icon="tasks", bg=None):
        bg = bg or COLORS["bg"]
        tk.Frame.__init__(self, parent, bg=bg)
        canvas = tk.Canvas(self, width=76, height=76, bg=bg, highlightthickness=0, bd=0)
        canvas.pack(pady=(22, 12))
        canvas.create_oval(4, 4, 72, 72, fill=COLORS["surface"], outline=COLORS["line"])
        if icon == "mail":
            canvas.create_rectangle(21, 26, 55, 50, outline=COLORS["accent"], width=2)
            canvas.create_line(21, 28, 38, 41, 55, 28, fill=COLORS["accent"], width=2,
                               capstyle="round", joinstyle="round")
        else:
            for i, y in enumerate((28, 38, 48)):
                canvas.create_oval(22, y - 2, 26, y + 2, fill=COLORS["accent"],
                                   outline=COLORS["accent"])
                canvas.create_line(31, y, 53, y, fill=COLORS["line"], width=3,
                                   capstyle="round")
            canvas.create_line(24, 38, 29, 43, 38, 31, fill=COLORS["mint"], width=2,
                               capstyle="round", joinstyle="round")
        tk.Label(self, text=title, bg=bg, fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 11, "bold")).pack()
        tk.Label(self, text=message, bg=bg, fg=COLORS["muted"],
                 font=("Microsoft YaHei UI", 9), wraplength=300,
                 justify="center").pack(pady=(5, 14))
        if action_text and command:
            PillButton(self, action_text, command, kind="soft", height=34).pack()
        tk.Frame(self, bg=bg, height=24).pack()

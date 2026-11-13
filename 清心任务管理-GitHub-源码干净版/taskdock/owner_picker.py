# -*- coding: utf-8 -*-
"""Owner selector backed by the collaboration directory when available."""

import tkinter as tk
from tkinter import ttk

from .constants import COLORS


class OwnerField(tk.Frame):
    def __init__(self, parent, app, display="", username="", bg=None):
        bg = bg or COLORS["surface"]
        tk.Frame.__init__(self, parent, bg=bg)
        self.app = app
        self.mapping = {}
        self.var = tk.StringVar()
        users = app.owner_options()
        self.mapping["待指派"] = ("", "")
        labels = ["待指派"]
        for user in users:
            name = user.get("display_name") or user.get("username") or ""
            account = user.get("username") or ""
            prefix = "本人 · " if user.get("source") == "self" else ""
            label = prefix + name + (" · @" + account if account else "")
            if label not in self.mapping:
                self.mapping[label] = (name, account)
                labels.append(label)
        self.values = list(dict.fromkeys(labels))
        self._set_initial(display, username)
        style = ttk.Style(self)
        try:
            style.configure("TaskDock.TCombobox", fieldbackground=COLORS["surface"],
                            background=COLORS["surface"], foreground=COLORS["ink"],
                            padding=5)
        except Exception:
            pass
        self.box = ttk.Combobox(self, textvariable=self.var, values=labels,
                                state="readonly", font=("Microsoft YaHei UI", 9),
                                style="TaskDock.TCombobox")
        self.box.pack(fill="x", ipady=2)
        self.box.bind("<<ComboboxSelected>>", self._selected)

    def _set_initial(self, display, username):
        display = (display or "").strip()
        username = (username or "").strip().lstrip("@")
        if not display or display in ("待指派", "未指定", "待定"):
            self.var.set("待指派")
            return
        for label, (name, account) in self.mapping.items():
            if label == "待指派":
                continue
            if (username and account.lower() == username.lower()) or (
                    not username and name == display):
                self.var.set(label)
                return
        label = display + (" · @" + username if username else "")
        if label in self.mapping:
            self.var.set(label)
            return
        self.mapping[label] = (display, username)
        if label not in self.values:
            self.values.append(label)
        self.var.set(label)

    def _selected(self, _event=None):
        pass

    def get(self):
        return self.mapping.get(self.var.get(), ("", ""))

    def set(self, display, username=""):
        self._set_initial(display, username)

    def focus_set(self):
        try:
            self.box.focus_set()
        except Exception:
            pass

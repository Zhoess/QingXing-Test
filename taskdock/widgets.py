# -*- coding: utf-8 -*-
"""Small hand-drawn Tk widgets used to keep the panel visually cohesive."""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from .constants import COLORS, FONT_FAMILY, FONT_ICON


def round_rect(canvas, x1, y1, x2, y2, radius=12, **kwargs):
    radius = max(0, min(radius, int((x2 - x1) / 2), int((y2 - y1) / 2)))
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


def _safe_bg(widget, fallback=None):
    try:
        return widget.cget("bg")
    except Exception:
        return fallback or COLORS["bg"]


class ScrollFrame(tk.Frame):
    """A frame with an invisible, smooth mouse-wheel scroll area."""

    def __init__(self, parent, bg=None, padding=0, scrollbar=False):
        bg = bg or _safe_bg(parent)
        tk.Frame.__init__(self, parent, bg=bg, bd=0, highlightthickness=0)
        self.canvas = tk.Canvas(
            self, bg=bg, bd=0, highlightthickness=0, yscrollincrement=24
        )
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar = None
        if scrollbar:
            self.scrollbar = ttk.Scrollbar(self, orient="vertical",
                                           command=self.canvas.yview)
            self.scrollbar.pack(side="right", fill="y")
            self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.inner = tk.Frame(self.canvas, bg=bg, bd=0, highlightthickness=0)
        self.window = self.canvas.create_window(
            (padding, padding), window=self.inner, anchor="nw"
        )
        self.padding = padding
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.inner.bind("<MouseWheel>", self._on_wheel)
        self._wheel = _WheelProxy(self)

    def _on_inner_configure(self, _event=None):
        bbox = self.canvas.bbox("all")
        if bbox:
            # Start the scroll region at the canvas origin so the top padding
            # remains visible when scrolled all the way up.
            self.canvas.configure(scrollregion=(
                0, 0, max(bbox[2], self.canvas.winfo_width()),
                max(bbox[3], self.canvas.winfo_height())
            ))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.window, width=max(1, event.width - self.padding * 2))
        self._on_inner_configure()

    def _on_wheel(self, event):
        self.scroll(event.delta)

    def scroll(self, delta):
        if self.canvas.bbox("all") is None:
            return
        steps = -1 if delta > 0 else 1
        magnitude = max(1, min(4, abs(int(delta / 120)) or 1))
        self.canvas.yview_scroll(steps * magnitude, "units")

    def scroll_to_top(self):
        self.canvas.yview_moveto(0.0)

    def refresh(self):
        self.inner.update_idletasks()
        self._on_inner_configure()

    def descendants(self):
        items = []
        stack = [self.inner]
        while stack:
            widget = stack.pop()
            items.append(widget)
            stack.extend(widget.winfo_children())
        return items

    def bind_wheel_all(self, function):
        for widget in self.descendants():
            widget.bind("<MouseWheel>", function, add="+")


class _WheelProxy(object):
    """Keeps a reference alive; ScrollFrame's app-level handler is preferred."""

    def __init__(self, frame):
        self.frame = frame


def bind_tree(widget, sequence, callback, add="+"):
    widget.bind(sequence, callback, add=add)
    for child in widget.winfo_children():
        bind_tree(child, sequence, callback, add=add)


class PillButton(tk.Canvas):
    def __init__(self, parent, text, command=None, kind="primary", width=None,
                 height=36, radius=10, font=None, icon="", bg=None, padx=16,
                 disabled=False):
        bg = bg or _safe_bg(parent)
        self._font = tkfont.Font(font=font or ("Microsoft YaHei UI", 10, "bold"))
        self._icon_font = tkfont.Font(family=FONT_ICON, size=10)
        label = ("%s  %s" % (icon, text)).strip() if icon else text
        text_width = self._font.measure(label) + self._icon_font.measure(icon)
        width = int(width or max(40, text_width + padx * 2))
        tk.Canvas.__init__(self, parent, width=width, height=height, bg=bg,
                           highlightthickness=0, bd=0, cursor="hand2")
        self.text = text
        self.command = command
        self.kind = kind
        self.radius = radius
        self.width = width
        self.height = height
        self._font_spec = font or ("Microsoft YaHei UI", 10, "bold")
        self._label = label
        self._icon = icon
        self._disabled = bool(disabled)
        self._hover = False
        self._pressed = False
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _palette(self):
        if self._disabled:
            return COLORS["line_soft"], COLORS["faint"], COLORS["line_soft"]
        if self.kind == "primary":
            return (COLORS["accent_hover"] if self._hover else COLORS["accent"]), COLORS["white"], COLORS["accent"]
        if self.kind == "dark":
            return (COLORS["dark_soft"] if self._hover else COLORS["dark"]), COLORS["white"], COLORS["dark"]
        if self.kind == "soft":
            return (COLORS["accent_pale"] if self._hover else COLORS["accent_soft"]), COLORS["accent"], COLORS["accent_soft"]
        if self.kind == "ghost":
            return (COLORS["surface_alt"] if self._hover else _safe_bg(self.master)), COLORS["ink_soft"], COLORS["line"]
        if self.kind == "danger":
            return (COLORS["danger"] if self._hover else COLORS["danger_soft"]), (COLORS["white"] if self._hover else COLORS["danger"]), COLORS["danger_soft"]
        return COLORS["surface"], COLORS["ink"], COLORS["line"]

    def _draw(self):
        self.delete("all")
        fill, fg, outline = self._palette()
        round_rect(self, 1, 1, self.width - 1, self.height - 1, self.radius,
                   fill=fill, outline=outline, width=1)
        self.create_text(self.width / 2, self.height / 2 + 0.5, text=self._label,
                         fill=fg, font=self._font_spec)

    def _on_enter(self, _event):
        if not self._disabled:
            self._hover = True
            self._draw()

    def _on_leave(self, _event):
        self._hover = False
        self._pressed = False
        self._draw()

    def _on_press(self, _event):
        if not self._disabled:
            self._pressed = True

    def _on_release(self, event):
        if self._disabled:
            return
        inside = 0 <= event.x <= self.width and 0 <= event.y <= self.height
        was = self._pressed
        self._pressed = False
        if was and inside and self.command:
            self.command()

    def set_disabled(self, value):
        self._disabled = bool(value)
        self.configure(cursor="arrow" if self._disabled else "hand2")
        self._draw()

    def set_text(self, text):
        self.text = text
        self._label = text
        self._draw()

    def set_kind(self, kind):
        self.kind = kind
        self._draw()


class Chip(tk.Canvas):
    def __init__(self, parent, text, command=None, selected=False, height=28,
                 font=None, count=None, bg=None):
        bg = bg or _safe_bg(parent)
        self._font = tkfont.Font(font=font or ("Microsoft YaHei UI", 9))
        self._label = text if count is None else "%s %d" % (text, count)
        width = self._font.measure(self._label) + 24
        tk.Canvas.__init__(self, parent, width=width, height=height, bg=bg,
                           highlightthickness=0, bd=0, cursor="hand2")
        self.width = width
        self.height = height
        self.command = command
        self.selected = selected
        self._hover = False
        self._draw()
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", lambda _e: self.command() if self.command else None)

    def _draw(self):
        self.delete("all")
        if self.selected:
            fill, fg, outline = COLORS["ink"], COLORS["white"], COLORS["ink"]
        elif self._hover:
            fill, fg, outline = COLORS["surface"], COLORS["ink"], COLORS["line"]
        else:
            fill, fg, outline = COLORS["surface"], COLORS["muted"], COLORS["line"]
        round_rect(self, 1, 1, self.width - 1, self.height - 1, self.height / 2,
                   fill=fill, outline=outline, width=1)
        self.create_text(self.width / 2, self.height / 2 + 0.5, text=self._label,
                         fill=fg, font=self._font)

    def _enter(self, _event):
        self._hover = True
        self._draw()

    def _leave(self, _event):
        self._hover = False
        self._draw()

    def set_selected(self, value):
        self.selected = bool(value)
        self._draw()


class Toggle(tk.Canvas):
    def __init__(self, parent, value=False, command=None, bg=None, width=42, height=24):
        bg = bg or _safe_bg(parent)
        tk.Canvas.__init__(self, parent, width=width, height=height, bg=bg,
                           highlightthickness=0, bd=0, cursor="hand2")
        self.width = width
        self.height = height
        self.value = bool(value)
        self.command = command
        self._draw()
        self.bind("<Button-1>", self._toggle)

    def _draw(self):
        self.delete("all")
        fill = COLORS["accent"] if self.value else COLORS["line"]
        round_rect(self, 1, 1, self.width - 1, self.height - 1, self.height / 2,
                   fill=fill, outline=fill)
        cx = self.width - self.height / 2 if self.value else self.height / 2
        r = self.height / 2 - 3
        self.create_oval(cx - r, self.height / 2 - r, cx + r, self.height / 2 + r,
                         fill=COLORS["white"], outline=COLORS["white"])

    def _toggle(self, _event):
        self.value = not self.value
        self._draw()
        if self.command:
            self.command(self.value)

    def set(self, value):
        self.value = bool(value)
        self._draw()


class ProgressSlider(tk.Canvas):
    def __init__(self, parent, value=0, command=None, bg=None, width=310,
                 height=30, limit=99):
        bg = bg or _safe_bg(parent)
        tk.Canvas.__init__(self, parent, width=width, height=height, bg=bg,
                           highlightthickness=0, bd=0, cursor="hand2")
        self.width = width
        self.height = height
        self.value = max(0, min(limit, int(value)))
        self.limit = limit
        self.command = command
        self._draw()
        self.bind("<Button-1>", self._set_from_event)
        self.bind("<B1-Motion>", self._set_from_event)
        self.bind("<ButtonRelease-1>", self._release)

    def _x_for(self, value):
        return 8 + (self.width - 16) * value / 100.0

    def _set_from_event(self, event):
        ratio = (event.x - 8) / float(max(1, self.width - 16))
        value = int(round(max(0, min(1, ratio)) * 100))
        value = min(value, self.limit)
        if value != self.value:
            self.value = value
            self._draw()
            if self.command:
                self.command(value)

    def _release(self, _event):
        if self.command:
            self.command(self.value, True)

    def _draw(self):
        self.delete("all")
        y = self.height / 2
        round_rect(self, 8, y - 3, self.width - 8, y + 3, 3,
                   fill=COLORS["line"], outline=COLORS["line"])
        end = self._x_for(self.value)
        if self.value > 0:
            round_rect(self, 8, y - 3, end, y + 3, 3,
                       fill=COLORS["accent"], outline=COLORS["accent"])
        r = 8
        self.create_oval(end - r, y - r, end + r, y + r,
                         fill=COLORS["white"], outline=COLORS["accent"], width=2)

    def set(self, value):
        self.value = max(0, min(self.limit, int(value)))
        self._draw()

    def set_limit(self, limit):
        self.limit = max(0, min(100, int(limit)))
        if self.value > self.limit:
            self.value = self.limit
        self._draw()


class NavItem(tk.Frame):
    def __init__(self, parent, icon, label, command, active=False, bg=None):
        bg = bg or COLORS["surface"]
        tk.Frame.__init__(self, parent, bg=bg, cursor="hand2")
        self.icon = icon
        self.label = label
        self.command = command
        self.active = active
        self.bg = bg
        self.icon_canvas = tk.Canvas(self, width=24, height=22, bg=bg,
                                     highlightthickness=0, bd=0, cursor="hand2")
        self.icon_canvas.pack(pady=(7, 0))
        self.text = tk.Label(self, text=label, bg=bg, fg=COLORS["muted"],
                             font=("Microsoft YaHei UI", 8), cursor="hand2")
        self.text.pack(pady=(1, 5))
        for widget in (self, self.icon_canvas, self.text):
            widget.bind("<Button-1>", self._click)
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)
        self._draw()

    def _draw(self):
        color = COLORS["accent"] if self.active else COLORS["muted"]
        c = self.icon_canvas
        c.delete("all")
        if self.active:
            c.create_line(5, 1, 19, 1, fill=COLORS["accent"], width=2,
                          capstyle="round")
        if self.icon == "tasks":
            for i, y in enumerate((5, 11, 17)):
                c.create_oval(3, y - 1.5, 6, y + 1.5, fill=color, outline=color)
                c.create_line(9, y, 21, y, fill=color, width=1.6,
                              capstyle="round")
        elif self.icon == "mail":
            c.create_rectangle(3, 5, 21, 18, outline=color, width=1.6)
            c.create_line(3, 6, 12, 13, 21, 6, fill=color, width=1.6,
                          capstyle="round", joinstyle="round")
        elif self.icon == "users":
            c.create_oval(3, 5, 10, 12, outline=color, width=1.6)
            c.create_arc(1, 10, 12, 21, start=0, extent=180, style="arc",
                         outline=color, width=1.6)
            c.create_oval(14, 4, 21, 11, outline=color, width=1.6)
            c.create_arc(12, 9, 23, 20, start=0, extent=180, style="arc",
                         outline=color, width=1.6)
        elif self.icon == "settings":
            c.create_oval(8, 6, 16, 14, outline=color, width=1.7)
            c.create_oval(10.5, 8.5, 13.5, 11.5, fill=color, outline=color)
            for angle in (0, 60, 120, 180, 240, 300):
                import math
                rad = math.radians(angle)
                x1, y1 = 12 + 6.1 * math.cos(rad), 11 + 6.1 * math.sin(rad)
                x2, y2 = 12 + 8.4 * math.cos(rad), 11 + 8.4 * math.sin(rad)
                c.create_line(x1, y1, x2, y2, fill=color, width=1.6,
                              capstyle="round")
        self.text.configure(fg=COLORS["accent"] if self.active else COLORS["muted"],
                            font=("Microsoft YaHei UI", 8, "bold" if self.active else "normal"))

    def set_active(self, active):
        self.active = bool(active)
        self._draw()

    def _click(self, _event):
        if self.command:
            self.command()

    def _enter(self, _event):
        if not self.active:
            self.configure(bg=COLORS["surface_alt"])
            self.icon_canvas.configure(bg=COLORS["surface_alt"])
            self.text.configure(bg=COLORS["surface_alt"])

    def _leave(self, _event):
        self.configure(bg=self.bg)
        self.icon_canvas.configure(bg=self.bg)
        self.text.configure(bg=self.bg)


class CheckCircle(tk.Canvas):
    def __init__(self, parent, checked=False, command=None, size=22, bg=None,
                 color=None, disabled=False):
        bg = bg or _safe_bg(parent)
        tk.Canvas.__init__(self, parent, width=size, height=size, bg=bg,
                           highlightthickness=0, bd=0,
                           cursor="arrow" if disabled else "hand2")
        self.size = size
        self.checked = bool(checked)
        self.command = command
        self.color = color or COLORS["accent"]
        self.disabled = disabled
        self._draw()
        if not disabled:
            self.bind("<Button-1>", self._click)

    def _draw(self):
        self.delete("all")
        pad = 2
        if self.checked:
            self.create_oval(pad, pad, self.size - pad, self.size - pad,
                             fill=self.color, outline=self.color)
            self.create_line(6, self.size / 2, 10, self.size - 7,
                             self.size - 6, 7,
                             fill=COLORS["white"], width=2, capstyle="round",
                             joinstyle="round")
        else:
            self.create_oval(pad, pad, self.size - pad, self.size - pad,
                             outline=COLORS["line"], width=1.6, fill=COLORS["surface"])

    def set(self, checked):
        self.checked = bool(checked)
        self._draw()

    def _click(self, _event):
        if self.command:
            self.command()


class SmallIconButton(tk.Canvas):
    """A 28px icon button drawn with text symbols (×, ‹, …, ↻)."""

    def __init__(self, parent, symbol, command=None, bg=None, size=28,
                 fg=None, hover_bg=None, tooltip=""):
        bg = bg or _safe_bg(parent)
        tk.Canvas.__init__(self, parent, width=size, height=size, bg=bg,
                           highlightthickness=0, bd=0, cursor="hand2")
        self.symbol = symbol
        self.command = command
        self.size = size
        self.fg = fg or COLORS["muted"]
        self.hover_bg = hover_bg or COLORS["surface_alt"]
        self.bg = bg
        self._hover = False
        self._draw()
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._click)

    def _draw(self):
        self.delete("all")
        if self._hover:
            round_rect(self, 1, 1, self.size - 1, self.size - 1, 7,
                       fill=self.hover_bg, outline=self.hover_bg)
        font = ("Microsoft YaHei UI", 13)
        if self.symbol in ("↻", "＋"):
            font = ("Segoe UI Symbol", 13)
        self.create_text(self.size / 2, self.size / 2 - 1, text=self.symbol,
                         fill=self.fg, font=font)

    def _enter(self, _event):
        self._hover = True
        self._draw()

    def _leave(self, _event):
        self._hover = False
        self._draw()

    def _click(self, _event):
        if self.command:
            self.command()

    def set_symbol(self, symbol):
        self.symbol = symbol
        self._draw()


class TagLabel(tk.Label):
    def __init__(self, parent, text, bg, fg, font=None):
        tk.Label.__init__(self, parent, text=text, bg=bg, fg=fg,
                          font=font or ("Microsoft YaHei UI", 8),
                          padx=7, pady=2)


def dot(parent, color, bg, size=6):
    canvas = tk.Canvas(parent, width=size, height=size, bg=bg,
                       highlightthickness=0, bd=0)
    canvas.create_oval(0, 0, size, size, fill=color, outline=color)
    return canvas


def hline(parent, color=None, bg=None, padx=0, pady=0):
    line = tk.Frame(parent, height=1, bg=color or COLORS["line_soft"])
    line.pack(fill="x", padx=padx, pady=pady)
    return line


def wrap_label(parent, text, font, fg, bg, width=340, justify="left"):
    return tk.Label(parent, text=text, font=font, fg=fg, bg=bg,
                    wraplength=width, justify=justify, anchor="w")

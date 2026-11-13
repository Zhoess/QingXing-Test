# -*- coding: utf-8 -*-
"""Shared constants for TaskDock."""

APP_NAME = "清心任务客户端"
APP_NAME_EN = "TASKCLIENT"
VERSION = "2.0.0"

# Palette: warm paper, forest ink, terracotta accent.
COLORS = {
    "bg": "#F3EFE7",
    "surface": "#FFFDF8",
    "surface_alt": "#FAF7F0",
    "surface_hover": "#FCFAF5",
    "ink": "#232824",
    "ink_soft": "#4D534C",
    "muted": "#7C766A",
    "faint": "#A39C8E",
    "line": "#E3DCCE",
    "line_soft": "#EEE8DC",
    "accent": "#D2643F",
    "accent_hover": "#BC5735",
    "accent_soft": "#F8E6DD",
    "accent_pale": "#FCF2EC",
    "dark": "#22302A",
    "dark_soft": "#2F4038",
    "dark_line": "#42544B",
    "mint": "#5A8A70",
    "mint_soft": "#E7F0EA",
    "blue": "#567A90",
    "blue_soft": "#E8EFF4",
    "amber": "#A77B32",
    "amber_soft": "#F5EDDD",
    "danger": "#BF5546",
    "danger_soft": "#F8E6E2",
    "white": "#FFFFFF",
    "shadow": "#D8D0C2",
}

FONT_FAMILY = "Microsoft YaHei UI"
FONT_ICON = "Segoe UI Symbol"
FONT_NUM = "Georgia"

FONTS = {
    "hero_date": (FONT_FAMILY, 9),
    "hero": (FONT_FAMILY, 16, "bold"),
    "hero_small": (FONT_FAMILY, 9),
    "h1": (FONT_FAMILY, 17, "bold"),
    "h2": (FONT_FAMILY, 12, "bold"),
    "title": (FONT_FAMILY, 11, "bold"),
    "body": (FONT_FAMILY, 10),
    "body_bold": (FONT_FAMILY, 10, "bold"),
    "small": (FONT_FAMILY, 9),
    "small_bold": (FONT_FAMILY, 9, "bold"),
    "tiny": (FONT_FAMILY, 8),
    "tiny_bold": (FONT_FAMILY, 8, "bold"),
    "button": (FONT_FAMILY, 10, "bold"),
    "nav": (FONT_FAMILY, 8),
    "nav_active": (FONT_FAMILY, 8, "bold"),
    "mono": ("Consolas", 9),
    "number": (FONT_NUM, 15, "bold"),
}

CYCLES = ["一次性", "每日", "每周", "每月", "每季度"]

FILTERS = [
    ("all", "全部"),
    ("doing", "进行中"),
    ("upcoming", "待开始"),
    ("overdue", "已逾期"),
    ("lost", "流失"),
    ("done", "已完成"),
]

STATUS_META = {
    "done": {"label": "已完成", "color": COLORS["mint"], "soft": COLORS["mint_soft"]},
    "lost": {"label": "已流失", "color": COLORS["danger"], "soft": COLORS["danger_soft"]},
    "overdue": {"label": "已逾期", "color": COLORS["danger"], "soft": COLORS["danger_soft"]},
    "doing": {"label": "进行中", "color": COLORS["blue"], "soft": COLORS["blue_soft"]},
    "upcoming": {"label": "待开始", "color": COLORS["amber"], "soft": COLORS["amber_soft"]},
    "todo": {"label": "待开始", "color": COLORS["amber"], "soft": COLORS["amber_soft"]},
}

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def status_meta(key):
    return STATUS_META.get(key, STATUS_META["todo"])

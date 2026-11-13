# -*- coding: utf-8 -*-
"""Settings: mailbox, window behavior, backup and about."""

import os
import tkinter as tk
from tkinter import filedialog, ttk

from . import analyzer, model
from .constants import APP_NAME, COLORS, VERSION
from .ui_common import (EmptyState, Modal, field_label, gap, section_card, styled_entry,
                        truncate)
from .widgets import Chip, PillButton, ScrollFrame, SmallIconButton, Toggle


AI_PRESETS = {
    "OpenAI": ("https://api.openai.com/v1/chat/completions", "gpt-4o-mini"),
    "DeepSeek": ("https://api.deepseek.com/chat/completions", "deepseek-chat"),
    "智谱 GLM": ("https://open.bigmodel.cn/api/paas/v4/chat/completions", "glm-4-flash"),
    "通义千问": ("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions", "qwen-plus"),
    "自定义": ("", ""),
}


def _provider_from_endpoint(endpoint):
    value = (endpoint or "").lower()
    if "deepseek" in value:
        return "DeepSeek"
    if "bigmodel" in value or "zhipu" in value:
        return "智谱 GLM"
    if "dashscope" in value or "aliyuncs" in value:
        return "通义千问"
    if "openai" in value:
        return "OpenAI"
    return "自定义"


class SettingsPage(tk.Frame):
    def __init__(self, parent, app):
        tk.Frame.__init__(self, parent, bg=COLORS["bg"])
        self.app = app
        self.scroll = ScrollFrame(self, bg=COLORS["bg"], padding=20)
        self.scroll.pack(fill="both", expand=True)
        self.body = self.scroll.inner
        self._build()

    def on_show(self):
        self._refresh_status()
        self._render_owners()

    def focus_ai(self):
        self.update_idletasks()
        total = max(1, self.body.winfo_height())
        y = max(0, self.ai_card.winfo_y() - 12)
        self.scroll.canvas.yview_moveto(min(1.0, y / total))

    def _build(self):
        settings = self.app.store.settings()
        body = self.body
        head = tk.Frame(body, bg=COLORS["bg"])
        head.pack(fill="x", pady=(2, 1))
        tk.Label(head, text="设置", bg=COLORS["bg"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 15, "bold")).pack(side="left")
        tk.Label(body, text="本地优先 · 数据与邮件解析都留在这台电脑", bg=COLORS["bg"],
                 fg=COLORS["faint"], font=("Microsoft YaHei UI", 8), anchor="w").pack(
            fill="x", pady=(1, 14))

        # ------------------------------------------------------------- mailbox
        card, inner = section_card(body)
        card.pack(fill="x", pady=(0, 12))
        title_row = tk.Frame(inner, bg=COLORS["surface"])
        title_row.pack(fill="x", pady=(0, 2))
        tk.Label(title_row, text="钉钉邮箱", bg=COLORS["surface"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        self.mail_status = tk.Label(title_row, text="", bg=COLORS["surface_alt"],
                                    fg=COLORS["faint"], font=("Microsoft YaHei UI", 8),
                                    padx=7, pady=2)
        self.mail_status.pack(side="right")
        tk.Label(inner, text="只读收件箱，通过 IMAP 获取最近邮件。不会发送或删除任何邮件。",
                 bg=COLORS["surface"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 8),
                 anchor="w", justify="left", wraplength=330).pack(fill="x", pady=(0, 11))

        self.account_var = tk.StringVar(value=settings.get("account", ""))
        self.password_var = tk.StringVar(value="")
        self.host_var = tk.StringVar(value=settings.get("imap_host", "imap.em.dingtalk.com"))
        self.port_var = tk.StringVar(value=str(settings.get("imap_port", 993)))
        self.days_var = tk.StringVar(value=str(settings.get("days", 14)))

        field_label(inner, "邮箱账号").pack(fill="x", pady=(0, 4))
        styled_entry(inner, self.account_var).pack(fill="x", ipady=6)
        gap(inner, 10)
        pass_row = tk.Frame(inner, bg=COLORS["surface"])
        pass_row.pack(fill="x", pady=(0, 4))
        tk.Label(pass_row, text="专用密码 / 授权码", bg=COLORS["surface"],
                 fg=COLORS["ink_soft"], font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")
        self.show_pass = tk.Label(pass_row, text="显示", bg=COLORS["surface"],
                                  fg=COLORS["accent"], font=("Microsoft YaHei UI", 8),
                                  cursor="hand2")
        self.show_pass.pack(side="right")
        self.show_pass.bind("<Button-1>", self._toggle_password)
        self.password_entry = styled_entry(inner, self.password_var, show="•")
        self.password_entry.pack(fill="x", ipady=6)
        tk.Label(inner, text="留空表示保留已保存的密码。", bg=COLORS["surface"],
                 fg=COLORS["faint"], font=("Microsoft YaHei UI", 8), anchor="w").pack(
            fill="x", pady=(3, 10))

        server_row = tk.Frame(inner, bg=COLORS["surface"])
        server_row.pack(fill="x")
        left = tk.Frame(server_row, bg=COLORS["surface"])
        left.pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Label(left, text="IMAP 服务器", bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(0, 3))
        styled_entry(left, self.host_var, font=("Consolas", 9)).pack(fill="x", ipady=5)
        right = tk.Frame(server_row, bg=COLORS["surface"])
        right.pack(side="left")
        tk.Label(right, text="端口", bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(0, 3))
        styled_entry(right, self.port_var, font=("Consolas", 9), width=7).pack(ipady=5)
        gap(inner, 10)

        days_row = tk.Frame(inner, bg=COLORS["surface"])
        days_row.pack(fill="x")
        tk.Label(days_row, text="同步最近", bg=COLORS["surface"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 9)).pack(side="left")
        styled_entry(days_row, self.days_var, font=("Consolas", 9), width=5).pack(
            side="left", padx=6, ipady=4)
        tk.Label(days_row, text="天的邮件（1–90）", bg=COLORS["surface"], fg=COLORS["muted"],
                 font=("Microsoft YaHei UI", 8)).pack(side="left")

        gap(inner, 12)
        tk.Label(inner, text="在钉钉邮箱网页版开启 IMAP，并生成客户端专用密码（不是登录密码）。"
                            "企业邮箱域名不同的话，填服务商提供的 IMAP 地址即可。",
                 bg=COLORS["surface_alt"], fg=COLORS["muted"],
                 font=("Microsoft YaHei UI", 8), justify="left", anchor="w",
                 wraplength=320, padx=9, pady=7).pack(fill="x")
        self.mail_message = tk.Label(inner, text="", bg=COLORS["surface"], fg=COLORS["faint"],
                                     font=("Microsoft YaHei UI", 8), anchor="w",
                                     justify="left", wraplength=330)
        self.mail_message.pack(fill="x", pady=(7, 0))
        actions = tk.Frame(inner, bg=COLORS["surface"])
        actions.pack(fill="x", pady=(9, 0))
        self.save_btn = PillButton(actions, "保存设置", self._save, kind="primary",
                                   width=84, height=34)
        self.save_btn.pack(side="left")
        self.test_btn = PillButton(actions, "测试连接", self._test, kind="ghost",
                                   width=84, height=34)
        self.test_btn.pack(side="left", padx=(6, 0))
        self.sync_btn = PillButton(actions, "立即同步", self._sync, kind="ghost",
                                   width=84, height=34)
        self.sync_btn.pack(side="left", padx=(6, 0))

        # ------------------------------------------------------------ AI mail
        card_ai, inner_ai = section_card(body)
        card_ai.pack(fill="x", pady=(0, 12))
        self.ai_card = card_ai
        ai_head = tk.Frame(inner_ai, bg=COLORS["surface"])
        ai_head.pack(fill="x", pady=(0, 2))
        tk.Label(ai_head, text="AI 邮件分析（可选）", bg=COLORS["surface"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        self.ai_status = tk.Label(ai_head, text="", bg=COLORS["surface_alt"],
                                  fg=COLORS["faint"], font=("Microsoft YaHei UI", 8),
                                  padx=7, pady=2)
        self.ai_status.pack(side="right")
        tk.Label(inner_ai, text="接入 OpenAI 兼容的 Chat Completions API。分析结果只会生成可修改的任务草稿，不会自动保存任务。",
                 bg=COLORS["surface"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 8),
                 anchor="w", justify="left", wraplength=330).pack(fill="x", pady=(0, 8))
        self.ai_enabled_toggle = self._toggle_row(
            inner_ai, "启用 AI 草稿", "打开后邮件详情会出现「AI 建任务」按钮。",
            bool(settings.get("ai_enabled", False)), self._ai_toggle_changed)
        self.ai_provider_var = tk.StringVar(
            value=settings.get("ai_provider") or _provider_from_endpoint(settings.get("ai_endpoint")))
        self._ai_key_required = False
        tk.Label(inner_ai, text="服务商", bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(6, 3))
        self.ai_provider_box = ttk.Combobox(
            inner_ai, textvariable=self.ai_provider_var, values=list(AI_PRESETS.keys()),
            state="readonly", font=("Microsoft YaHei UI", 9))
        self.ai_provider_box.pack(fill="x", ipady=2)
        self.ai_provider_box.bind("<<ComboboxSelected>>", self._apply_ai_provider)
        tk.Label(inner_ai, text="DeepSeek、智谱 GLM、通义千问均使用 OpenAI 兼容接口；也可选自定义填写。",
                 bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 7), anchor="w", justify="left",
                 wraplength=330).pack(fill="x", pady=(3, 0))
        self.ai_endpoint_var = tk.StringVar(
            value=settings.get("ai_endpoint") or "https://api.openai.com/v1/chat/completions")
        self.ai_model_var = tk.StringVar(value=settings.get("ai_model") or "gpt-4o-mini")
        self.ai_key_var = tk.StringVar(value="")
        field_label(inner_ai, "API 地址", "OpenAI 兼容 /chat/completions").pack(
            fill="x", pady=(2, 4))
        styled_entry(inner_ai, self.ai_endpoint_var, font=("Consolas", 8)).pack(
            fill="x", ipady=5)
        gap(inner_ai, 8)
        tk.Label(inner_ai, text="模型", bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(0, 3))
        styled_entry(inner_ai, self.ai_model_var, font=("Consolas", 9)).pack(
            fill="x", ipady=5)
        gap(inner_ai, 8)
        tk.Label(inner_ai, text="API Key", bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(0, 3))
        styled_entry(inner_ai, self.ai_key_var, show="•", font=("Consolas", 9)).pack(
            fill="x", ipady=5)
        tk.Label(inner_ai, text="留空表示保留已保存的 Key。启用后邮件正文会发送到该 API；敏感邮件请谨慎使用。",
                 bg=COLORS["surface_alt"], fg=COLORS["muted"],
                 font=("Microsoft YaHei UI", 8), anchor="w", justify="left",
                 wraplength=320, padx=9, pady=7).pack(fill="x", pady=(8, 0))
        ai_actions = tk.Frame(inner_ai, bg=COLORS["surface"])
        ai_actions.pack(fill="x", pady=(8, 0))
        self.ai_save_btn = PillButton(ai_actions, "保存 AI 设置", self._save_ai_clicked,
                                      kind="primary", width=90, height=32)
        self.ai_save_btn.pack(side="left")
        self.ai_test_btn = PillButton(ai_actions, "测试 AI", self._test_ai,
                                      kind="ghost", width=70, height=32)
        self.ai_test_btn.pack(side="left", padx=(6, 0))
        self.ai_message = tk.Label(inner_ai, text="", bg=COLORS["surface"],
                                   fg=COLORS["faint"], font=("Microsoft YaHei UI", 8),
                                   anchor="w", justify="left", wraplength=330)
        self.ai_message.pack(fill="x", pady=(6, 0))

        # --------------------------------------------------------- owner directory
        card_owner, inner_owner = section_card(body)
        card_owner.pack(fill="x", pady=(0, 12))
        owner_head = tk.Frame(inner_owner, bg=COLORS["surface"])
        owner_head.pack(fill="x", pady=(0, 2))
        tk.Label(owner_head, text="跟踪负责人", bg=COLORS["surface"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        self.owner_count = tk.Label(owner_head, text="", bg=COLORS["surface_alt"],
                                    fg=COLORS["faint"], font=("Microsoft YaHei UI", 7),
                                    padx=6, pady=2)
        self.owner_count.pack(side="right")
        tk.Label(inner_owner, text="配置任务负责人选择列表；已有任务里的姓名不会因为删除配置而丢失。",
                 bg=COLORS["surface"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 8),
                 anchor="w", justify="left", wraplength=330).pack(fill="x", pady=(0, 7))
        owner_search_row = tk.Frame(inner_owner, bg=COLORS["surface"])
        owner_search_row.pack(fill="x", pady=(0, 7))
        self.owner_search_var = tk.StringVar()
        styled_entry(owner_search_row, self.owner_search_var, font=("Microsoft YaHei UI", 8)).pack(
            side="left", fill="x", expand=True, ipady=4)
        PillButton(owner_search_row, "新增", self._add_owner, kind="primary",
                   width=50, height=28).pack(side="right", padx=(6, 0))
        PillButton(owner_search_row, "更新", self.app.refresh_owner_scope, kind="ghost",
                   width=50, height=28).pack(side="right", padx=(6, 0))
        self.owner_search_var.trace_add("write", lambda *_: self._render_owners())
        self.owner_list = tk.Frame(inner_owner, bg=COLORS["surface"])
        self.owner_list.pack(fill="x")
        self._render_owners()

        # -------------------------------------------------------------- window
        card2, inner2 = section_card(body)
        card2.pack(fill="x", pady=(0, 12))
        tk.Label(inner2, text="窗口与提醒", bg=COLORS["surface"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 10, "bold"), anchor="w").pack(fill="x", pady=(0, 8))
        self.topmost_toggle = self._toggle_row(
            inner2, "窗口置顶", "始终浮在其他窗口上方，方便随手查看。",
            bool(settings.get("topmost", True)), self._set_topmost)
        self.dock_toggle = self._toggle_row(
            inner2, "贴靠屏幕右侧", "下次启动时自动停靠在桌面右边缘。",
            bool(settings.get("dock_right", True)), self._set_dock)
        self.auto_toggle = self._toggle_row(
            inner2, "启动后自动同步", "打开应用后在后台读取一次邮件。",
            bool(settings.get("auto_sync", False)), self._set_auto_sync)

        # ---------------------------------------------------------------- data
        card3, inner3 = section_card(body)
        card3.pack(fill="x", pady=(0, 12))
        tk.Label(inner3, text="数据", bg=COLORS["surface"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 10, "bold"), anchor="w").pack(fill="x", pady=(0, 7))
        self.data_stats = tk.Label(inner3, text="", bg=COLORS["surface"], fg=COLORS["muted"],
                                   font=("Microsoft YaHei UI", 8), anchor="w", justify="left",
                                   wraplength=330)
        self.data_stats.pack(fill="x")
        self.data_path = tk.Label(inner3, text="", bg=COLORS["surface"], fg=COLORS["faint"],
                                  font=("Consolas", 7), anchor="w", justify="left",
                                  wraplength=330)
        self.data_path.pack(fill="x", pady=(3, 9))
        row = tk.Frame(inner3, bg=COLORS["surface"])
        row.pack(fill="x")
        PillButton(row, "导出备份", self.app.export_data, kind="ghost", width=78,
                   height=32).pack(side="left")
        PillButton(row, "导入备份", self.app.import_data, kind="ghost", width=78,
                   height=32).pack(side="left", padx=(6, 0))
        PillButton(row, "打开目录", self.app.open_data_dir, kind="ghost", width=78,
                   height=32).pack(side="left", padx=(6, 0))
        row2 = tk.Frame(inner3, bg=COLORS["surface"])
        row2.pack(fill="x", pady=(7, 0))
        PillButton(row2, "清空全部任务", self._clear_all_tasks, kind="danger", width=100,
                   height=30).pack(side="left")
        tk.Label(row2, text="任务及其子任务会删除，邮件保留", bg=COLORS["surface"],
                 fg=COLORS["faint"], font=("Microsoft YaHei UI", 8)).pack(side="left", padx=(7, 0))

        # --------------------------------------------------------------- about
        card4, inner4 = section_card(body)
        card4.pack(fill="x", pady=(0, 22))
        tk.Label(inner4, text="%s  %s" % (APP_NAME, VERSION), bg=COLORS["surface"],
                 fg=COLORS["ink"], font=("Microsoft YaHei UI", 10, "bold"), anchor="w").pack(fill="x")
        tk.Label(inner4, text="清心任务客户端：本地优先的桌面任务面板。任务、子任务、进度与负责人全部保存在本机；"
                              "邮件只读解析，不发送、不删除。",
                 bg=COLORS["surface"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 8),
                 anchor="w", justify="left", wraplength=330).pack(fill="x", pady=(4, 8))
        for line in ("· 要求、周期、开始与结束时间", "· 子任务全部完成，任务才能完成",
                     "· 负责人、进度与跟进记录", "· 钉钉邮件提取待办与更新建议"):
            tk.Label(inner4, text=line, bg=COLORS["surface"], fg=COLORS["faint"],
                     font=("Microsoft YaHei UI", 8), anchor="w").pack(fill="x", pady=1)
        tk.Label(inner4, text="Ctrl+N 新建任务   ·   左拖任务卡片删除   ·   管理可批量删除",
                 bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8), anchor="w", justify="left",
                 wraplength=330).pack(fill="x", pady=(9, 0))

    def _toggle_row(self, parent, title, description, value, command):
        row = tk.Frame(parent, bg=COLORS["surface"])
        row.pack(fill="x", pady=(3, 7))
        info = tk.Frame(row, bg=COLORS["surface"])
        info.pack(side="left", fill="x", expand=True)
        tk.Label(info, text=title, bg=COLORS["surface"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 9), anchor="w").pack(fill="x")
        tk.Label(info, text=description, bg=COLORS["surface"], fg=COLORS["faint"],
                 font=("Microsoft YaHei UI", 8), anchor="w", justify="left",
                 wraplength=280).pack(fill="x")
        toggle = Toggle(row, value=value, command=command, bg=COLORS["surface"])
        toggle.pack(side="right", padx=(8, 0))
        return toggle

    def _toggle_password(self, _event=None):
        if self.password_entry.cget("show"):
            self.password_entry.configure(show="")
            self.show_pass.configure(text="隐藏")
        else:
            self.password_entry.configure(show="•")
            self.show_pass.configure(text="显示")

    def _render_owners(self):
        if not hasattr(self, "owner_list"):
            return
        for child in list(self.owner_list.winfo_children()):
            child.destroy()
        local = self.app.store.owner_directory()
        entries = [{"owner": item, "kind": "local"} for item in local]
        local_keys = {
            (item.get("username") or "").casefold() or (item.get("name") or "").casefold()
            for item in local
        }
        for item in self.app.owner_options():
            source = item.get("source") or "local"
            if source == "local":
                continue
            key = (item.get("username") or "").casefold() or (item.get("display_name") or "").casefold()
            if key in local_keys:
                continue
            entries.append({"owner": item, "kind": source})
        synced = [entry for entry in entries if entry["kind"] != "local"]
        if hasattr(self, "owner_count"):
            self.owner_count.configure(
                text="共 %d · 本地 %d · 同步 %d" % (len(entries), len(local), len(synced)))
        query = (getattr(self, "owner_search_var", tk.StringVar()).get() or "").strip().lower()
        visible = []
        for entry in entries:
            owner = entry["owner"]
            text = ((owner.get("name") or owner.get("display_name") or "") + " " +
                    (owner.get("username") or "")).lower()
            if not query or query in text:
                visible.append(entry)
        if not visible:
            tk.Label(self.owner_list,
                     text="暂无负责人，点「更新」从管理端同步" if not entries else "没有匹配的负责人",
                     bg=COLORS["surface"], fg=COLORS["faint"],
                     font=("Microsoft YaHei UI", 8), anchor="w").pack(fill="x", pady=5)
            return
        for entry in visible:
            owner = entry["owner"]
            kind = entry["kind"]
            active = owner.get("active", True)
            row = tk.Frame(self.owner_list, bg=COLORS["surface_alt"], padx=8, pady=6)
            row.pack(fill="x", pady=(0, 4))
            tk.Label(row, text="●" if active else "○",
                     bg=COLORS["surface_alt"],
                     fg=COLORS["mint"] if active else COLORS["faint"],
                     font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(0, 5))
            info = tk.Frame(row, bg=COLORS["surface_alt"])
            info.pack(side="left", fill="x", expand=True)
            name = owner.get("name") or owner.get("display_name") or ""
            tk.Label(info, text=name, bg=COLORS["surface_alt"],
                     fg=COLORS["ink_soft"], font=("Microsoft YaHei UI", 9, "bold"),
                     anchor="w").pack(fill="x")
            if owner.get("username"):
                tk.Label(info, text="@" + owner["username"], bg=COLORS["surface_alt"],
                         fg=COLORS["faint"], font=("Microsoft YaHei UI", 7),
                         anchor="w").pack(fill="x")
            if kind == "local":
                PillButton(row, "编辑", lambda _, item=owner: self._edit_owner(item),
                           kind="ghost", width=42, height=23).pack(side="right", padx=(4, 0))
                PillButton(row, "删除", lambda _, item=owner: self._delete_owner(item),
                           kind="ghost", width=42, height=23).pack(side="right")
            else:
                label = {"self": "本人", "org": "组织同步", "friend": "好友同步"}.get(kind, "同步")
                tk.Label(row, text=label, bg=COLORS["accent_pale"], fg=COLORS["accent"],
                         font=("Microsoft YaHei UI", 7, "bold"), padx=6, pady=2).pack(side="right")

    def _add_owner(self):
        OwnerEditDialog(self.app, None, self._render_owners)

    def _edit_owner(self, owner):
        OwnerEditDialog(self.app, owner, self._render_owners)

    def _delete_owner(self, owner):
        def remove():
            self.app.store.delete_owner(owner.get("id"))
            self._render_owners()
            self.app.toast.show("负责人已从选择列表删除", "success")
        self.app.confirm(
            "删除负责人？",
            "只从负责人选择列表移除，不会修改已有任务里的姓名。",
            "删除", remove, danger=True)

    def _refresh_status(self):
        settings = self.app.store.settings()
        if settings.get("account") and self.app.store.has_password():
            self.mail_status.configure(text="已配置", bg=COLORS["mint_soft"], fg=COLORS["mint"])
        elif settings.get("account"):
            self.mail_status.configure(text="缺少密码", bg=COLORS["amber_soft"], fg=COLORS["amber"])
        else:
            self.mail_status.configure(text="未配置", bg=COLORS["surface_alt"], fg=COLORS["faint"])
        stats = self.app.store.stats()
        self.data_stats.configure(
            text="%d 个任务 · %d 封邮件 · 数据文件 %s" % (
                len(self.app.store.tasks), len(self.app.store.emails),
                self._size(stats.get("size", 0)))
        )
        self.data_path.configure(text=stats.get("path", ""))
        if self.app.syncing:
            self.sync_btn.set_disabled(True)
            self.sync_btn.set_text("同步中…")
        else:
            self.sync_btn.set_disabled(False)
            self.sync_btn.set_text("立即同步")
        self._refresh_ai_status()

    @staticmethod
    def _size(value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return "—"
        if value > 1024 * 1024:
            return "%.1f MB" % (value / 1024.0 / 1024.0)
        return "%.1f KB" % (value / 1024.0) if value >= 1024 else "%d B" % value

    def _save_ai(self, silent=False):
        endpoint = self.ai_endpoint_var.get().strip()
        ai_model = self.ai_model_var.get().strip()
        provider = self.ai_provider_var.get().strip() or "自定义"
        ai_enabled = bool(self.ai_enabled_toggle.value)
        key = self.ai_key_var.get().strip()
        if ai_enabled:
            if not endpoint.startswith(("http://", "https://")):
                self._ai_message("API 地址必须以 http:// 或 https:// 开头", "error")
                return False
            if not ai_model:
                self._ai_message("请填写 AI 模型名称", "error")
                return False
            if not key and (not self.app.store.has_ai_key() or self._ai_key_required):
                self._ai_message("请填写 API Key", "error")
                return False
        settings = self.app.store.settings()
        settings["ai_enabled"] = ai_enabled
        settings["ai_provider"] = provider
        settings["ai_endpoint"] = endpoint
        settings["ai_model"] = ai_model
        if key:
            self.app.store.set_ai_key(key)
            self.ai_key_var.set("")
            self._ai_key_required = False
        self.app.store.save()
        self._refresh_ai_status()
        if not silent:
            self._ai_message("AI 设置已保存", "success")
            self.app.toast("AI 设置已保存", "success")
        return True

    def _save_ai_clicked(self):
        self._save_ai(silent=False)

    def _apply_ai_provider(self, _event=None):
        provider = self.ai_provider_var.get()
        preset = AI_PRESETS.get(provider)
        if not preset or provider == "自定义":
            self._ai_message("自定义模式：请填写兼容 Chat Completions 的地址和模型", "info")
            return
        endpoint, model_name = preset
        self.ai_endpoint_var.set(endpoint)
        self.ai_model_var.set(model_name)
        self.ai_key_var.set("")
        self._ai_key_required = True
        self._ai_message("已填入 %s 地址和模型，请填写该服务商的 API Key 后保存" % provider,
                         "info")

    def _ai_toggle_changed(self, _value):
        self._refresh_ai_status()

    def _ai_message(self, text, kind="info"):
        color = {"success": COLORS["mint"], "error": COLORS["danger"],
                 "warn": COLORS["amber"]}.get(kind, COLORS["faint"])
        if hasattr(self, "ai_message"):
            self.ai_message.configure(text=text, fg=color)

    def _refresh_ai_status(self):
        settings = self.app.store.settings()
        configured = bool(
            (settings.get("ai_endpoint") or "").strip()
            and (settings.get("ai_model") or "").strip()
            and self.app.store.has_ai_key()
        )
        if configured and settings.get("ai_enabled"):
            text, bg, fg = "已启用", COLORS["mint_soft"], COLORS["mint"]
        elif configured:
            text, bg, fg = "已保存 · 未启用", COLORS["amber_soft"], COLORS["amber"]
        else:
            text, bg, fg = "未配置", COLORS["surface_alt"], COLORS["faint"]
        if hasattr(self, "ai_status"):
            self.ai_status.configure(text=text, bg=bg, fg=fg)

    def _test_ai(self):
        if not self._save_ai(silent=True):
            self._ai_message("请先补齐 AI 设置并保存", "error")
            return
        endpoint = self.ai_endpoint_var.get().strip()
        model_name = self.ai_model_var.get().strip()
        key = self.ai_key_var.get().strip() or self.app.store.ai_key()
        if not endpoint or not model_name or not key:
            self._ai_message("请填写 API 地址、模型和 Key", "error")
            return
        config = {"endpoint": endpoint, "model": model_name, "key": key}
        sample = {
            "subject": "AI 连接测试：请于11月20日前提交测试材料",
            "body": "这是一封测试邮件，请于11月20日18:00前提交测试材料，负责人：测试员。",
            "sender": "清心任务管理",
            "date": model.iso(model.now()),
        }
        self.ai_test_btn.set_disabled(True)
        self.ai_test_btn.set_text("测试中…")
        self._ai_message("正在请求 AI API…（最长等待 60 秒）", "info")

        def success(result):
            self.ai_test_btn.set_disabled(False)
            self.ai_test_btn.set_text("测试 AI")
            projects = result.get("projects") or []
            if projects:
                self._ai_message("API 正常，识别到 %d 个项目" % len(projects), "success")
                self.app.toast("AI API 正常：识别到 %d 个项目" % len(projects), "success")
            else:
                self._ai_message("API 已响应，但没有识别到项目", "warn")
                self.app.toast("AI API 已响应，但没有识别到项目", "warn")

        def failure(exc):
            self.ai_test_btn.set_disabled(False)
            self.ai_test_btn.set_text("测试 AI")
            self._ai_message(truncate(str(exc), 120), "error")
            self.app.toast(truncate(str(exc), 90), "error", 5200)

        self.app.run_async(
            lambda: analyzer.analyze_email_ai(
                sample, config, tasks=self.app.store.active_tasks(),
                previous_emails=self.app.store.emails, timeout=60),
            success, failure)

    def _collect(self):
        account = self.account_var.get().strip()
        host = self.host_var.get().strip()
        try:
            port = int(self.port_var.get().strip())
            days = int(self.days_var.get().strip())
        except ValueError:
            self._mail_error("端口和同步天数必须是数字")
            return False
        if account and not host:
            self._mail_error("请填写 IMAP 服务器地址")
            return False
        if not (1 <= port <= 65535):
            self._mail_error("端口应在 1–65535 之间")
            return False
        if not (1 <= days <= 90):
            self._mail_error("同步天数应在 1–90 之间")
            return False
        settings = self.app.store.settings()
        settings["account"] = account
        settings["imap_host"] = host
        settings["imap_port"] = port
        settings["days"] = days
        if not self._save_ai(silent=True):
            return False
        password = self.password_var.get()
        if password:
            self.app.store.set_password(password)
            self.password_var.set("")
        self.app.store.save()
        self._mail_message("设置已保存", "success")
        self._refresh_status()
        return True

    def _mail_message(self, text, kind="info"):
        color = {"success": COLORS["mint"], "error": COLORS["danger"],
                 "warn": COLORS["amber"]}.get(kind, COLORS["faint"])
        self.mail_message.configure(text=text, fg=color)

    def _mail_error(self, text):
        self._mail_message(text, "error")
        self.app.toast(text, "error")

    def _save(self):
        self._collect()

    def _test(self):
        if not self._collect():
            return
        if not self.app.store.has_password():
            self._mail_error("请先填写邮箱专用密码")
            return
        self.test_btn.set_disabled(True)
        self._mail_message("正在连接邮箱…", "info")
        self.app.test_mail(self.test_btn, self._mail_message)

    def _sync(self):
        if not self._collect():
            return
        self.app.sync_mail()

    def _set_topmost(self, value):
        self.app.store.set_setting("topmost", bool(value))
        self.app.set_pin(bool(value))

    def _set_dock(self, value):
        self.app.store.set_setting("dock_right", bool(value))

    def _set_auto_sync(self, value):
        self.app.store.set_setting("auto_sync", bool(value))

    def _clear_all_tasks(self):
        self.app.pages["tasks"].clear_all()
# -*- coding: utf-8 -*-
"""追加：负责人配置弹窗。"""
import tkinter as tk

from .constants import COLORS
from .ui_common import Modal, field_label, gap, styled_entry
from .widgets import PillButton, Toggle


class OwnerEditDialog(Modal):
    def __init__(self, app, owner=None, on_saved=None):
        self.app = app
        self.owner = owner
        self.on_saved = on_saved
        self.name_var = tk.StringVar(value=(owner or {}).get("name") or "")
        self.username_var = tk.StringVar(value=(owner or {}).get("username") or "")
        self.active_var = bool((owner or {}).get("active", True))
        Modal.__init__(self, app, "编辑跟踪负责人" if owner else "新增跟踪负责人",
                       "负责人会出现在任务和子任务的选择列表中")
        self._build()

    def _build(self):
        body = self.content
        field_label(body, "姓名", "必填，例如：林夏").pack(fill="x", pady=(0, 5))
        styled_entry(body, self.name_var, font=("Microsoft YaHei UI", 10)).pack(
            fill="x", ipady=6)
        gap(body, 12)
        field_label(body, "账号", "可选，例如：linxia").pack(fill="x", pady=(0, 5))
        styled_entry(body, self.username_var, font=("Microsoft YaHei UI", 10)).pack(
            fill="x", ipady=6)
        gap(body, 12)
        row = tk.Frame(body, bg=COLORS["surface"], padx=12, pady=10,
                       highlightthickness=1, highlightbackground=COLORS["line"])
        row.pack(fill="x")
        info = tk.Frame(row, bg=COLORS["surface"])
        info.pack(side="left", fill="x", expand=True)
        tk.Label(info, text="启用", bg=COLORS["surface"], fg=COLORS["ink_soft"],
                 font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x")
        tk.Label(info, text="关闭后不出现在新的负责人选择列表里。", bg=COLORS["surface"],
                 fg=COLORS["faint"], font=("Microsoft YaHei UI", 7),
                 anchor="w").pack(fill="x", pady=(2, 0))
        self.active_toggle = Toggle(row, self.active_var, bg=COLORS["surface"])
        self.active_toggle.pack(side="right", padx=(8, 0))
        self.error = tk.Label(body, text="", bg=COLORS["bg"], fg=COLORS["danger"],
                              font=("Microsoft YaHei UI", 8), anchor="w")
        self.error.pack(fill="x", pady=(9, 0))
        PillButton(self.footer_left, "取消", self.force_close, kind="ghost",
                   width=58, height=32).pack(side="left", padx=16)
        PillButton(self.footer_right, "保存", self._save, kind="primary",
                   width=76, height=34).pack(side="right", padx=16)

    def _save(self):
        name = self.name_var.get().strip()
        username = self.username_var.get().strip()
        try:
            if self.owner:
                self.app.store.update_owner(self.owner.get("id"), name, username,
                                            self.active_toggle.value)
            else:
                self.app.store.add_owner(name, username, self.active_toggle.value)
        except ValueError as exc:
            self.error.configure(text=str(exc))
            return
        if self.on_saved:
            self.on_saved()
        self.app.toast.show("负责人已保存", "success")
        self.force_close()

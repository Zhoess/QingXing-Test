(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const state = {
    token: localStorage.getItem("taskdock_admin_token") || "",
    user: null,
    data: null,
    page: "overview",
    editingId: null,
    orgEditingId: null,
    orgParent: null,
    taskKey: null,
    taskTags: [],
    chatTask: null,
    chatReadOnly: false,
    chatTimer: null,
    messageThreads: [],
    polling: false,
    dataKey: null,
    insightFilter: "all",
    insightIssue: null,
  };

  const PAGE_META = {
    overview: ["GLOBAL OVERVIEW", "全局总览"],
    accounts: ["ACCOUNTS", "账户与终端"],
    tasks: ["ALL TASKS", "全局任务池"],
    messages: ["MESSAGES", "消息中心"],
    insights: ["ANALYSIS", "管理洞察"],
    org: ["ORGANIZATION", "组织架构"],
  };

  const esc = (value) => String(value === undefined || value === null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  function toast(message, kind = "") {
    const el = $("toast");
    el.textContent = message;
    el.className = "toast show " + kind;
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => { el.className = "toast"; }, 2800);
  }

  async function api(path, options = {}) {
    const headers = Object.assign({}, options.headers || {});
    if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    if (state.token) headers["Authorization"] = "Bearer " + state.token;
    const response = await fetch(path, Object.assign({}, options, { headers }));
    let payload = {};
    try { payload = await response.json(); } catch (_) { payload = {}; }
    if (!response.ok) {
      if (response.status === 401) {
        clearSession();
        showGate("login");
      }
      throw new Error(payload.error || "请求失败");
    }
    return payload;
  }

  function clearSession() {
    state.token = "";
    state.user = null;
    state.data = null;
    localStorage.removeItem("taskdock_admin_token");
    $("app").classList.add("hidden");
  }

  function showGate(panel) {
    $("gate").classList.remove("hidden");
    $("app").classList.add("hidden");
    $("gateLoading").classList.add("hidden");
    $("setupPanel").classList.add("hidden");
    $("loginPanel").classList.add("hidden");
    $(panel === "setup" ? "setupPanel" : "loginPanel").classList.remove("hidden");
  }

  function showApp(user) {
    state.user = user;
    $("gate").classList.add("hidden");
    $("app").classList.remove("hidden");
    $("adminName").textContent = user.display_name || user.username;
    $("adminUser").textContent = "@" + user.username;
    $("adminAvatar").textContent = (user.display_name || user.username || "A").slice(0, 1).toUpperCase();
    switchPage("overview");
    loadData();
    clearInterval(showApp._timer);
    showApp._timer = setInterval(() => {
      if (document.hidden) return;
      if (!$("app").classList.contains("hidden")) loadData(true);
    }, 5000);
  }

  async function init() {
    try {
      const status = await api("/api/status");
      if (status.setup_required) {
        showGate("setup");
        if (!["127.0.0.1", "localhost", "::1"].includes(location.hostname)) {
          $("setupError").textContent = "首次初始化请在清心任务管理终端所在的电脑上，用 127.0.0.1 打开本页。";
        }
        return;
      }
      if (!state.token) {
        showGate("login");
        return;
      }
      const me = await api("/api/me");
      if (me.user.role !== "admin") {
        clearSession();
        showGate("login");
        $("loginError").textContent = "该账号不是管理账号，请在清心任务客户端登录。";
        return;
      }
      showApp(me.user);
    } catch (error) {
      showGate("login");
      $("loginError").textContent = error.message;
    }
  }

  async function collectTasks() {
    const button = $("collectBtn");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "通知中…";
    try {
      const result = await api("/api/admin/collect", {
        method: "POST",
        body: JSON.stringify({}),
      });
      toast("已通知 " + (result.online || 0) + " 个在线客户端，正在收取任务", "good");
      [2500, 6000, 12000].forEach((delay) => setTimeout(() => loadData(true), delay));
    } catch (error) {
      toast(error.message, "error");
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function loadData(silent = false) {
    if (state.polling) return;
    state.polling = true;
    try {
      const data = await api("/api/admin/overview");
      const nextKey = JSON.stringify({ ...data, generated_at: null });
      const changed = nextKey !== state.dataKey;
      state.data = data;
      state.dataKey = nextKey;
      if (changed || !silent) {
        renderAll();
      } else {
        const generated = data.generated_at ? new Date(data.generated_at) : new Date();
        $("generatedAt").textContent = "更新于 " + generated.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
      }
      if (!silent) toast("数据已刷新", "good");
    } catch (error) {
      if (error.message) toast(error.message, "error");
    } finally {
      state.polling = false;
    }
  }

  function renderAll() {
    if (!state.data) return;
    renderStats();
    renderInsights();
    renderWorkload();
    renderRecentTasks();
    renderAccounts();
    renderOrg();
    renderTasks();
    loadMessageThreads();
    const generated = state.data.generated_at ? new Date(state.data.generated_at) : new Date();
    $("generatedAt").textContent = "更新于 " + generated.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
    $("sideVersion").textContent = "v2.0 · " + (state.data.stats.users || 0) + " 账户";
  }

  function renderStats() {
    const s = state.data.stats || {};
    const cards = [
      ["账户总数", s.users || 0, "活跃 " + (s.active_users || 0) + " 个 · 在线 " + (s.online || 0) + " 个", "", true],
      ["任务总数", s.tasks || 0, "共享 " + (s.shared || 0) + " 个", "accent"],
      ["完成率", (s.completion || 0) + "%", "已完成 " + (s.completed || 0) + " 个", ""],
      ["已流失", s.lost || 0, "流失终态", s.lost ? "lost" : ""],
      ["已逾期", s.overdue || 0, "需要优先处理", s.overdue ? "accent" : ""],
      ["3 天内到期", s.due_soon || 0, "临近截止", ""],
      ["待处理邀请", s.pending_offers || 0, "好友/任务邀请", ""],
    ];
    $("statGrid").innerHTML = cards.map(([label, value, note, cls, dark]) => `
      <div class="stat-card ${cls || ""} ${dark ? "dark" : ""}">
        <div class="stat-label"><span>${esc(label)}</span><span>${dark ? "●" : "·"}</span></div>
        <div class="stat-value">${esc(value)}</div>
        <div class="stat-note">${esc(note)}</div>
      </div>`).join("");
  }

  function insightHtml(item, index) {
    return `<div class="insight ${esc(item.tone || "")}">
      <b>${index !== undefined ? String(index + 1).padStart(2, "0") + " · " : ""}${esc(item.title)}</b>
      <p>${esc(item.detail)}</p>
    </div>`;
  }

  const INSIGHT_FILTERS = [
    ["all", "全部问题"], ["lost", "流失"], ["warning", "预警"],
    ["overdue", "逾期"], ["due_soon", "临期"], ["stalled", "停滞"],
    ["unassigned", "待指派"], ["follow", "跟进"],
  ];

  const INSIGHT_GROUPS = [
    ["lost", "流失", "已标记流失，优先级最高。", "danger"],
    ["overdue", "已逾期", "截止时间已过但任务仍未完成。", "danger"],
    ["warning", "预警", "已标记预警，需要重点关注。", "warn"],
    ["due_soon", "3 天内到期", "临近截止但仍未完成。", "warn"],
    ["stalled", "停滞", "超过 7 天没有更新。", "warn"],
    ["unassigned", "待指派", "未完成但没有明确负责人。", "accent"],
    ["follow", "跟进", "已标记跟进，需要持续推动。", "accent"],
    ["no_due", "没有截止时间", "未完成但未设置截止时间，容易遗漏。", "warn"],
    ["zero_progress", "已开始但 0% 进度", "开始超过 3 天，进度仍为 0%。", "warn"],
    ["long_running", "运行超过 30 天", "长期未完成，检查目标和截止时间。", "accent"],
    ["multi_owner", "多负责人写法", "负责人不是单一账号，无法直接定向沟通。", "accent"],
    ["stale14", "超过 14 天未更新", "长时间没有推进记录。", "warn"],
  ];

  function insightDays(value) {
    if (!value) return null;
    const date = new Date(String(value).replace(" ", "T"));
    if (Number.isNaN(date.getTime())) return null;
    return (Date.now() - date.getTime()) / 86400000;
  }

  function taskReasons(task) {
    const reasons = [];
    const tags = task.tags || [];
    const due = task.due ? new Date(String(task.due).replace(" ", "T")) : null;
    const now = new Date();
    const updatedDays = insightDays(task.updated_at || task.created_at);
    if (tags.includes("lost")) reasons.push({ key: "lost", label: "流失", tone: "danger", weight: 100 });
    if (tags.includes("warning")) reasons.push({ key: "warning", label: "预警", tone: "warn", weight: 70 });
    if (tags.includes("follow")) reasons.push({ key: "follow", label: "跟进", tone: "accent", weight: 25 });
    if (due && !task.completed && due < now) {
      reasons.push({ key: "overdue", label: "已逾期", tone: "danger", weight: 90 });
    } else if (due && !task.completed && due - now <= 3 * 86400000) {
      reasons.push({ key: "due_soon", label: "3 天内到期", tone: "warn", weight: 55 });
    }
    if (!task.completed && updatedDays !== null && updatedDays > 7) {
      reasons.push({ key: "stalled", label: "停滞 " + Math.floor(updatedDays) + " 天", tone: "warn", weight: 60 });
    }
    if (!task.completed && (!task.owner || task.owner === "待指派")) {
      reasons.push({ key: "unassigned", label: "待指派", tone: "accent", weight: 45 });
    }
    if (!task.completed && !task.due) {
      reasons.push({ key: "no_due", label: "无截止", tone: "warn", weight: 20 });
    }
    if (!task.completed && Number(task.progress || 0) === 0) {
      const startDays = insightDays(task.start);
      if (startDays !== null && startDays > 3) {
        reasons.push({ key: "zero_progress", label: "0% 进度", tone: "warn", weight: 35 });
      }
    }
    if (!task.completed) {
      const startDays = insightDays(task.start);
      if (startDays !== null && startDays > 30) {
        reasons.push({ key: "long_running", label: "超 30 天", tone: "accent", weight: 30 });
      }
    }
    if (/[、,，/;；]/.test(task.owner || "")) {
      reasons.push({ key: "multi_owner", label: "多人负责", tone: "accent", weight: 20 });
    }
    if (!task.completed && updatedDays !== null && updatedDays > 14) {
      reasons.push({ key: "stale14", label: "超 14 天未更新", tone: "warn", weight: 40 });
    }
    return reasons;
  }

  function activeTaskList() {
    return (state.data.tasks || []).filter((task) => !task.archived);
  }

  function insightScore(task) {
    return Math.max(0, ...taskReasons(task).map((reason) => reason.weight));
  }

  function showTaskFromInsight(taskId) {
    const task = (state.data.tasks || []).find((item) => String(item.id) === String(taskId));
    if (task) openTaskDetail({ dataset: { user: String(task.user_id), task: String(task.id) } });
  }

  function chatTaskFromInsight(taskId) {
    const task = (state.data.tasks || []).find((item) => String(item.id) === String(taskId));
    if (!task) return;
    openChat({ dataset: { user: String(task.user_id), task: String(task.id) } });
  }

  function renderInsightKpis(tasks) {
    const reasonList = tasks.map(taskReasons);
    const count = (key) => reasonList.filter((reasons, index) =>
      !tasks[index].completed && reasons.some((reason) => reason.key === key)).length;
    const overdue = count("overdue");
    const lost = count("lost");
    const stalled = count("stalled");
    const unassigned = count("unassigned");
    const active = tasks.filter((task) => !task.completed).length;
    const cards = [
      ["项目总数", tasks.length, "未归档", "mint"],
      ["进行中", active, "未完成", "accent"],
      ["已逾期", overdue, "需要立即处理", overdue ? "danger" : ""],
      ["流失风险", lost, "流失标签", lost ? "danger" : ""],
      ["停滞", stalled, "超过 7 天未更新", stalled ? "warn" : ""],
      ["待指派", unassigned, "没有负责人", unassigned ? "warn" : ""],
    ];
    $("insightKpis").innerHTML = cards.map(([label, value, detail, tone]) =>
      `<div class="ops-kpi ${tone}"><div class="label">${label}</div><div class="value">${value}</div><div class="detail">${detail}</div></div>`).join("");
  }

  function renderInsightProblems(tasks) {
    const all = tasks.map((task) => ({ task, reasons: taskReasons(task) }))
      .filter((row) => row.reasons.length && !row.task.completed);
    const counts = {};
    all.forEach((row) => row.reasons.forEach((reason) => {
      counts[reason.key] = (counts[reason.key] || 0) + 1;
    }));
    $("insightFilters").innerHTML = INSIGHT_FILTERS.map(([key, label]) =>
      `<button type="button" class="${!state.insightIssue && state.insightFilter === key ? "on" : ""}" data-insight-filter="${key}">${label}${key !== "all" && counts[key] ? " " + counts[key] : ""}</button>`).join("");
    let filtered = all;
    let context = "";
    if (state.insightIssue) {
      const group = INSIGHT_GROUPS.find(([key]) => key === state.insightIssue);
      filtered = all.filter((row) => row.reasons.some((reason) => reason.key === state.insightIssue));
      context = group ? group[1] : state.insightIssue;
    } else if (state.insightFilter !== "all") {
      filtered = all.filter((row) => row.reasons.some((reason) => reason.key === state.insightFilter));
    }
    filtered = filtered.sort((a, b) =>
      Math.max(...b.reasons.map((r) => r.weight)) - Math.max(...a.reasons.map((r) => r.weight)));
    $("insightProblemCount").textContent = context
      ? "专项 · " + context + " · " + filtered.length + " 个"
      : "共 " + filtered.length + " 个项目";
    const banner = context ? `<div class="issue-context"><span>正在查看：<b>${esc(context)}</b></span><button type="button" class="link-btn" data-insight-clear="1">清除专项</button></div>` : "";
    $("insightProblems").innerHTML = banner + (filtered.map(({ task, reasons }) => {
      const tone = reasons.some((r) => r.tone === "danger") ? "danger" : (
        reasons.some((r) => r.tone === "warn") ? "warn" : "accent");
      return `<div class="ops-item ${tone}">
        <div class="ops-item-head"><b>${esc(task.title)}</b><span class="muted">${esc(task.owner || "待指派")}</span>
          <button class="link-btn" type="button" data-insight-chat="${esc(task.id)}">沟通</button>
          <button class="link-btn" type="button" data-insight-task="${esc(task.id)}">查看</button></div>
        <div class="ops-item-meta">
          ${reasons.map((reason) => `<span class="reason ${reason.tone}">${esc(reason.label)}</span>`).join("")}
          <span>${task.progress || 0}%</span><span>截止 ${fmtDate(task.due)}</span>
        </div>
      </div>`;
    }).join("") || `<div class="ops-empty">当前筛选下没有项目。</div>`);
  }

  function renderInsightIssues(tasks) {
    const rows = tasks.map((task) => ({ task, reasons: taskReasons(task) }))
      .filter((row) => !row.task.completed);
    const groups = INSIGHT_GROUPS.map(([key, label, detail, tone], order) => {
      const matched = rows.filter((row) => row.reasons.some((reason) => reason.key === key))
        .map((row) => row.task);
      return { key, label, detail, tone, matched, order };
    }).filter((group) => group.matched.length > 0)
      .sort((a, b) => b.matched.length - a.matched.length || a.order - b.order);
    if (state.insightIssue && !groups.some((group) => group.key === state.insightIssue)) {
      state.insightIssue = null;
      renderInsightProblems(tasks);
    }
    $("insightIssues").innerHTML = groups.map((group) => `<details class="issue-group ${group.tone}" data-issue="${group.key}" ${state.insightIssue === group.key ? "open" : ""}>
      <summary><span>${esc(group.label)}</span><b>${group.matched.length}</b></summary>
      <p>${esc(group.detail)}</p>
      <div class="issue-children">
        ${group.matched.map((task) => `<button type="button" data-insight-task="${esc(task.id)}"><span>${esc(task.title)}</span><em>${esc(task.owner || "待指派")}</em></button>`).join("")}
      </div>
    </details>`).join("") || `<div class="ops-empty">当前没有需要提示的问题。</div>`;
  }

  function renderInsightProjects(tasks) {
    const rows = tasks.filter((task) => !task.completed)
      .sort((a, b) => insightScore(b) - insightScore(a)
        || (new Date(a.due || "2999-01-01") - new Date(b.due || "2999-01-01")));
    $("insightProjectCount").textContent = "进行中 " + rows.length + " 个 · 按风险排序";
    $("insightProjects").innerHTML = rows.slice(0, 12).map((task) => {
      const reasons = taskReasons(task).slice(0, 3);
      return `<div class="ops-project">
        <div class="title"><b>${esc(task.title)}</b><span>${esc(task.owner || "待指派")} · ${esc(task.cycle || "一次性")}</span></div>
        <div><span class="bar"><i style="width:${Math.max(0, Math.min(100, task.progress || 0))}%"></i></span> <span>${task.progress || 0}%</span></div>
        <div class="risk">${reasons.map((reason) => `<span class="reason ${reason.tone}">${esc(reason.label)}</span>`).join("") || "—"}</div>
        <span class="due">${esc(fmtDate(task.due))}</span>
        <button class="link-btn" type="button" data-insight-task="${esc(task.id)}">详情</button>
      </div>`;
    }).join("") || `<div class="ops-empty">还没有进行中的项目。</div>`;
  }

  function renderInsights() {
    const insights = state.data.insights || [];
    if ($("insightList")) {
      $("insightList").innerHTML = insights.slice(0, 3).map((item, i) => insightHtml(item, i)).join("");
    }
    if (!$("insightKpis")) return;
    const tasks = activeTaskList();
    renderInsightKpis(tasks);
    renderInsightProblems(tasks);
    renderInsightIssues(tasks);
    renderInsightProjects(tasks);
    const generated = state.data.generated_at ? new Date(state.data.generated_at) : new Date();
    $("insightUpdated").textContent = "数据更新于 " + generated.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  }

  function workloadHtml(target) {
    const items = state.data.workload || [];
    const max = Math.max(1, ...items.map((item) => item.count));
    if (!items.length) return `<div class="empty">还没有未完成任务。</div>`;
    target.innerHTML = items.map((item) => `
      <div class="workload-row">
        <span>${esc(item.name)}</span>
        <div class="bar"><i style="width:${Math.max(4, Math.round(item.count / max * 100))}%"></i></div>
        <b>${item.count}</b>
      </div>`).join("");
  }

  function renderWorkload() {
    workloadHtml($("workloadList"));
    workloadHtml($("insightWorkload"));
  }

  function taskStatus(task) {
    if (task.archived) return ["已归档", "archived"];
    if (task.lost) return ["已流失", "lost"];
    if (task.completed) return ["已完成", "done"];
    if (task.due) {
      const diff = new Date(task.due) - new Date();
      if (diff < 0) return ["已逾期", "overdue"];
      if (diff < 3 * 86400000) return ["临期", "overdue"];
    }
    if (task.source && task.source !== "local") return ["共享中", "shared"];
    return ["进行中", "open"];
  }

  function sourceLabel(source) {
    return { local: "本地", shared: "共享", transferred: "转交" }[source] || source || "本地";
  }

  function fmtDate(value) {
    if (!value) return "未设";
    const date = new Date(value);
    if (isNaN(date.getTime())) return esc(value);
    return date.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }

  function taskRow(task, withOwner = true) {
    const [label, cls] = taskStatus(task);
    return `<tr>
      <td><span class="task-title">${esc(task.title)}</span><span class="sub">${esc(task.requirement || "")}</span></td>
      <td>${withOwner ? `<span class="avatar">${esc((task.display_name || task.username || "?").slice(0, 1))}</span>${esc(task.display_name || task.username || "")}<span class="sub">@${esc(task.username || "")}</span>` : esc(task.owner || "待指派")}</td>
      ${withOwner ? `<td>${esc(task.owner || "待指派")}${task.owner_username ? `<span class="sub">@${esc(task.owner_username)}</span>` : ""}</td>` : ""}
      <td>${esc(task.cycle || "一次性")}</td>
      <td>${fmtDate(task.due)}</td>
      <td><div class="progress"><div class="track"><i style="width:${Math.max(0, Math.min(100, task.progress || 0))}%"></i></div><span>${task.progress || 0}%</span></div></td>
      <td><span class="pill ${cls}">${label}</span></td>
      <td><span class="pill ${task.source && task.source !== "local" ? "shared" : "archived"}">${esc(sourceLabel(task.source))}</span></td>
    </tr>`;
  }

  function renderRecentTasks() {
    const tasks = (state.data.tasks || []).filter((task) => !task.archived).slice(0, 7);
    $("recentTasks").innerHTML = tasks.length
      ? tasks.map((task) => {
          const [label, cls] = taskStatus(task);
          return `<tr>
            <td><span class="task-title">${esc(task.title)}</span><span class="sub">${esc(task.requirement || "")}</span></td>
            <td>${esc(task.display_name || task.username)}</td>
            <td>${fmtDate(task.due)}</td>
            <td><div class="progress"><div class="track"><i style="width:${task.progress || 0}%"></i></div><span>${task.progress || 0}%</span></div></td>
            <td><span class="pill ${cls}">${label}</span></td>
          </tr>`;
        }).join("")
      : `<tr><td colspan="5"><div class="empty">还没有同步上来的任务。</div></td></tr>`;
  }

  function orgLabelMap() {
    const units = state.data.org_units || [];
    const byParent = {};
    units.forEach((unit) => {
      const key = unit.parent_id || 0;
      (byParent[key] = byParent[key] || []).push(unit);
    });
    const labels = {};
    const walk = (parent, depth) => {
      (byParent[parent] || []).forEach((unit) => {
        labels[unit.id] = "— ".repeat(depth) + unit.name;
        walk(unit.id, depth + 1);
      });
    };
    walk(0, 0);
    units.forEach((unit) => { if (!(unit.id in labels)) labels[unit.id] = unit.name; });
    return labels;
  }

  function fillOrgSelects() {
    const labels = orgLabelMap();
    const options = Object.entries(labels)
      .map(([id, label]) => `<option value="${id}">${esc(label)}</option>`).join("");
    const fill = (id, blank) => {
      const select = $(id);
      if (!select) return;
      const current = select.value;
      select.innerHTML = `<option value="">${blank}</option>` + options;
      if (current && labels[current]) select.value = current;
    };
    fill("newOrg", "未分配");
    fill("editOrg", "未分配");
    fill("orgParent", "无（一级组织）");
  }

  function renderOrg() {
    const units = (state.data.org_units || []).slice();
    const users = (state.data.users || []).slice();
    const byParent = {};
    const membersByOrg = {};
    units.forEach((unit) => {
      const key = unit.parent_id || 0;
      (byParent[key] = byParent[key] || []).push(unit);
    });
    users.forEach((user) => {
      const key = user.org_unit_id || 0;
      (membersByOrg[key] = membersByOrg[key] || []).push(user);
    });
    const memberHtml = (members, depth) => {
      if (!members.length) {
        return `<div class="org-members empty-members" style="padding-left:${depth * 24 + 30}px">暂无账号</div>`;
      }
      return members.map((user) => `<div class="org-member" style="padding-left:${depth * 24 + 30}px">
        <span class="avatar">${esc((user.display_name || user.username || "?").slice(0, 1))}</span>
        <b>${esc(user.display_name || user.username)}</b>
        <span class="sub">@${esc(user.username)}</span>
        <span class="pill ${user.status === "active" ? "active" : "disabled"}">${user.status === "active" ? "正常" : "已停用"}</span>
      </div>`).join("");
    };
    const rows = [];
    const walk = (parent, depth) => {
      (byParent[parent] || []).forEach((unit) => {
        rows.push(`<div class="org-row" style="padding-left:${depth * 24 + 10}px">
          <div><b>${esc(unit.name)}</b><span class="sub">${unit.member_count || 0} 人</span></div>
          <div>
            <button class="btn small ghost" data-org-action="child" data-id="${unit.id}">加下级</button>
            <button class="btn small" data-org-action="edit" data-id="${unit.id}">改名</button>
            <button class="btn small danger-text" data-org-action="delete" data-id="${unit.id}">删除</button>
          </div>
        </div>`);
        rows.push(memberHtml(membersByOrg[unit.id] || [], depth));
        walk(unit.id, depth + 1);
      });
    };
    walk(0, 0);
    const unassigned = membersByOrg[0] || [];
    if (unassigned.length) {
      rows.push(`<div class="org-row unassigned-row"><div><b>未分配组织</b><span class="sub">${unassigned.length} 人</span></div></div>`);
      rows.push(memberHtml(unassigned, 0));
    }
    $("orgCount").textContent = units.length + " 个组织 · " + users.length + " 个账号";
    $("orgTree").innerHTML = rows.join("") || `<div class="empty">还没有组织，先新增一级组织。</div>`;
    fillOrgSelects();
  }

  function openOrgModal(unit = null, parentId = null) {
    state.orgEditingId = unit ? unit.id : null;
    state.orgParent = parentId;
    $("orgModalTitle").textContent = unit ? "编辑组织" : "新增组织";
    $("orgName").value = unit ? unit.name : "";
    fillOrgSelects();
    $("orgParent").value = unit ? (unit.parent_id || "") : (parentId || "");
    $("orgError").textContent = "";
    $("orgModal").classList.remove("hidden");
    setTimeout(() => $("orgName").focus(), 30);
  }

  function closeOrgModal() {
    state.orgEditingId = null;
    state.orgParent = null;
    $("orgModal").classList.add("hidden");
  }

  async function saveOrg() {
    const name = $("orgName").value.trim();
    if (!name) {
      $("orgError").textContent = "请填写组织名称";
      return;
    }
    const parent_id = $("orgParent").value || null;
    try {
      if (state.orgEditingId) {
        await api("/api/admin/org/update", {
          method: "POST",
          body: JSON.stringify({ id: state.orgEditingId, name, parent_id }),
        });
      } else {
        await api("/api/admin/org/create", {
          method: "POST",
          body: JSON.stringify({ name, parent_id }),
        });
      }
      closeOrgModal();
      toast("组织已保存", "good");
      await loadData(true);
    } catch (error) {
      $("orgError").textContent = error.message;
    }
  }

  async function orgAction(button) {
    const action = button.dataset.orgAction;
    const id = Number(button.dataset.id);
    const unit = (state.data.org_units || []).find((item) => item.id === id);
    if (!unit) return;
    if (action === "child") openOrgModal(null, id);
    else if (action === "edit") openOrgModal(unit);
    else if (action === "delete") {
      if (!confirm(`删除组织「${unit.name}」？需先清空下级组织和成员。`)) return;
      try {
        await api("/api/admin/org/delete", {
          method: "POST",
          body: JSON.stringify({ id }),
        });
        toast("组织已删除", "good");
        await loadData(true);
      } catch (error) { toast(error.message, "error"); }
    }
  }

  function renderAccounts() {
    const query = ($("accountSearch").value || "").toLowerCase();
    const users = (state.data.users || []).filter((user) =>
      !query || (user.username + " " + user.display_name + " " + (user.org_unit_name || "")).toLowerCase().includes(query));
    $("accountRows").innerHTML = users.length ? users.map((user) => {
      const me = state.user && state.user.id === user.id;
      return `<tr>
        <td><span class="avatar">${esc((user.display_name || user.username).slice(0, 1))}</span><b>${esc(user.display_name)}</b><span class="sub">@${esc(user.username)}</span></td>
        <td>${user.role === "admin" ? "管理端" : "清心任务客户端"}</td>
        <td>${esc(user.org_unit_name || "未分配")}</td>
        <td><span class="pill ${user.status === "active" ? "active" : "disabled"}">${user.status === "active" ? "正常" : "已停用"}</span></td>
        <td>${user.open_tasks || 0}</td>
        <td>${user.completed_tasks || 0}</td>
        <td>${user.last_seen_at ? fmtDate(user.last_seen_at) : "从未登录"}</td>
        <td>
          ${me ? `
            <button class="btn small" data-action="edit" data-id="${user.id}" data-username="${esc(user.username)}" data-display="${esc(user.display_name)}" data-org="${user.org_unit_id || ""}">修改</button>
            <span class="muted">当前账号</span>` : `
            <button class="btn small" data-action="edit" data-id="${user.id}" data-username="${esc(user.username)}" data-display="${esc(user.display_name)}" data-org="${user.org_unit_id || ""}">修改</button>
            <button class="btn small" data-action="status" data-id="${user.id}" data-status="${user.status === "active" ? "disabled" : "active"}">${user.status === "active" ? "停用" : "启用"}</button>
            <button class="btn small" data-action="password" data-id="${user.id}">重置密码</button>
            ${user.role !== "admin" ? `<button class="btn small danger-text" data-action="delete" data-id="${user.id}" data-username="${esc(user.username)}">删除</button>` : ""}`}
        </td>
      </tr>`;
    }).join("") : `<tr><td colspan="8"><div class="empty">没有匹配的账户。</div></td></tr>`;
  }

  function fillUserFilter() {
    const select = $("taskUser");
    const current = select.value;
    const orgOptions = (state.data.org_units || [])
      .map((unit) => `<option value="org:${unit.id}">组织：${esc(unit.name)}</option>`).join("");
    const userOptions = (state.data.users || [])
      .filter((user) => user.role !== "admin" || user.id === state.user.id)
      .map((user) => `<option value="${user.id}">${esc(user.display_name)}（@${esc(user.username)}）</option>`).join("");
    select.innerHTML = `<option value="">全部成员</option>` + orgOptions + userOptions;
    select.value = current;
  }

  function taskDueDate(task) {
    if (!task.due) return null;
    const value = new Date(String(task.due).replace(" ", "T"));
    return Number.isNaN(value.getTime()) ? null : value;
  }

  function renderTasks() {
    fillUserFilter();
    const query = ($("taskSearch").value || "").toLowerCase();
    const status = $("taskStatus").value;
    const userFilter = $("taskUser").value;
    const ownerQuery = ($("taskOwner").value || "").toLowerCase();
    const cycle = $("taskCycle").value;
    const progressFilter = $("taskProgress").value;
    const sourceFilter = $("taskSource").value;
    const tag = $("taskTag").value;
    const dueFilter = $("taskDue").value;
    const sort = $("taskSort").value;
    let tasks = (state.data.tasks || []).slice();
    tasks = status === "archived"
      ? tasks.filter((task) => task.archived)
      : tasks.filter((task) => !task.archived);
    if (userFilter.startsWith("org:")) {
      const orgId = userFilter.slice(4);
      tasks = tasks.filter((task) => {
        const owner = (state.data.users || []).find((item) => String(item.id) === String(task.user_id));
        return owner && String(owner.org_unit_id) === String(orgId);
      });
    } else if (userFilter) {
      tasks = tasks.filter((task) => String(task.user_id) === String(userFilter));
    }
    if (ownerQuery) tasks = tasks.filter((task) =>
      String(task.owner || "").toLowerCase().includes(ownerQuery)
      || String(task.owner_username || "").toLowerCase().includes(ownerQuery));
    if (cycle) tasks = tasks.filter((task) => (task.cycle || "一次性") === cycle);
    if (progressFilter === "0") tasks = tasks.filter((task) => Number(task.progress || 0) === 0);
    else if (progressFilter === "100") tasks = tasks.filter((task) => Number(task.progress || 0) >= 100 || task.completed);
    else if (progressFilter === "running") tasks = tasks.filter((task) => Number(task.progress || 0) > 0 && Number(task.progress || 0) < 100);
    if (sourceFilter) tasks = tasks.filter((task) => (task.source || "local") === sourceFilter);
    if (query) tasks = tasks.filter((task) => (task.title + " " + (task.requirement || "") + " " + (task.owner || "") + " " + (task.display_name || "") + " " + (task.username || "")).toLowerCase().includes(query));
    if (status === "done") tasks = tasks.filter((task) => task.completed && !task.archived);
    else if (status === "lost") tasks = tasks.filter((task) => task.lost && !task.archived);
    else if (status === "open") tasks = tasks.filter((task) => !task.completed && !task.lost && !task.archived);
    else if (status === "overdue") tasks = tasks.filter((task) => { const [label] = taskStatus(task); return label === "已逾期"; });
    else if (status === "shared") tasks = tasks.filter((task) => task.source && task.source !== "local");
    if (tag) tasks = tasks.filter((task) => tag === "none"
      ? !(task.tags || []).length : (task.tags || []).includes(tag));
    if (dueFilter) {
      const now = new Date();
      const end = new Date(now.getTime() + 3 * 86400000);
      tasks = tasks.filter((task) => {
        if (dueFilter === "none") return !task.due;
        const due = taskDueDate(task);
        if (!due) return false;
        if (dueFilter === "overdue") return !task.completed && due < now;
        if (dueFilter === "today") return due.toDateString() === now.toDateString();
        return due >= now && due <= end;
      });
    }
    const terminalRank = (task) => (task.completed || task.lost) ? 1 : 0;
    tasks.sort((a, b) => terminalRank(a) - terminalRank(b));
    if (sort === "updated") {
      tasks.sort((a, b) => terminalRank(a) - terminalRank(b)
        || String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
    } else if (sort === "progress") {
      tasks.sort((a, b) => terminalRank(a) - terminalRank(b)
        || (b.progress || 0) - (a.progress || 0));
    } else if (sort === "owner") {
      tasks.sort((a, b) => terminalRank(a) - terminalRank(b)
        || String(a.owner || "").localeCompare(String(b.owner || ""), "zh-CN"));
    } else {
      tasks.sort((a, b) => {
        const rank = terminalRank(a) - terminalRank(b);
        if (rank) return rank;
        const da = taskDueDate(a) ? taskDueDate(a).getTime() : Infinity;
        const db = taskDueDate(b) ? taskDueDate(b).getTime() : Infinity;
        return da - db;
      });
    }
    $("taskCount").textContent = "共 " + tasks.length + " 条";
    const rows = tasks.map((task) => {
      const [label, cls] = taskStatus(task);
      const tagHtml = (task.tags || []).map((tag) => {
        const names = { warning: "预警", lost: "流失", follow: "跟进" };
        return `<span class="tag-badge ${tag}">${names[tag] || esc(tag)}</span>`;
      }).join("");
      return `<tr>
        <td><span class="task-title">${esc(task.title)}</span><span class="sub">${esc(task.requirement || "")}</span></td>
        <td><span class="avatar">${esc((task.display_name || task.username || "?").slice(0, 1))}</span>${esc(task.display_name || task.username || "")}<span class="sub">@${esc(task.username || "")}</span></td>
        <td>${esc(task.owner || "待指派")}${task.owner_username ? `<span class="sub">@${esc(task.owner_username)}</span>` : ""}${task.copy_count > 1 ? `<span class="sub">合并 ${task.copy_count} 个客户端</span>` : ""}</td>
        <td>${esc(task.cycle || "一次性")}</td>
        <td>${fmtDate(task.due)}</td>
        <td><div class="progress"><div class="track"><i style="width:${task.progress || 0}%"></i></div><span>${task.progress || 0}%</span></div></td>
        <td><span class="pill ${cls}">${label}</span></td>
        <td>${tagHtml || "—"}</td>
        <td><span class="pill ${task.merged ? "shared" : (task.source && task.source !== "local" ? "shared" : "archived")}">${esc(task.merged ? "合并" : sourceLabel(task.source))}</span></td>
        <td><button class="btn small" data-task-detail="1" data-user="${task.user_id}" data-task="${esc(task.id)}">详情</button>
          <button class="btn small ghost" data-task-chat="1" data-user="${task.user_id}" data-task="${esc(task.id)}">沟通</button></td>
      </tr>`;
    }).join("");
    $("taskRows").innerHTML = rows || `<tr><td colspan="10"><div class="empty">没有匹配的任务。</div></td></tr>`;
  }

  function findTask(userId, taskId) {
    return (state.data.tasks || []).find((task) =>
      String(task.user_id) === String(userId) && String(task.id) === String(taskId));
  }

  function renderTaskTagButtons() {
    document.querySelectorAll("[data-task-tag]").forEach((button) => {
      button.classList.toggle("on", state.taskTags.includes(button.dataset.taskTag));
    });
  }

  function openTaskDetail(button) {
    const task = findTask(button.dataset.user, button.dataset.task);
    if (!task) return;
    state.taskKey = { userId: task.user_id, taskId: task.id };
    state.taskTags = (task.tags || []).slice();
    $("taskModalTitle").textContent = task.title || "任务详情";
    const [statusLabel, statusClass] = taskStatus(task);
    const tags = (task.tags || []).map((tag) => {
      const names = { warning: "预警", lost: "流失", follow: "跟进" };
      return `<span class="tag-badge ${tag}">${names[tag] || esc(tag)}</span>`;
    }).join("");
    const info = [
      ["归属账户", (task.display_name || task.username || "") + "  @" + (task.username || "")],
      ["负责人", (task.owner || "待指派") + (task.owner_username ? "  @" + task.owner_username : "")],
      ["周期", task.cycle || "一次性"],
      ["截止时间", fmtDate(task.due)],
      ["进度", (task.progress || 0) + "%"],
      ["来源", sourceLabel(task.source)],
    ];
    const subtasks = (task.subtasks || []).map((subtask) => `<div class="detail-subtask ${subtask.done ? "done" : ""}">
      <span class="check">${subtask.done ? "✓" : "○"}</span>
      <span>${esc(subtask.title || "子任务")}</span>
      <span class="sub">${esc(subtask.owner || "待指派")}${subtask.due ? " · " + esc(fmtDate(subtask.due)) : ""}</span>
    </div>`).join("");
    const notes = (task.notes || []).slice(-6).map((note) => {
      const text = typeof note === "string" ? note : (note.text || "");
      const at = typeof note === "string" ? "" : (note.at || "");
      return `<div class="detail-note"><span class="meta">${esc((at || "").slice(0, 16).replace("T", " "))}</span>${esc(text)}</div>`;
    }).join("");
    $("taskDetail").innerHTML = `
      <div class="detail-badges"><span class="pill ${statusClass}">${statusLabel}</span>${tags}</div>
      <div class="detail-grid">${info.map(([label, value]) =>
        `<div class="detail-item"><span>${esc(label)}</span><b>${esc(value)}</b></div>`).join("")}</div>
      <div class="detail-section"><h4>任务要求</h4>
        <div class="detail-text">${esc(task.requirement || "未填写")}</div></div>
      ${task.lost ? `<div class="detail-section"><h4>流失原因</h4><div class="detail-text">${esc(task.lost_reason || "未填写")}</div></div>` : ""}
      ${subtasks ? `<div class="detail-section"><h4>子任务（${(task.subtasks || []).filter((s) => s.done).length}/${(task.subtasks || []).length}）</h4><div class="detail-list">${subtasks}</div></div>` : ""}
      ${notes ? `<div class="detail-section"><h4>任务记录</h4><div class="detail-list">${notes}</div></div>` : ""}`;
    renderTaskTagButtons();
    $("taskError").textContent = "";
    $("taskChat").disabled = false;
    $("taskChat").title = task.owner_username ? "与负责人沟通" : "未指派负责人，将沟通建任务人";
    $("taskModal").classList.remove("hidden");
  }

  function closeTaskDetail() {
    state.taskKey = null;
    state.taskTags = [];
    $("taskModal").classList.add("hidden");
  }

  function toggleTaskTag(button) {
    const tag = button.dataset.taskTag;
    if (state.taskTags.includes(tag)) {
      state.taskTags = state.taskTags.filter((item) => item !== tag);
    } else {
      state.taskTags.push(tag);
    }
    renderTaskTagButtons();
  }

  async function saveTaskTags() {
    if (!state.taskKey) return;
    try {
      await api(`/api/admin/tasks/${state.taskKey.userId}/${encodeURIComponent(state.taskKey.taskId)}/tags`, {
        method: "POST",
        body: JSON.stringify({ tags: state.taskTags }),
      });
      toast("任务标签已保存，客户端下次状态更新后同步", "good");
      closeTaskDetail();
      await loadData(true);
    } catch (error) {
      $("taskError").textContent = error.message;
    }
  }

  const QUICK_MESSAGES = ["过来办公室开个会", "更新下项目情况", "项目进展顺利吗", "请尽快反馈", "收到请回复"];

  function openChat(button) {
    const task = findTask(button.dataset.user, button.dataset.task);
    state.chatTask = {
      userId: button.dataset.user,
      taskId: button.dataset.task,
      title: task ? task.title : (button.dataset.title || "已删除任务对话"),
    };
    state.chatReadOnly = !task;
    $("chatTitle").textContent = state.chatTask.title;
    $("chatMeta").textContent = task ? "正在连接负责人…" : "任务已删除，仅可查看历史消息";
    $("chatHistory").innerHTML = `<div class="empty">加载中…</div>`;
    $("chatInput").value = "";
    $("chatInput").disabled = state.chatReadOnly;
    $("chatSend").disabled = state.chatReadOnly;
    $("chatInput").placeholder = state.chatReadOnly
      ? "任务已删除，历史对话只读" : "输入要发送给负责人的消息…";
    $("chatError").textContent = "";
    $("chatQuick").innerHTML = state.chatReadOnly ? "" : QUICK_MESSAGES
      .map((text) => `<button type="button" data-quick-chat="${esc(text)}">${esc(text)}</button>`).join("");
    $("chatModal").classList.remove("hidden");
    loadChat();
    clearInterval(state.chatTimer);
    state.chatTimer = setInterval(loadChat, 5000);
  }

  async function loadChat() {
    if (!state.chatTask) return;
    try {
      const data = await api(`/api/admin/messages?task_user_id=${state.chatTask.userId}&task_id=${encodeURIComponent(state.chatTask.taskId)}`);
      const info = data.recipient || {};
      const recipient = info.recipient || {};
      const online = recipient.last_seen_at && (Date.now() - new Date(recipient.last_seen_at).getTime() < 45000);
      const fallback = info.recipient_kind === "creator";
      $("chatMeta").textContent = state.chatReadOnly
        ? "任务已删除，仅可查看历史消息"
        : (fallback
          ? `负责人未绑定账号，将沟通建任务人：${recipient.display_name || recipient.username || ""}　${online ? "在线" : "离线"}　@${recipient.username || ""}`
          : `负责人：${info.owner || recipient.display_name || "未绑定"}　${online ? "在线" : "离线"}　@${recipient.username || ""}`);
      const messages = data.messages || [];
      $("chatHistory").innerHTML = messages.length ? messages.map((message) => {
        const mine = state.user && message.from_id === state.user.id;
        return `<div class="chat-msg ${mine ? "mine" : ""}"><span class="meta">${esc(message.from_name || message.from_username)} · ${esc((message.created_at || "").slice(11, 16))}</span>${esc(message.body)}</div>`;
      }).join("") : `<div class="empty">还没有消息，发送第一条吧。</div>`;
      $("chatHistory").scrollTop = $("chatHistory").scrollHeight;
      if (messages.length) {
        api("/api/admin/messages/thread/read", {
          method: "POST",
          body: JSON.stringify({ task_user_id: state.chatTask.userId, task_id: state.chatTask.taskId }),
        }).then(loadMessageThreads).catch(() => {});
      }
    } catch (error) {
      $("chatError").textContent = error.message;
    }
  }

  function closeChat() {
    state.chatTask = null;
    state.chatReadOnly = false;
    clearInterval(state.chatTimer);
    state.chatTimer = null;
    $("chatInput").disabled = false;
    $("chatSend").disabled = false;
    $("chatModal").classList.add("hidden");
  }

  async function sendChat(text) {
    if (!state.chatTask || state.chatReadOnly) return;
    const body = (text === undefined ? $("chatInput").value : text).trim();
    if (!body) {
      $("chatError").textContent = "请输入消息内容";
      return;
    }
    try {
      const result = await api("/api/admin/messages/send", {
        method: "POST",
        body: JSON.stringify({ task_user_id: state.chatTask.userId, task_id: state.chatTask.taskId, body }),
      });
      $("chatInput").value = "";
      $("chatError").textContent = "";
      toast(result.recipient_kind === "creator"
        ? "负责人未绑定，已发送给建任务人"
        : (result.online ? "已发送，负责人当前在线" : "已发送，负责人当前离线，上线后可查看"), "good");
      await loadChat();
    } catch (error) {
      $("chatError").textContent = error.message;
    }
  }

  async function loadMessageThreads() {
    try {
      const data = await api("/api/admin/messages/threads");
      state.messageThreads = data.threads || [];
      renderMessageThreads();
      const badge = $("msgBadge");
      badge.textContent = String(data.unread || 0);
      badge.classList.toggle("hidden", !data.unread);
    } catch (error) {
      $("messageThreads").innerHTML = `<tr><td colspan="6"><div class="empty">${esc(error.message)}</div></td></tr>`;
    }
  }

  function renderMessageThreads() {
    const threads = state.messageThreads || [];
    $("messageCount").textContent = "共 " + threads.length + " 个对话";
    $("messageThreads").innerHTML = threads.map((thread) => `<tr>
      <td><span class="task-title">${esc(thread.task_title || "任务对话")}</span></td>
      <td>${esc(thread.latest_from || "")}</td>
      <td>${esc(thread.latest_body || "")}</td>
      <td>${esc((thread.latest_at || "").slice(11, 16))}</td>
      <td>${thread.unread ? `<span class="message-unread">${thread.unread}</span>` : "0"}</td>
      <td><button class="btn small" data-message-thread="1" data-user="${thread.task_user_id}" data-task="${esc(thread.task_id || "")}" data-title="${esc(thread.task_title || "")}">查看对话</button></td>
    </tr>`).join("") || `<tr><td colspan="6"><div class="empty">还没有任务消息。打开任务行「沟通」发送第一条。</div></td></tr>`;
  }

  function openMessageThread(button) {
    openChat(button);
  }

  function switchPage(page) {
    state.page = page;
    document.querySelectorAll(".page").forEach((el) => el.classList.add("hidden"));
    $("page-" + page).classList.remove("hidden");
    document.querySelectorAll(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.page === page));
    const [eyebrow, title] = PAGE_META[page];
    $("pageEyebrow").textContent = eyebrow;
    $("pageTitle").textContent = title;
    if (page === "tasks") renderTasks();
    if (page === "messages") loadMessageThreads();
    if (page === "insights") renderInsights();
    if (page === "org") renderOrg();
  }

  async function login() {
    const error = $("loginError");
    error.textContent = "";
    try {
      const result = await api("/api/login", {
        method: "POST",
        body: JSON.stringify({ username: $("loginUser").value.trim(), password: $("loginPass").value }),
      });
      if (result.user.role !== "admin") throw new Error("该账号不是管理账号，请在清心任务客户端登录。");
      state.token = result.token;
      localStorage.setItem("taskdock_admin_token", state.token);
      showApp(result.user);
    } catch (err) {
      error.textContent = err.message;
    }
  }

  async function setup() {
    const error = $("setupError");
    error.textContent = "";
    const password = $("setupPass").value;
    if (password !== $("setupPass2").value) { error.textContent = "两次输入的密码不一致。"; return; }
    try {
      const result = await api("/api/setup", {
        method: "POST",
        body: JSON.stringify({
          username: $("setupUser").value.trim(),
          display_name: $("setupName").value.trim() || $("setupUser").value.trim(),
          password,
        }),
      });
      state.token = result.token;
      localStorage.setItem("taskdock_admin_token", state.token);
      showApp(result.user);
    } catch (err) {
      error.textContent = err.message;
    }
  }

  async function createUser() {
    try {
      await api("/api/admin/users", {
        method: "POST",
        body: JSON.stringify({
          username: $("newUser").value.trim(),
          display_name: $("newName").value.trim(),
          password: $("newPass").value,
          org_unit_id: $("newOrg").value || null,
        }),
      });
      $("newUser").value = "";
      $("newName").value = "";
      $("newPass").value = "";
      $("newOrg").value = "";
      toast("清心任务客户端账户已创建", "good");
      loadData(true);
    } catch (err) { toast(err.message, "error"); }
  }

  function openEditAccount(button) {
    state.editingId = button.dataset.id;
    $("editUsername").value = button.dataset.username || "";
    $("editDisplay").value = button.dataset.display || "";
    fillOrgSelects();
    $("editOrg").value = button.dataset.org || "";
    $("editError").textContent = "";
    $("accountModal").classList.remove("hidden");
    setTimeout(() => $("editUsername").focus(), 30);
  }

  function closeEditAccount() {
    state.editingId = null;
    $("accountModal").classList.add("hidden");
  }

  async function saveEditAccount() {
    const id = state.editingId;
    if (!id) return;
    const username = $("editUsername").value.trim();
    const display_name = $("editDisplay").value.trim();
    if (!username || !display_name) {
      $("editError").textContent = "账号和显示名称都不能为空";
      return;
    }
    try {
      const result = await api(`/api/admin/users/${id}/update`, {
        method: "POST",
        body: JSON.stringify({ username, display_name,
          org_unit_id: $("editOrg").value || null }),
      });
      if (state.user && String(state.user.id) === String(id)) {
        state.user.username = result.user.username;
        state.user.display_name = result.user.display_name;
      }
      closeEditAccount();
      toast("账户资料已修改", "good");
      await loadData(true);
    } catch (err) {
      $("editError").textContent = err.message;
    }
  }

  async function accountAction(button) {
    const id = button.dataset.id;
    const action = button.dataset.action;
    try {
      if (action === "edit") {
        openEditAccount(button);
        return;
      } else if (action === "status") {
        const status = button.dataset.status;
        if (!confirm(status === "disabled" ? "停用这个账户？该账户将无法登录和同步。" : "重新启用这个账户？")) return;
        await api(`/api/admin/users/${id}/status`, { method: "POST", body: JSON.stringify({ status }) });
        toast("账户状态已更新", "good");
      } else if (action === "password") {
        const password = prompt("设置新密码（至少 6 位）：");
        if (password === null) return;
        await api(`/api/admin/users/${id}/password`, { method: "POST", body: JSON.stringify({ password }) });
        toast("密码已重置", "good");
      } else if (action === "delete") {
        const username = button.dataset.username;
        const typed = prompt(`此操作不可撤销。请输入账号 ${username} 确认删除：`);
        if (typed === null) return;
        if (typed.trim().toLowerCase() !== username.toLowerCase()) {
          toast("账号输入不匹配，已取消删除", "error");
          return;
        }
        if (!confirm(`最后确认：删除清心任务客户端账户 ${username}？\n该账户的任务、好友关系和邀请会一并删除。`)) return;
        await api(`/api/admin/users/${id}/delete`, {
          method: "POST",
          body: JSON.stringify({ confirm: typed.trim() }),
        });
        toast("清心任务客户端账户已删除", "good");
      }
      loadData(true);
    } catch (err) { toast(err.message, "error"); }
  }

  function bind() {
    $("setupBtn").addEventListener("click", setup);
    $("loginBtn").addEventListener("click", login);
    $("loginPass").addEventListener("keydown", (event) => { if (event.key === "Enter") login(); });
    $("setupPass2").addEventListener("keydown", (event) => { if (event.key === "Enter") setup(); });
    $("createUserBtn").addEventListener("click", createUser);
    $("editSave").addEventListener("click", saveEditAccount);
    $("editCancel").addEventListener("click", closeEditAccount);
    $("editClose").addEventListener("click", closeEditAccount);
    $("accountModal").addEventListener("click", (event) => {
      if (event.target === $("accountModal")) closeEditAccount();
    });
    $("editDisplay").addEventListener("keydown", (event) => {
      if (event.key === "Enter") saveEditAccount();
    });
    $("refreshBtn").addEventListener("click", () => loadData(false));
    $("collectBtn").addEventListener("click", collectTasks);
    $("addOrgBtn").addEventListener("click", () => openOrgModal());
    $("orgSave").addEventListener("click", saveOrg);
    $("orgClose").addEventListener("click", closeOrgModal);
    $("orgCancel").addEventListener("click", closeOrgModal);
    $("orgTree").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-org-action]");
      if (button) orgAction(button);
    });
    $("logoutBtn").addEventListener("click", () => {
      if (state.token) {
        fetch("/api/logout", { method: "POST", headers: { "Authorization": "Bearer " + state.token } }).catch(() => {});
      }
      clearSession();
      showGate("login");
    });
    document.querySelectorAll(".nav-item").forEach((button) => {
      button.addEventListener("click", () => switchPage(button.dataset.page));
    });
    document.querySelectorAll("[data-jump]").forEach((button) => {
      button.addEventListener("click", () => switchPage(button.dataset.jump));
    });
    $("accountSearch").addEventListener("input", renderAccounts);
    $("taskSearch").addEventListener("input", renderTasks);
    $("taskStatus").addEventListener("change", renderTasks);
    $("taskUser").addEventListener("change", renderTasks);
    $("taskOwner").addEventListener("input", renderTasks);
    ["taskCycle", "taskProgress", "taskTag", "taskDue", "taskSource", "taskSort"].forEach((id) => {
      $(id).addEventListener("change", renderTasks);
    });
    $("taskReset").addEventListener("click", () => {
      ["taskSearch", "taskOwner", "taskStatus", "taskUser", "taskCycle",
       "taskProgress", "taskTag", "taskDue", "taskSource"].forEach((id) => {
        $(id).value = "";
      });
      $("taskSort").value = "due";
      renderTasks();
    });
    $("messageRefresh").addEventListener("click", loadMessageThreads);
    $("messageThreads").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-message-thread]");
      if (button) openMessageThread(button);
    });
    $("insightFilters").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-insight-filter]");
      if (!button) return;
      state.insightFilter = button.dataset.insightFilter;
      state.insightIssue = null;
      renderInsightProblems(activeTaskList());
    });
    $("insightIssues").addEventListener("click", (event) => {
      const taskButton = event.target.closest("button[data-insight-task]");
      if (taskButton) {
        event.preventDefault();
        showTaskFromInsight(taskButton.dataset.insightTask);
        return;
      }
      const summary = event.target.closest("summary");
      if (!summary) return;
      const details = summary.parentElement;
      state.insightIssue = details.dataset.issue;
      state.insightFilter = "all";
      renderInsightProblems(activeTaskList());
    });
    ["insightProblems", "insightProjects"].forEach((id) => {
      $(id).addEventListener("click", (event) => {
        if (event.target.closest("button[data-insight-clear]")) {
          state.insightIssue = null;
          state.insightFilter = "all";
          renderInsightProblems(activeTaskList());
          return;
        }
        const chatButton = event.target.closest("button[data-insight-chat]");
        if (chatButton) {
          chatTaskFromInsight(chatButton.dataset.insightChat);
          return;
        }
        const button = event.target.closest("button[data-insight-task]");
        if (button) showTaskFromInsight(button.dataset.insightTask);
      });
    });
    $("taskRows").addEventListener("click", (event) => {
      const chatButton = event.target.closest("button[data-task-chat]");
      if (chatButton) { openChat(chatButton); return; }
      const button = event.target.closest("button[data-task-detail]");
      if (button) openTaskDetail(button);
    });
    $("chatClose").addEventListener("click", closeChat);
    $("chatCancel").addEventListener("click", closeChat);
    $("chatSend").addEventListener("click", () => sendChat());
    $("chatQuick").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-quick-chat]");
      if (button) sendChat(button.dataset.quickChat);
    });
    document.querySelectorAll("[data-task-tag]").forEach((button) => {
      button.addEventListener("click", () => toggleTaskTag(button));
    });
    $("taskSave").addEventListener("click", saveTaskTags);
    $("taskChat").addEventListener("click", () => {
      const key = state.taskKey;
      if (!key) return;
      const taskId = key.taskId;
      closeTaskDetail();
      chatTaskFromInsight(taskId);
    });
    $("taskClose").addEventListener("click", closeTaskDetail);
    $("taskCancel").addEventListener("click", closeTaskDetail);
    $("accountRows").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action]");
      if (button) accountAction(button);
    });
  }

  bind();
  init();
})();



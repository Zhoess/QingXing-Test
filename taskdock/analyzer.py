# -*- coding: utf-8 -*-
"""Email-to-task analysis.

The local rules are deterministic and explainable. An optional
OpenAI-compatible chat-completions endpoint can produce a richer draft; the
draft is always opened in the editable task form before anything is saved.
"""

import json
import re
import socket
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from . import model

ACTION_WORDS = (
    "请", "需要", "务必", "完成", "提交", "确认", "反馈", "回复", "跟进", "推进",
    "准备", "提供", "安排", "处理", "更新", "评审", "上线", "发布", "交付",
    "签收", "整理", "汇总", "沟通", "对接", "协助", "deadline", "due",
)
INFO_WORDS = ("促销", "优惠", "订阅", "退订", "newsletter", "unsubscribe",
              "自动发送", "请勿直接回复")
GREETINGS = ("你好", "您好", "hi", "hello", "各位", "大家好", "辛苦了", "谢谢",
             "thanks", "best", "此致", "敬礼")
OWNER_BLACKLIST = {
    "大家", "各位", "相关", "同事", "团队", "我们", "你们", "负责", "人员", "请在",
    "请于", "尽快", "务必", "部门", "公司", "客户", "供应", "厂商", "以上",
    "协助", "准备", "确认", "完成", "提交", "反馈", "跟进", "处理", "对接",
}


def _normalize(text):
    trans = str.maketrans("０１２３４５６７８９：％", "0123456789:%")
    return (text or "").translate(trans).replace("\u3000", " ").replace("\xa0", " ")


def clean_subject(subject):
    text = _normalize(subject).strip()
    for _ in range(3):
        text = re.sub(r"^\s*(?:回复|答复|转发|回覆)\s*[:：]\s*", "", text)
        text = re.sub(r"^\s*(?:re|fw|fwd)\s*[:：]\s*", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 38:
        text = text[:37].rstrip() + "…"
    return text or "邮件待办"


def _period_hour(period, default=18):
    if period in ("上午", "早上"):
        return 10
    if period in ("下午", "中午"):
        return 14
    if period in ("晚上", "傍晚"):
        return 19
    return default


def _parse_clock(period, hour, minute, fallback_hour=18):
    try:
        hour = int(hour)
    except (TypeError, ValueError):
        return fallback_hour, 0
    if period in ("下午", "晚上", "傍晚") and 0 < hour < 12:
        hour += 12
    if period == "中午" and 0 < hour < 11:
        hour += 12
    try:
        minute = int(minute or 0)
    except (TypeError, ValueError):
        minute = 0
    return min(23, hour), min(59, minute)


def _safe_dt(year, month, day, hour=18, minute=0, at=None):
    at = at or model.now()
    try:
        dt = datetime(year, month, day, hour, minute)
    except ValueError:
        return None
    if year == at.year and dt < at - timedelta(days=45):
        try:
            dt = dt.replace(year=year + 1)
        except ValueError:
            return None
    return dt


def extract_due(text, at=None):
    """Extract the most likely deadline. Returns (datetime, source_text)."""
    at = at or model.now()
    text = _normalize(text)
    candidates = []
    absolute = re.compile(
        r"(?:(20\d{2})\s*[年/-]\s*)?(\d{1,2})\s*[月/-]\s*(\d{1,2})\s*[日号]?"
        r"(?:\s*(上午|下午|晚上|傍晚|中午|早上)?\s*(\d{1,2})\s*(?:[:：点时])\s*(\d{1,2})?\s*分?)?"
    )
    for match in absolute.finditer(text):
        year = int(match.group(1)) if match.group(1) else at.year
        month, day = int(match.group(2)), int(match.group(3))
        if not (1 <= month <= 12 and 1 <= day <= 31):
            continue
        period, hour, minute = match.group(4), match.group(5), match.group(6)
        h, m = _parse_clock(period, hour, minute, _period_hour(period, 18))
        dt = _safe_dt(year, month, day, h, m, at)
        if not dt:
            continue
        before = text[max(0, match.start() - 18):match.start()]
        after = text[match.end():match.end() + 10]
        score = 0
        if re.search(r"(截止|deadline|due|请于|于|在)\s*$", before, re.I):
            score += 3
        if re.search(r"^\s*(前|之前|以前|截止)", after):
            score += 3
        if year != at.year:
            score += 1
        if period or hour:
            score += 1
        if dt < at - timedelta(days=60):
            score -= 2
        candidates.append((score, dt, match.group(0).strip()))

    relative = re.compile(
        r"(今天|明天|后天|本周[一二三四五六日天]|下周[一二三四五六日天]|本月底|月底)"
        r"(?:\s*(上午|下午|晚上|傍晚|中午|早上)?\s*(\d{1,2})\s*(?:[:：点时])\s*(\d{1,2})?\s*分?)?"
    )
    weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
    for match in relative.finditer(text):
        word = match.group(1)
        period, hour, minute = match.group(2), match.group(3), match.group(4)
        h, m = _parse_clock(period, hour, minute, _period_hour(period, 18))
        if word == "今天":
            dt = at.replace(hour=h, minute=m)
        elif word == "明天":
            dt = (at + timedelta(days=1)).replace(hour=h, minute=m)
        elif word == "后天":
            dt = (at + timedelta(days=2)).replace(hour=h, minute=m)
        elif word in ("本月底", "月底"):
            nxt = (at.replace(day=1) + timedelta(days=32)).replace(day=1)
            dt = (nxt - timedelta(days=1)).replace(hour=h, minute=m)
        else:
            target = weekday_map.get(word[-1], 0)
            monday = at - timedelta(days=at.weekday())
            if word.startswith("下周"):
                monday += timedelta(days=7)
            dt = (monday + timedelta(days=target)).replace(hour=h, minute=m)
        candidates.append((4, dt, match.group(0).strip()))

    if not candidates:
        return None, ""
    candidates.sort(key=lambda c: (-c[0], c[1]))
    best_score = candidates[0][0]
    top = [c for c in candidates if c[0] == best_score]
    top.sort(key=lambda c: c[1])
    return top[0][1], top[0][2]


def extract_owner(text):
    text = _normalize(text)
    patterns = [
        r"负责人\s*[:：]\s*([\u4e00-\u9fa5A-Za-z·]{2,10})",
        r"^\s*([\u4e00-\u9fa5·]{2,4})\s*[，,：:]\s*(?:你好|您好|好)",
        r"^\s*([\u4e00-\u9fa5·]{2,4})\s*[，,]\s*$",
        r"请\s*(?:由\s*)?([\u4e00-\u9fa5·]{2,4})\s*(?:在|于|尽快|负责|跟进|确认|完成|提交|准备|处理|协助|对接)",
        r"由\s*([\u4e00-\u9fa5·]{2,4})\s*(?:负责|跟进|牵头|完成|处理)",
        r"([\u4e00-\u9fa5·]{2,4})\s*负责",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.MULTILINE)
        if not match:
            continue
        name = match.group(1).strip()
        name = re.split(r"[，,：:。；;\s]", name)[0]
        if 1 < len(name) <= 10 and name not in OWNER_BLACKLIST:
            return name
    return ""


def extract_progress(text):
    text = _normalize(text)
    patterns = [
        r"(?:进度|完成度|已完成)\s*(?:约|大约|为|达到|[:：])?\s*(\d{1,3})\s*%",
        r"(\d{1,3})\s*%\s*(?:的)?(?:进度|完成度)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return max(0, min(100, int(match.group(1))))
    return None


def done_hint(text):
    text = _normalize(text)
    if re.search(r"(尚未|还未|没有|未)(?:全部)?完成", text):
        return False
    return bool(re.search(r"(?:已|已经)(?:全部)?(?:完成|交付|上线|提交|验收)", text))


def _clean_line(line):
    line = re.sub(r"^\s*(?:[-*•·]|\d{1,2}[.、)]|[（(]\d+[)）])\s*", "", line.strip())
    line = re.sub(r"^[\u4e00-\u9fa5·]{2,4}\s*[，,：:]\s*(?:你好|您好|好)\s*[，,：:]?\s*", "", line)
    line = re.sub(r"^(?:请|烦请|麻烦)\s*", "请", line) if line.startswith("请") else line
    line = re.sub(r"\s+", " ", line).strip(" \t")
    return line


def action_lines(body, limit=4):
    candidates = []
    for raw in re.split(r"[\r\n]+", body or ""):
        line = _clean_line(raw)
        if len(line) < 6:
            continue
        lower = line.lower()
        if any(word in lower for word in INFO_WORDS):
            continue
        if any(lower.startswith(word) for word in GREETINGS) and len(line) < 24:
            continue
        if line.startswith(">"):
            continue
        score = 0
        for word in ACTION_WORDS:
            if word.lower() in lower:
                score += 2 if word in ("请", "需要", "务必", "截止", "完成", "提交") else 1
        if re.search(r"\d{1,2}\s*[月/-]\s*\d{1,2}|\d{1,2}\s*[:：]\s*\d{2}", line):
            score += 2
        if "负责人" in line:
            score += 1
        if score:
            candidates.append((score, line))
    if not candidates:
        return []
    selected = sorted(candidates, key=lambda item: -item[0])[:limit]
    order = {line: i for i, (_, line) in enumerate(candidates)}
    selected.sort(key=lambda item: order.get(item[1], 0))
    return [line for _, line in selected]


def _normalize_match_text(text):
    text = _normalize(text).lower()
    return re.sub(r"[^0-9a-z\u4e00-\u9fa5]+", "", text)


def _bigrams(text):
    clean = _normalize_match_text(text)
    if len(clean) < 2:
        return {clean} if clean else set()
    return {clean[i:i + 2] for i in range(len(clean) - 1)}


def match_tasks(subject, body, tasks, owner=""):
    subj = _normalize_match_text(subject)
    if not subj:
        return []
    results = []
    for task in tasks:
        title = _normalize_match_text(task.get("title", ""))
        if not title:
            continue
        seq = SequenceMatcher(None, subj, title).ratio()
        a, b = _bigrams(subject), _bigrams(task.get("title", ""))
        overlap = len(a & b) / float(max(1, min(len(a), len(b)))) if a and b else 0
        score = max(seq * 0.9, overlap * 0.88)
        if task.get("owner") and owner and task["owner"] == owner:
            score += 0.04
        if title and title in _normalize_match_text(body):
            score += 0.08
        score = min(0.99, score)
        if score >= 0.26:
            results.append({
                "task_id": task.get("id"),
                "title": task.get("title", ""),
                "score": round(score, 3),
                "reason": "标题/关键词相似 %d%%" % int(score * 100),
            })
    results.sort(key=lambda item: -item["score"])
    return results[:3]


def analyze_email(email, tasks, at=None):
    at = at or model.now()
    subject = email.get("subject") or ""
    body = email.get("body") or ""
    blob = subject + "\n" + body

    title = clean_subject(subject)
    due, due_source = extract_due(blob, at)
    owner = extract_owner(blob)
    progress = extract_progress(blob)
    done = done_hint(blob)
    lines = action_lines(body)
    matches = match_tasks(subject, body, tasks, owner)

    actionable = bool(lines) or bool(re.search(r"请|需要|务必|截止|提交|完成", blob))
    info = any(word in blob.lower() for word in INFO_WORDS) and not lines
    if info or not actionable:
        intent = "info"
    elif matches and matches[0]["score"] >= 0.55:
        intent = "update"
    else:
        intent = "new"

    if lines:
        requirement = "；".join(line.rstrip("。；") for line in lines)
    else:
        requirement = re.sub(r"\s+", " ", body).strip()[:180]
    if len(requirement) > 500:
        requirement = requirement[:499].rstrip() + "…"

    confidence = 0.34
    if due:
        confidence += 0.2
    if owner:
        confidence += 0.15
    if lines:
        confidence += 0.18
    if matches:
        confidence += 0.1
    if intent == "info":
        confidence = min(confidence, 0.35)
    confidence = max(0.2, min(0.95, confidence))

    return {
        "intent": intent,
        "title": title,
        "requirement": requirement,
        "due": model.iso(due) if due else None,
        "due_source": due_source,
        "owner": owner,
        "progress": progress,
        "done_hint": done,
        "matches": matches,
        "confidence": round(confidence, 2),
        "actionable": actionable,
        "summary": (lines[0] if lines else re.sub(r"\s+", " ", body).strip()[:90]),
        "analyzed_at": model.iso(at),
    }


def ensure_analyses(store):
    """Analyze new or unanalyzed emails in place. Returns changed count."""
    changed = 0
    for email in store.emails:
        analysis = email.get("analysis")
        if not analysis or not analysis.get("analyzed_at"):
            linked_task_id = None
            for task in store.tasks:
                if email.get("id") in (task.get("email_ids") or []):
                    linked_task_id = task.get("id")
                    break
            email["analysis"] = analyze_email(email, store.tasks)
            if linked_task_id:
                email["analysis"]["linked_task_id"] = linked_task_id
            changed += 1
    if changed:
        store.save()
    return changed


# ---------------------------------------------------------------- optional AI

AI_SYSTEM_PROMPT = (
    "你是一名从业30年的政务文员，擅长从邮件、通知、函件、工作周报和汇报中识别项目、"
    "判断项目阶段，并把事项拆解成可跟踪的工作任务。"
    "工作周报不是一封普通邮件：要把它当成项目台账来读，识别所有独立项目。"
    "项目可能同时出现在「本周项目变化」「项目详情」「重点工作跟踪」「合同签订」等章节，"
    "必须按项目名称合并去重，不要按段落或句子拆成多个项目。"
    "每个项目要尽量完整地保留事实，不能只写一句概括；要写清楚背景、已经发生的进展、"
    "当前情况和本次要求/交付标准，保留金额、日期、人名、合同状态、验收要求等关键数字。"
    "每个项目判断与已有任务的关系：update（同一项目补充要求/进度/时间变化）、"
    "subtask（属于已有任务的子工作包）、new（新建）、unrelated（纯通知/无后续动作）。"
    "如果当前邮件是周报，必须结合已有任务和上一期周报邮件，逐项列出本周与上一期的差异："
    "changes 数组写新增要求、进度变化、时间变化、完成项、卡点和风险；"
    "suggest_subtask 表示是否建议把这些差异新增为已有任务的子任务；"
    "subtask_title 给出建议的子任务名称（不新增则为空字符串）。"
    "update/subtask 必须从输入任务列表中选择 target_task_id，不确定时用 new。"
    "只返回 JSON，不要 markdown，不要解释。字段："
    "email_summary（一句话概括邮件）；projects（数组，每项包含 "
    "title（项目/事项名称）、summary（一句话当前情况）、"
    "background（项目背景、客户/甲方、合同或金额、历史由来、关键干系人）、"
    "progress（已经完成的进展、当前阶段、已交付/已签约/获奖情况、关键节点）、"
    "situation（当前正在推进什么、卡点、风险、待决策事项）、"
    "requirement（本次明确要求）、deliverable（交付物/材料/汇报/验收标准）、"
    "status（进行中/已签约/待签约/已完成/暂停/商机等）、"
    "contract_amount（合同金额或空字符串）、next_action（下一步动作）、"
    "due（YYYY-MM-DDTHH:MM:SS 或 null）、owner（负责人，可多人用顿号分隔）、"
    "action_items（字符串数组）、relation、target_task_id（已有任务 id 或 null）、"
    "changes（与上一期相比的差异字符串数组，最多 8 条）、"
    "suggest_subtask（true/false）、subtask_title（建议子任务名称或空字符串）、"
    "match_reason、confidence（0到1））。"
    "background/progress/situation/deliverable 不能为空泛套话，必须来自邮件原文；"
    "如果邮件没有明确交付标准，就根据要求归纳，不要编造。"
    "完成的、没有后续动作的合同/奖项不要生成任务。无法确定日期就返回 null。"
    "不要把人名误当项目；不要把部门、公司、大家当作负责人。"
)


class AnalyzerError(Exception):
    pass


def ai_config(store):
    settings = store.settings()
    if not settings.get("ai_enabled"):
        return None
    endpoint = (settings.get("ai_endpoint") or "").strip()
    key = store.ai_key()
    model_name = (settings.get("ai_model") or "").strip()
    if not endpoint or not key or not model_name:
        return None
    return {"endpoint": endpoint, "key": key, "model": model_name}


def _extract_json(text):
    text = (text or "").strip()
    text = re.sub(r"```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```", "", text).strip()
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise AnalyzerError("AI 没有返回有效的 JSON")
    start = min(starts)
    opening = text[start]
    closing = "}" if opening == "{" else "]"
    depth = 0
    in_string = False
    escaped = False
    end = -1
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                end = index
                break
    if end < 0:
        raise AnalyzerError("AI 返回的 JSON 不完整，可能是输出被截断；请减少项目或换用输出上限更高的模型")
    raw = text[start:end + 1]
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise AnalyzerError("AI JSON 解析失败：%s" % exc)
    if isinstance(data, list):
        return {"projects": data}
    if not isinstance(data, dict):
        raise AnalyzerError("AI 返回的 JSON 不是对象")
    return data


def _normalize_ai_project(data, subject, body, task_ids):
    relation = str(data.get("relation") or "new").lower()
    if relation not in ("new", "update", "subtask", "unrelated"):
        relation = "new"
    target = str(data.get("target_task_id") or "").strip() or None
    if target not in task_ids:
        target = None
    if relation in ("update", "subtask") and not target:
        relation = "new"
    title = str(data.get("title") or clean_subject(subject)).strip()[:160]
    background = str(data.get("background") or "").strip()
    progress_text = str(data.get("progress") or "").strip()
    situation = str(data.get("situation") or "").strip()
    deliverable = str(data.get("deliverable") or "").strip()
    requirement = str(data.get("requirement") or "").strip()
    items = data.get("action_items") or []
    action_items = []
    if isinstance(items, list):
        action_items = [str(item).strip() for item in items if str(item).strip()]
    raw_changes = data.get("changes") or []
    changes = []
    if isinstance(raw_changes, list):
        changes = [str(item).strip()[:240] for item in raw_changes if str(item).strip()][:8]
    subtask_title = str(data.get("subtask_title") or "").strip()[:160]
    suggest_subtask = data.get("suggest_subtask") in (True, 1, "1", "true", "True") and bool(changes or subtask_title)
    sections = []
    if background:
        sections.append("【背景】" + background)
    if progress_text:
        sections.append("【当前进展】" + progress_text)
    if situation:
        sections.append("【当前情况】" + situation)
    if requirement:
        sections.append("【本次要求】" + requirement)
    if deliverable:
        sections.append("【交付标准】" + deliverable)
    if action_items:
        sections.append("【行动项】" + "；".join(action_items))
    if sections:
        requirement = "\n".join(sections)
    else:
        requirement = requirement or re.sub(r"\s+", " ", body).strip()[:300]
    requirement = requirement[:4000]
    owner = str(data.get("owner") or "").strip()[:60]
    due = model.parse_dt(data.get("due")) if data.get("due") else None
    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence") or 0.6)))
    except (TypeError, ValueError):
        confidence = 0.6
    summary = str(data.get("summary") or "").strip()[:300]
    if not summary:
        summary = (situation or progress_text or background)[:300]
    return {
        "title": title or "邮件项目",
        "summary": summary,
        "background": background[:1200],
        "progress": progress_text[:1600],
        "situation": situation[:1200],
        "deliverable": deliverable[:1000],
        "requirement": requirement,
        "status": str(data.get("status") or "").strip()[:40],
        "contract_amount": str(data.get("contract_amount") or "").strip()[:40],
        "next_action": str(data.get("next_action") or "").strip()[:300],
        "due": model.iso(due) if due else None,
        "owner": owner,
        "action_items": action_items,
        "changes": changes,
        "suggest_subtask": suggest_subtask,
        "subtask_title": subtask_title,
        "relation": relation,
        "target_task_id": target,
        "match_reason": str(data.get("match_reason") or "").strip()[:300],
        "confidence": round(confidence, 2),
    }


def ai_subtask_requirement(project):
    """Build the body of an AI-created subtask: title plus this week's diff."""
    changes = [str(item).strip() for item in (project.get("changes") or []) if str(item).strip()]
    parts = []
    if changes:
        parts.append("本期差异：\n" + "\n".join("• " + item for item in changes))
    requirement = str(project.get("requirement") or "").strip()
    if requirement:
        parts.append("相关要求：\n" + requirement)
    if not parts:
        parts.append(str(project.get("summary") or "").strip())
    return "\n\n".join(parts)[:2000]


def analyze_email_ai(email, config, tasks=None, timeout=180, previous_emails=None):
    endpoint = (config.get("endpoint") or "").strip()
    key = (config.get("key") or "").strip()
    model_name = (config.get("model") or "").strip()
    if not endpoint.startswith(("http://", "https://")):
        raise AnalyzerError("AI API 地址必须以 http:// 或 https:// 开头")
    if not key or not model_name:
        raise AnalyzerError("AI API Key 或模型未配置")

    subject = email.get("subject") or ""
    sender = email.get("sender") or ""
    date_value = email.get("date") or ""
    body = (email.get("body") or "")[:12000]
    task_context = []
    for task in (tasks or [])[:40]:
        task_context.append({
            "id": task.get("id"),
            "title": task.get("title", ""),
            "owner": task.get("owner", ""),
            "due": task.get("due"),
            "status": task.get("status") or ("completed" if task.get("completed") else "active"),
            "requirement": (task.get("requirement") or "")[:700],
            "progress": task.get("progress"),
            "updated_at": task.get("updated_at"),
        })
    email_context = []
    subject_key = _normalize_match_text(subject)
    for previous in (previous_emails or []):
        if not isinstance(previous, dict) or previous.get("id") == email.get("id"):
            continue
        previous_subject = previous.get("subject") or ""
        previous_key = _normalize_match_text(previous_subject)
        similarity = SequenceMatcher(None, subject_key, previous_key).ratio() if subject_key and previous_key else 0
        if similarity < 0.22 and not ("周报" in subject_key and "周报" in previous_key):
            continue
        projects = []
        analysis = previous.get("analysis") or {}
        for item in (analysis.get("projects") or [])[:8]:
            if not isinstance(item, dict):
                continue
            projects.append({
                "title": item.get("title", ""),
                "summary": (item.get("summary") or "")[:300],
                "requirement": (item.get("requirement") or "")[:600],
                "progress": (item.get("progress") or "")[:400],
            })
        email_context.append({
            "date": previous.get("date"),
            "subject": previous_subject[:160],
            "body": (previous.get("body") or "")[:1200],
            "projects": projects,
        })
        if len(email_context) >= 3:
            break
    user_prompt = (
        "当前时间：%s\n邮件日期：%s\n发件人：%s\n主题：%s\n\n"
        "已有任务（用于判断本周差异和是否新增子任务）：\n%s\n\n"
        "上一期相关邮件：\n%s\n\n正文：\n%s"
        % (datetime.now().strftime("%Y-%m-%d %H:%M"), date_value, sender, subject,
           json.dumps(task_context, ensure_ascii=False),
           json.dumps(email_context, ensure_ascii=False), body)
    )
    payload = {
        "model": model_name,
        "temperature": 0.1,
        "max_tokens": 4000,
        "messages": [
            {"role": "system", "content": AI_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    is_glm_reasoning = (
        "bigmodel.cn" in endpoint
        and (model_name.startswith("glm-5") or model_name.startswith("glm-4.5")
             or model_name.startswith("glm-4.6"))
    )
    if is_glm_reasoning:
        # GLM-5 系列始终思考；思考 token 也占用 max_tokens，给足输出预算。
        payload["max_tokens"] = 12000
        payload["thinking"] = {"type": "enabled"}
        if model_name.startswith("glm-5.3"):
            # GLM-5.3 支持 low 推理档；长邮件分析优先降低延迟。
            payload["reasoning_effort"] = "low"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": "Bearer " + key,
            "api-key": key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise AnalyzerError("AI API 返回 HTTP %s：%s" % (exc.code, detail))
    except (socket.timeout, TimeoutError):
        raise AnalyzerError(
            "AI 请求超时（已等待 %d 秒）。可减少邮件长度、换更快的模型或稍后重试。" % timeout)
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in str(reason).lower():
            raise AnalyzerError(
                "AI 请求超时（已等待 %d 秒）。可减少邮件长度、换更快的模型或稍后重试。" % timeout)
        raise AnalyzerError("无法连接 AI API：%s" % reason)
    except Exception as exc:
        raise AnalyzerError("AI 请求失败：%s" % exc)

    try:
        response_data = json.loads(raw)
        choice = response_data["choices"][0]
        finish_reason = choice.get("finish_reason")
        content = choice["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    except (ValueError, KeyError, IndexError, TypeError):
        raise AnalyzerError("AI 返回格式不符合 Chat Completions 规范")
    if not content or not str(content).strip():
        reasoning = str(choice.get("message", {}).get("reasoning_content") or "")
        if reasoning:
            raise AnalyzerError(
                "AI 只返回了思考过程，最终内容为空（模型思考占用了输出上限）。"
                "请换用 glm-4-flash 等非思考模型，或减少邮件长度/项目数量后重试。"
            )
        raise AnalyzerError("AI 返回内容为空；请检查模型、Key 或稍后重试")

    try:
        data = _extract_json(content)
    except AnalyzerError as exc:
        if finish_reason == "length":
            raise AnalyzerError(
                "AI 输出被截断：项目太多或模型输出上限太小。请减少本周项目数量，或换用输出上限更高的模型。"
            )
        raise exc
    task_ids = {task.get("id") for task in (tasks or [])}
    raw_projects = data.get("projects")
    if not isinstance(raw_projects, list) or not raw_projects:
        raw_projects = [data]
    projects = []
    merged = {}
    for item in raw_projects:
        if not isinstance(item, dict):
            continue
        project = _normalize_ai_project(item, subject, body, task_ids)
        if project["relation"] == "unrelated":
            continue
        key = _normalize_match_text(project["title"])
        if key and key in merged:
            existing = merged[key]
            for field in ("summary", "requirement", "status", "contract_amount",
                          "next_action", "owner", "subtask_title"):
                if not existing.get(field) and project.get(field):
                    existing[field] = project[field]
            existing_changes = existing.setdefault("changes", [])
            for change in project.get("changes") or []:
                if change and change not in existing_changes:
                    existing_changes.append(change)
            if project.get("suggest_subtask"):
                existing["suggest_subtask"] = True
                if not existing.get("subtask_title"):
                    existing["subtask_title"] = project.get("subtask_title") or ""
            if project.get("confidence", 0) > existing.get("confidence", 0):
                existing["confidence"] = project["confidence"]
        else:
            merged[key] = project
            projects.append(project)
    email_summary = str(data.get("email_summary") or "").strip()[:300]
    if not projects:
        return {
            "intent": "info",
            "title": clean_subject(subject),
            "requirement": re.sub(r"\s+", " ", body).strip()[:300],
            "due": None,
            "due_source": "AI",
            "owner": "",
            "progress": None,
            "done_hint": False,
            "matches": [],
            "confidence": 0.3,
            "actionable": False,
            "summary": email_summary or "没有识别到需要跟进的项目",
            "analyzed_at": model.iso(model.now()),
            "ai": True,
            "projects": [],
        }
    first = projects[0]
    return {
        "intent": "new",
        "title": first["title"],
        "requirement": first["requirement"],
        "due": first["due"],
        "due_source": "AI",
        "owner": first["owner"],
        "progress": None,
        "done_hint": False,
        "matches": [],
        "confidence": first["confidence"],
        "actionable": True,
        "summary": email_summary or first["summary"] or first["requirement"][:90],
        "analyzed_at": model.iso(model.now()),
        "ai": True,
        "projects": projects,
        "email_summary": email_summary,
    }

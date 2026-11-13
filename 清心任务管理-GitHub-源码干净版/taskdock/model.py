# -*- coding: utf-8 -*-
"""Task data model and the rules that keep task/subtask state consistent."""

import re
import uuid
from datetime import datetime, timedelta


class CompletionBlocked(Exception):
    def __init__(self, pending):
        self.pending = pending
        super().__init__("还有 %d 个子任务未完成" % pending)


def now():
    return datetime.now().replace(second=0, microsecond=0)


def new_id(prefix="t"):
    return "%s_%s" % (prefix, uuid.uuid4().hex[:10])


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else None


def parse_dt(value, base=None):
    """Parse the date formats a person is likely to type.

    Returns a naive local datetime, or None when the text cannot be parsed.
    Date-only values use 18:00 because most task deadlines are end-of-day.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(second=0, microsecond=0)
    text = str(value).strip()
    if not text:
        return None
    text = (
        text.replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
        .replace("号", "")
        .replace("：", ":")
        .replace("／", "/")
        .replace("．", ".")
    )
    text = re.sub(r"\s+", " ", text)
    base = base or now()

    formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y/%m/%d %H:%M",
        "%Y.%m.%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            if "%H" not in fmt:
                dt = dt.replace(hour=18, minute=0)
            return dt.replace(second=0, microsecond=0)
        except ValueError:
            pass

    # Month/day without a year: choose the next occurrence if it is far past.
    for fmt in ("%m-%d %H:%M", "%m/%d %H:%M", "%m.%d %H:%M", "%m-%d", "%m/%d", "%m.%d"):
        try:
            dt = datetime.strptime(text, fmt)
            has_time = "%H" in fmt
            dt = dt.replace(year=base.year, hour=dt.hour if has_time else 18, minute=dt.minute)
            if dt < base - timedelta(days=45):
                dt = dt.replace(year=base.year + 1)
            return dt
        except ValueError:
            pass
    return None


def task_start(task):
    return parse_dt(task.get("start"))


def task_due(task):
    return parse_dt(task.get("due"))


def all_subtasks_done(task):
    return all(bool(s.get("done")) for s in task.get("subtasks", []))


def pending_subtasks(task):
    return [s for s in task.get("subtasks", []) if not s.get("done")]


def subtask_stats(task):
    items = task.get("subtasks", [])
    done = len([s for s in items if s.get("done")])
    return done, len(items)


def status_of(task, at=None):
    at = at or now()
    if task.get("completed"):
        return "done"
    if task.get("lost"):
        return "lost"
    due = task_due(task)
    if due and due < at:
        return "overdue"
    start = task_start(task)
    started = bool(start and start <= at)
    touched = int(task.get("progress") or 0) > 0 or subtask_stats(task)[0] > 0
    if start and not started and not touched:
        return "upcoming"
    if started or touched or not start:
        return "doing"
    return "upcoming"


def counts(tasks, at=None):
    at = at or now()
    result = {
        "total": len(tasks),
        "done": 0,
        "active": 0,
        "overdue": 0,
        "today": 0,
        "upcoming": 0,
        "doing": 0,
        "lost": 0,
        "due_soon": 0,
    }
    for task in tasks:
        status = status_of(task, at)
        if status == "done":
            result["done"] += 1
            continue
        if status == "lost":
            result["lost"] += 1
            continue
        result["active"] += 1
        result[status] = result.get(status, 0) + 1
        due = task_due(task)
        if due:
            if due.date() == at.date():
                result["today"] += 1
            if at <= due <= at + timedelta(days=3):
                result["due_soon"] += 1
    result["percent"] = int(round(result["done"] * 100.0 / result["total"])) if result["total"] else 0
    return result


def clamp_progress(value):
    try:
        value = int(round(float(value)))
    except (TypeError, ValueError):
        value = 0
    return max(0, min(100, value))


def set_progress(task, value, at=None):
    """Set progress, enforcing the completion gate.

    ｜ 100% is only possible when every subtask is done. If subtasks remain,
    ｜ the value is capped at 99 so a task never *looks* complete illegally.
    """
    at = at or now()
    value = clamp_progress(value)
    if value >= 100:
        if all_subtasks_done(task):
            value = 100
            task["completed"] = True
            task["completed_at"] = iso(at)
        else:
            value = 99
            task["completed"] = False
            task["completed_at"] = None
    else:
        if task.get("completed"):
            task["completed"] = False
            task["completed_at"] = None
    task["progress"] = value
    task["updated_at"] = iso(at)
    return value


def mark_complete(task, at=None):
    at = at or now()
    pending = len(pending_subtasks(task))
    if pending:
        raise CompletionBlocked(pending)
    task["completed"] = True
    task["completed_at"] = iso(at)
    task["lost"] = False
    task["lost_at"] = None
    task["lost_reason"] = ""
    task["tags"] = [tag for tag in (task.get("tags") or []) if tag != "lost"]
    task["progress"] = 100
    task["updated_at"] = iso(at)
    return task


def mark_lost(task, at=None, reason=""):
    at = at or now()
    task["lost"] = True
    task["lost_at"] = iso(at)
    task["lost_reason"] = (reason or "").strip()[:500]
    task["completed"] = False
    task["completed_at"] = None
    task["progress"] = 100
    task["updated_at"] = iso(at)
    return task


def reopen_lost(task, at=None):
    at = at or now()
    task["lost"] = False
    task["lost_at"] = None
    task["lost_reason"] = ""
    if int(task.get("progress") or 0) >= 100:
        task["progress"] = 90
    task["updated_at"] = iso(at)
    return task


def reopen(task, at=None):
    at = at or now()
    task["completed"] = False
    task["completed_at"] = None
    if int(task.get("progress") or 0) >= 100:
        task["progress"] = 90
    task["updated_at"] = iso(at)
    return task


def toggle_subtask(task, subtask_id, at=None):
    at = at or now()
    for sub in task.get("subtasks", []):
        if sub.get("id") == subtask_id:
            sub["done"] = not bool(sub.get("done"))
            sub["done_at"] = iso(at) if sub["done"] else None
            break
    else:
        return task
    if task.get("completed") and not all_subtasks_done(task):
        task["completed"] = False
        task["completed_at"] = None
        task["progress"] = min(int(task.get("progress") or 0), 95)
    elif all_subtasks_done(task) and not task.get("completed"):
        # Nudge progress forward, but completion still needs an explicit 100%.
        done, total = subtask_stats(task)
        if total:
            task["progress"] = max(int(task.get("progress") or 0), min(99, int(done * 100.0 / total)))
    task["updated_at"] = iso(at)
    return task


def add_subtask(task, title, start=None, due=None, owner="", owner_username="",
                requirement="", at=None):
    title = (title or "").strip()
    if not title:
        return None
    sub = {
        "id": new_id("s"),
        "title": title,
        "requirement": (requirement or "").strip()[:2000],
        "done": False,
        "done_at": None,
        "start": iso(parse_dt(start)) if start else None,
        "due": iso(parse_dt(due)) if due else None,
        "owner": (owner or "").strip(),
        "owner_username": (owner_username or "").strip(),
        "created_at": iso(at or now()),
    }
    task.setdefault("subtasks", []).append(sub)
    task["updated_at"] = iso(at or now())
    if not all_subtasks_done(task) and task.get("completed"):
        task["completed"] = False
        task["completed_at"] = None
        task["progress"] = min(int(task.get("progress") or 0), 95)
    return sub


def remove_subtask(task, subtask_id, at=None):
    before = len(task.get("subtasks", []))
    task["subtasks"] = [s for s in task.get("subtasks", []) if s.get("id") != subtask_id]
    task["updated_at"] = iso(at or now())
    if task.get("completed") and not all_subtasks_done(task):
        task["completed"] = False
        task["completed_at"] = None
        task["progress"] = min(int(task.get("progress") or 0), 95)
    return len(task["subtasks"]) != before


TAG_META = {
    "warning": ("预警", "amber", "amber_soft"),
    "lost": ("流失", "danger", "danger_soft"),
    "follow": ("跟进", "blue", "blue_soft"),
}
TAG_KEYS = tuple(TAG_META)


def clean_tags(tags):
    if not isinstance(tags, (list, tuple, set)):
        return []
    result = []
    for tag in tags:
        value = str(tag or "").strip().lower()
        if value in TAG_META and value not in result:
            result.append(value)
    return result


def create_task(title, requirement="", cycle="一次性", start=None, due=None,
                owner="", owner_username="", progress=0, subtasks=None, note="", tags=None):
    at = now()
    start_dt = parse_dt(start) or at
    due_dt = parse_dt(due) or (start_dt + timedelta(days=7)).replace(hour=18, minute=0)
    task = {
        "id": new_id(),
        "title": (title or "").strip() or "未命名任务",
        "requirement": (requirement or "").strip(),
        "cycle": cycle or "一次性",
        "start": iso(start_dt),
        "due": iso(due_dt),
        "owner": (owner or "").strip(),
        "owner_username": (owner_username or "").strip(),
        "progress": 0,
        "completed": False,
        "completed_at": None,
        "lost": False,
        "lost_at": None,
        "lost_reason": "",
        "revision": 0,
        "subtasks": [],
        "notes": [],
        "email_ids": [],
        "tags": clean_tags(tags),
        "created_at": iso(at),
        "updated_at": iso(at),
        "demo": False,
    }
    if note:
        task["notes"].append({"at": iso(at), "text": note})
    for item in subtasks or []:
        if isinstance(item, dict):
            add_subtask(task, item.get("title"), item.get("start"), item.get("due"),
                        item.get("owner"), item.get("owner_username"),
                        requirement=item.get("requirement") or "")
            if item.get("done"):
                task["subtasks"][-1]["done"] = True
        else:
            add_subtask(task, str(item))
    set_progress(task, progress, at)
    return task


def add_note(task, text, email_id=None, at=None):
    text = (text or "").strip()
    if not text:
        return
    task.setdefault("notes", []).append({
        "at": iso(at or now()),
        "text": text,
        "email_id": email_id,
    })
    task["updated_at"] = iso(at or now())


def link_email(task, email_id):
    ids = task.setdefault("email_ids", [])
    if email_id and email_id not in ids:
        ids.append(email_id)
        task["updated_at"] = iso(now())


def sort_tasks(tasks):
    """Active tasks first, nearest deadline first; completed tasks last."""
    def key(task):
        status = status_of(task)
        done_rank = 1 if status in ("done", "lost") else 0
        due = task_due(task)
        due_rank = due.timestamp() if due else 9999999999
        return (done_rank, due_rank, task.get("created_at") or "")

    return sorted(tasks, key=key)


def filter_tasks(tasks, key):
    if key == "all":
        return list(tasks)
    if key == "doing":
        return [t for t in tasks if status_of(t) in ("doing", "todo")]
    if key == "lost":
        return [t for t in tasks if t.get("lost") or "lost" in (t.get("tags") or [])]
    return [t for t in tasks if status_of(t) == key]


def is_same_day(a, b):
    return bool(a and b and a.date() == b.date())


def due_text(task, at=None):
    at = at or now()
    if task.get("lost"):
        lost = parse_dt(task.get("lost_at"))
        return "流失于 %s" % (lost.strftime("%m/%d") if lost else "已流失")
    if task.get("completed"):
        done = parse_dt(task.get("completed_at"))
        return "完成于 %s" % (done.strftime("%m/%d") if done else "已归档")
    due = task_due(task)
    if not due:
        return "未设截止"
    delta = (due.date() - at.date()).days
    time_part = due.strftime("%H:%M")
    if delta < 0:
        return "逾期 %d 天" % abs(delta)
    if delta == 0:
        return "今天 %s" % time_part
    if delta == 1:
        return "明天 %s" % time_part
    if delta <= 6:
        week = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][due.weekday()]
        return "%s %s" % (week, time_part)
    return "%s %s" % (due.strftime("%m/%d"), time_part)


def due_tone(task):
    status = status_of(task)
    if status == "lost":
        return "danger"
    if status == "done":
        return "muted"
    due = task_due(task)
    if not due:
        return "muted"
    delta = (due.date() - now().date()).days
    if delta < 0:
        return "danger"
    if delta <= 1:
        return "amber"
    return "muted"


def duration_text(task):
    start, due = task_start(task), task_due(task)
    if not start or not due:
        return ""
    days = (due - start).days
    if days <= 0:
        return "当天"
    return "%d 天" % days


def progress_text(task):
    done, total = subtask_stats(task)
    if total:
        return "%d/%d" % (done, total)
    return "无子任务"


def normalize_task(task):
    """Repair task dictionaries loaded from older or hand-edited JSON."""
    task.setdefault("id", new_id())
    task.setdefault("title", "未命名任务")
    task.setdefault("requirement", "")
    task.setdefault("cycle", "一次性")
    task.setdefault("start", iso(now()))
    task.setdefault("due", iso(now() + timedelta(days=7)))
    task.setdefault("owner", "")
    task.setdefault("owner_username", "")
    if task.get("source_email_id") and not task.get("owner_username"):
        # AI/email tasks must not keep a name that has no account.
        task["owner"] = "待指派"
    task["progress"] = clamp_progress(task.get("progress", 0))
    task.setdefault("completed", False)
    task.setdefault("completed_at", None)
    task.setdefault("lost", False)
    task.setdefault("lost_at", None)
    task.setdefault("lost_reason", "")
    task.setdefault("revision", 0)
    if task.get("lost"):
        task["completed"] = False
        task["completed_at"] = None
    task.setdefault("subtasks", [])
    for sub in task["subtasks"]:
        if isinstance(sub, dict):
            sub.setdefault("requirement", "")
    task.setdefault("notes", [])
    task.setdefault("email_ids", [])
    task["tags"] = clean_tags(task.get("tags"))
    if task.get("lost"):
        if "lost" not in task["tags"]:
            task["tags"].append("lost")
        task["completed"] = False
    elif "lost" in task["tags"]:
        # Migrate the old tag-only loss marker to a real lost state.
        task["lost"] = True
        task["lost_at"] = task.get("lost_at") or task.get("updated_at") or iso(now())
        task["completed"] = False
        task["completed_at"] = None
    task.setdefault("share_group_id", None)
    task.setdefault("source", "local")
    task.setdefault("archived", False)
    task.setdefault("received_from", None)
    task.setdefault("transferred_to", None)
    task.setdefault("created_at", iso(now()))
    task.setdefault("updated_at", task.get("created_at"))
    for sub in task["subtasks"]:
        sub.setdefault("id", new_id("s"))
        sub.setdefault("title", "子任务")
        sub["done"] = bool(sub.get("done"))
        sub.setdefault("done_at", None)
        sub.setdefault("start", None)
        sub.setdefault("due", None)
        sub.setdefault("owner", "")
        sub.setdefault("owner_username", "")
    if task.get("completed") and not all_subtasks_done(task):
        # A stale hand-edited file must not break the core completion rule.
        task["completed"] = False
        task["completed_at"] = None
        task["progress"] = min(task["progress"], 95)
    if task.get("completed") or task.get("lost"):
        task["progress"] = 100
    elif task["progress"] >= 100:
        # A non-completed task may not display 100%; completion is gated by
        # subtasks and must be explicit.
        task["progress"] = 99
    return task

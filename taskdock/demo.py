# -*- coding: utf-8 -*-
"""First-run sample data. Everything is local and can be cleared in Settings."""

from datetime import datetime, timedelta

from . import model


def _at(days=0, hour=18, minute=0):
    base = datetime.now().replace(second=0, microsecond=0)
    return (base + timedelta(days=days)).replace(hour=hour, minute=minute)


def _cn_date(dt):
    return "%d月%d日 %02d:%02d" % (dt.month, dt.day, dt.hour, dt.minute)


def _task(title, requirement, cycle, start, due, owner, progress, subs, demo=True):
    task = model.create_task(
        title=title,
        requirement=requirement,
        cycle=cycle,
        start=start,
        due=due,
        owner=owner,
        progress=0,
    )
    for text, done in subs:
        model.add_subtask(task, text)
        if done:
            task["subtasks"][-1]["done"] = True
            task["subtasks"][-1]["done_at"] = model.iso(model.now())
    model.set_progress(task, progress)
    task["demo"] = demo
    return task


def seed_data():
    t1 = _task(
        "Q4 品牌发布会方案",
        "完成主视觉、场地与嘉宾邀约，11 月 5 日前提交最终执行方案，预算控制在 80 万以内。",
        "一次性",
        _at(-9, 9, 30),
        _at(3, 18, 0),
        "林夏",
        65,
        [
            ("确认发布会主题与主视觉方向", True),
            ("锁定场地并完成合同审批", True),
            ("确认嘉宾名单与出席意向", True),
            ("输出完整执行方案与预算表", False),
            ("内部评审并完成终版定稿", False),
        ],
    )
    t2 = _task(
        "每周经营数据复盘",
        "汇总上周 GMV、转化率与投放 ROI，输出复盘结论并在周会上同步。",
        "每周",
        _at(-5, 9, 0),
        _at(1, 17, 0),
        "陈默",
        40,
        [
            ("导出各渠道经营数据", True),
            ("完成异常指标归因", False),
            ("输出周会复盘页", False),
        ],
    )
    t3 = _task(
        "供应商合同续签",
        "完成三家核心供应商的续签谈判，法务条款需在到期前确认完毕。",
        "一次性",
        _at(-18, 10, 0),
        _at(-3, 18, 0),
        "周然",
        20,
        [
            ("收集供应商报价与资质", True),
            ("法务确认违约与保密条款", False),
        ],
    )
    t4 = _task(
        "新版官网文案定稿",
        "完成首页、产品页与品牌故事三套文案，并交付给设计团队。",
        "一次性",
        _at(-12, 9, 0),
        _at(-1, 16, 0),
        "苏禾",
        100,
        [
            ("首页主文案", True),
            ("产品页功能描述", True),
            ("品牌故事长文", True),
        ],
    )
    model.mark_complete(t4, _at(-1, 15, 30))

    t5 = _task(
        "客户成功案例访谈",
        "完成三家标杆客户的访谈与授权，沉淀可对外发布的案例素材。",
        "一次性",
        _at(2, 10, 0),
        _at(8, 18, 0),
        "林夏",
        0,
        [
            ("确认访谈客户名单", False),
            ("完成访谈提纲", False),
            ("回收授权书与素材", False),
        ],
    )

    due1 = _at(3, 18, 0)
    due2 = _at(6, 17, 0)
    due3 = _at(1, 12, 0)
    emails = [
        {
            "id": "mail_demo_1",
            "uid": "demo-1",
            "subject": "关于 Q4 品牌发布会方案的三点确认",
            "sender": "林夏",
            "sender_email": "linxia@example.com",
            "date": model.iso(_at(0, 9, 12)),
            "body": (
                "Hi，\n\n"
                "关于 Q4 品牌发布会方案，请在 %s 前确认以下三点：\n"
                "1. 舞台尺寸调整为 12m × 6m，是否影响主视觉延展；\n"
                "2. 嘉宾名单新增两位行业媒体主编，需要同步制作桌牌；\n"
                "3. 执行方案与预算表请在评审前发我。\n\n"
                "目前整体方案进度约 70%%，负责人：林夏。\n"
                "辛苦了。\n" % _cn_date(due1)
            ),
            "snippet": "请在截止前确认舞台尺寸、嘉宾名单，并同步执行方案与预算表。",
            "read": False,
            "analysis": None,
            "demo": True,
            "folder": "INBOX",
        },
        {
            "id": "mail_demo_2",
            "uid": "demo-2",
            "subject": "请协助准备供应商合规材料",
            "sender": "采购中心",
            "sender_email": "procurement@example.com",
            "date": model.iso(_at(-1, 14, 20)),
            "body": (
                "周然，你好：\n\n"
                "根据年度供应商复核要求，请于 %s 前提交三家核心供应商的合规材料，"
                "包括营业执照、授权书与最近一期审计报告。\n"
                "材料请统一命名后上传至采购共享盘，并在邮件中回复确认。\n\n"
                "如有问题请及时沟通。\n" % _cn_date(due2)
            ),
            "snippet": "请于截止前提交三家核心供应商的合规材料，并回复确认。",
            "read": False,
            "analysis": None,
            "demo": True,
            "folder": "INBOX",
        },
        {
            "id": "mail_demo_3",
            "uid": "demo-3",
            "subject": "回复: 供应商合同续签",
            "sender": "法务部 · 顾言",
            "sender_email": "legal@example.com",
            "date": model.iso(_at(-1, 17, 5)),
            "body": (
                "周然，\n\n"
                "合同里的违约与保密条款需要再确认一版，请务必在 %s 前反馈法务。\n"
                "另外，供应商资质文件还缺一份盖章版，请一并补齐。\n\n"
                "顾言\n" % _cn_date(due3)
            ),
            "snippet": "违约与保密条款需要再确认，请截止前反馈，并补齐盖章资质。",
            "read": True,
            "analysis": None,
            "demo": True,
            "folder": "INBOX",
        },
        {
            "id": "mail_demo_4",
            "uid": "demo-4",
            "subject": "本周经营数据已生成",
            "sender": "数据平台",
            "sender_email": "noreply@example.com",
            "date": model.iso(_at(-2, 8, 0)),
            "body": (
                "本周经营数据报表已生成，可在数据平台查看。\n"
                "本邮件由系统自动发送，请勿直接回复。\n"
            ),
            "snippet": "本周经营数据报表已生成，可在数据平台查看。",
            "read": True,
            "analysis": None,
            "demo": True,
            "folder": "INBOX",
        },
    ]
    return {
        "version": 1,
        "tasks": [t1, t2, t3, t4, t5],
        "emails": emails,
        "settings": default_settings(),
    }


def default_settings():
    return {
        "account": "",
        "mail_password": "",
        "imap_host": "imap.em.dingtalk.com",
        "imap_port": 993,
        "days": 14,
        "ai_enabled": False,
        "ai_endpoint": "https://api.openai.com/v1/chat/completions",
        "ai_model": "gpt-4o-mini",
        "ai_api_key": "",
        "auto_sync": False,
        "topmost": True,
        "dock_right": True,
        "window_x": None,
        "window_y": None,
        "last_sync": None,
        "last_sync_error": "",
        "collab_server": "http://127.0.0.1:8787",
        "collab_token": "",
        "collab_user_id": None,
        "collab_username": "",
        "collab_display_name": "",
        "collab_role": "member",
        "collab_last_sync": None,
        "library": "inbox",
        "seen_intro": False,
        "demo_cleaned_version": 0,
    }

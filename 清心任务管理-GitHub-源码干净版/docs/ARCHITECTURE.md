# 架构说明

## 组件

| 组件 | 目录 | 职责 |
| --- | --- | --- |
| Windows 客户端 | `taskdock/` | 任务、子任务、邮件、AI、好友、共享、私聊 |
| 管理服务 | `taskdock_server/` | 认证、任务同步、共享组、编辑锁、消息、管理 API |
| 管理端 Web | `taskdock_server/templates` / `static` | 账户、任务池、洞察、消息中心 |
| 测试 | `tests/` | 模型、解析、服务端 API、桌面 UI |

## 数据流

### 客户端启动

```text
读取 %APPDATA%\TaskDock\data.json
  → 修复旧数据（normalize_task）
  → 启动 Tkinter
  → 10 秒心跳 / 手动状态更新
```

### 任务与管理端

```text
客户端本地任务
  → 手动「状态更新」或管理端「主动更新任务」
  → POST /api/sync
  → SQLite tasks
  → GET /api/admin/overview
  → 管理端任务池 / 统计 / 洞察
```

### 共享任务

```text
A 共享任务
  → offers pending
  → B 接受
  → 创建 B 副本，share_group_id 相同
  → A 编辑保存
  → /api/tasks/shared/update
  → 全字段写回 group 所有副本，revision + 1
  → B 状态更新后获得新 revision
```

### 编辑锁

```text
POST /api/locks/acquire  { scope: "group:g_xxx" }
  → task_locks
  → 返回当前 revision
POST /api/locks/release
  → 删除锁
```

### 好友私聊

```text
POST /api/friends/messages/send
  → messages(thread_key = "minId:maxId")
GET /api/friends/messages?friend_id=
  → 双方消息
```

私聊 `thread_key` 非空，管理端任务消息线程、客户端任务消息和未读查询均过滤这类记录。

## 数据模型摘要

### tasks

```text
user_id, task_id, title, requirement, cycle, start, due,
owner, owner_username, progress, completed,
lost, lost_at, lost_reason, revision,
subtasks_json, notes_json, tags_json,
share_group_id, source, archived, received_from, transferred_to,
updated_at, created_at
```

### offers

```text
from_id, to_id, mode(share|transfer), status(pending|accepted|declined),
task_id, task_snapshot, share_group_id, message,
created_at, responded_at, accepted_task_id
```

### messages

```text
from_id, to_id, task_user_id, task_id, task_title,
thread_key, body, created_at, read_at
```

- `thread_key` 为空：任务沟通
- `thread_key` 非空：好友私聊

### task_locks

```text
scope, user_id, user_name, locked_at, expires_at
```

## 关键规则

- 任务完成需要所有子任务完成；100% 完成必须显式设置。
- 任务流失是终态，与完成互斥。
- 共享任务保存必须持有编辑锁，且 `base_revision` 与服务端一致。
- 共享任务编辑保存后 revision 递增。
- 管理端汇聚按 `share_group_id` 优先，标题关键词兜底。
- 私聊不进入管理端消息中心。
- 任务删除后历史消息仍保留，管理端只读查看。

## 构建

```text
PyInstaller
  ├─ TaskDock.exe         windowed
  └─ TaskDockServer.exe   console
```

发布包目录：

```text
清心任务管理/
├── 主管理端/
│   └── 清心任务管理终端/
└── 子客户端/
    └── 清心任务客户端/
```

# AI 周报梳理

## 目标

把钉钉邮件、工作周报、项目汇报整理成可跟踪的任务，并在本周与上一期之间对比差异，辅助用户决定是否新增子任务。

## 处理流程

```text
邮件正文
  │
  ├─ 本地规则：标题、截止时间、负责人、行动项、完成提示
  └─ 可选 AI：项目拆解、背景/进展/情况/要求/交付物
        │
        ▼
项目列表
  │
  ├─ 与已有任务匹配：new / update / subtask / unrelated
  ├─ 与上一期周报邮件对比
  └─ 输出 changes / suggest_subtask / subtask_title
        │
        ▼
AI 项目梳理窗口
  ├─ 新建任务
  ├─ 追加到现有任务
  ├─ 作为子任务
  └─ 忽略
```

## 输出字段

每个项目包含：

| 字段 | 说明 |
| --- | --- |
| `title` | 项目 / 事项名称 |
| `summary` | 一句话当前情况 |
| `background` | 背景、客户、合同、金额、干系人 |
| `progress` | 已完成进展、阶段、交付/签约/获奖 |
| `situation` | 当前推进、卡点、风险、待决策 |
| `requirement` | 本次明确要求 |
| `deliverable` | 交付物 / 验收标准 |
| `status` | 进行中 / 已签约 / 待签约 / 已完成 / 暂停 / 商机 |
| `contract_amount` | 合同金额 |
| `next_action` | 下一步动作 |
| `due` | 截止时间 |
| `owner` | 负责人 |
| `action_items` | 行动项数组 |
| `relation` | new / update / subtask / unrelated |
| `target_task_id` | 已有任务 id |
| `changes` | 与上一期相比的差异点 |
| `suggest_subtask` | 是否建议新增子任务 |
| `subtask_title` | 建议子任务标题 |
| `match_reason` | 匹配原因 |
| `confidence` | 置信度 0–1 |

## 差异子任务

用户在「AI 项目梳理」中勾选：

```text
☐ 将差异添加为子任务
```

保存时会创建子任务：

```text
子任务标题
补充验收材料

子任务内容
本期差异：
• 新增验收材料要求
• 完成时间推迟到下周

相关要求：
补充新的验收材料并重新提交
```

## 历史项目

- 已创建 / 未创建 / 已忽略的项目记录永久保留。
- 任务被删除后，AI 项目记录仍保留，并标记“任务已删除”。
- 复扫不会把已处理项目强制退回为未建立。

## 配置

管理端 / 客户端「AI 设置」支持：

- OpenAI
- DeepSeek
- 智谱 GLM
- 通义千问
- 自定义 OpenAI 兼容接口

API Key 使用 Windows DPAPI 保存。

## 注意

AI 结果可能不准确，涉及合同、金额、客户承诺和正式交付日期时，必须人工复核。

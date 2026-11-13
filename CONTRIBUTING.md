# 贡献指南

感谢你愿意参与清心任务管理项目。

## 开始之前

1. 先阅读 `README.md` 和 `SKILL.md`，了解已有需求基线。
2. 不要删除或静默降级已经验收的功能；新增需求应追加，并记录变更原因。
3. 不要提交任何真实账号、邮箱、API Key、客户数据、`data.json` 或 `server.db`。
4. 涉及数据结构的改动必须同时考虑旧数据迁移。

## 开发环境

- Python 3.8+
- Windows 10/11（桌面客户端）
- Tkinter（官方 Windows Python 自带）
- SQLite（Python 标准库自带）

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -q
```

## 分支与提交

建议使用简短的英文分支名：

```text
feat/shared-task-sync
fix/deleted-task-chat
docs/github-readme
```

提交信息建议：

```text
feat: sync all fields for shared tasks
fix: keep deleted task chat history readable
docs: add GitHub upload materials
test: cover duplicate share guard
```

## 提交前检查

```powershell
# 1. 全部测试
$env:PYTHONIOENCODING='utf-8'
python -m unittest discover -s tests -q

# 2. 语法检查
python -m py_compile taskdock/*.py taskdock_server/*.py

# 3. 前端 JS 语法检查（如安装了 Node.js）
node --check taskdock_server/static/admin.js

# 4. 确认没有敏感文件
git status
git diff --cached
```

## 代码约定

- 使用 Python 3.8 兼容语法。
- 客户端基于 Tkinter，不要引入重量级 UI 框架。
- 服务端优先使用标准库；新增依赖需说明原因。
- 任务模型变更必须兼容旧 `data.json` 和旧 `server.db`。
- 所有新增交互至少补一个自动化测试。
- 管理端前端保持原生 HTML/CSS/JS，不引入构建链，除非有明确必要。

## Pull Request

PR 描述请包含：

- 需求背景
- 修改内容
- 影响的端（客户端 / 服务端 / 两端）
- 测试结果
- 截图（涉及 UI 时）
- 数据迁移说明（涉及字段时）

## 安全

不要在 Issue、PR、日志或截图中暴露：

- API Key
- 邮箱账号 / 密码
- DPAPI 密文
- 真实客户名称、合同金额、内部邮件正文
- `%APPDATA%\TaskDock` 或 `%APPDATA%\TaskDockServer` 的原始数据

安全问题请按 `SECURITY.md` 私下报告。

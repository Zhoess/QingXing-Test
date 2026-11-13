# 清心任务管理 · TaskDock

> 面向政务与项目型团队的 Windows 任务协作系统：桌面任务面板 + 管理端任务池 + 好友协作 + AI 周报梳理。

![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows&logoColor=white)
![Storage](https://img.shields.io/badge/Storage-SQLite-003B57?logo=sqlite&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-97%20passed-2E7D32)
![Version](https://img.shields.io/badge/Version-2.0.0-B35A3D)

清心任务管理由两端组成：

- **清心任务客户端**：Windows 桌面常驻面板，负责任务、子任务、钉钉邮件、AI 项目梳理、好友私聊、任务共享与转交。
- **清心任务管理终端**：Web 管理控制台，负责账户、组织架构、全局任务池、任务汇聚、统计洞察和消息中心。

两端通过一个自托管的 HTTP 服务交换数据，数据默认保存在本机 SQLite。

---

## 核心能力

### 任务管理

- 新建、编辑、删除、完成、恢复、流失任务。
- 任务标题、要求、周期、开始/截止时间、负责人、标签、进度、子任务、记录。
- 完成与流失都是终态：完成后灰色沉底，流失后红色沉底并显示流失时间。
- 流失必须填写原因，管理端可查看；恢复后清空流失状态。
- 子任务独立维护标题、内容、负责人、起止时间和完成状态。
- 任务搜索、状态筛选、日期跨度筛选、标签筛选。
- 已完成 / 已流失任务在客户端和管理端都自动沉底。

### 协作网络

- 账号登录、好友申请、好友列表、接收箱。
- **共享协作**：双方保留任务副本，继续共同推进。
- **转交任务**：接收方获得任务，原端自动归档。
- 一次可勾选多个任务转发给同一好友。
- 同一任务不会重复共享给同一好友。
- 好友私聊与任务沟通隔离，私聊不回传管理端。
- 共享任务全字段同步：标题、要求、负责人、截止时间、周期、进度、子任务、标签、记录。
- 共享任务编辑锁 + 版本号校验，避免两个人同时编辑和旧副本覆盖新内容。
- 管理端按共享组和标题关键词汇聚多客户端副本，同一项目只展示一行。

### AI 邮件与周报

- 支持 OpenAI、DeepSeek、智谱 GLM、通义千问及兼容 Chat Completions 的自定义服务。
- 从钉钉邮件中识别项目、阶段、要求、交付物、负责人和截止时间。
- 周报按项目名称合并去重，生成项目任务草稿。
- 本周周报分析会结合已有任务和上一期周报邮件，列出差异点。
- 用户可勾选「将差异添加为子任务」，按建议标题挂到现有任务下。
- AI 项目历史永久保留；任务删除或完成后仍保留项目记录。

### 管理端

- 账户创建、编辑、停用、重置密码、删除。
- 组织架构与负责人范围。
- 全局任务池：状态、成员、组织、标签、截止范围筛选。
- 任务汇聚：共享副本只算一行，统计不重复。
- 总览 KPI：账户、任务、完成率、已流失、逾期、临期、待处理邀请。
- 规则洞察：逾期、临期、停滞、待指派、流失风险。
- 任务消息中心：按任务与负责人沟通；任务删除后仍可只读查看历史。
- 管理端 5 秒轮询；「主动更新任务」触发在线客户端手动同步。

---

## 架构

```text
┌────────────────────────────────────────────┐
│        清心任务管理终端（Web Console）        │
│  账户 / 组织 / 任务池 / 洞察 / 消息中心       │
└──────────────────────┬─────────────────────┘
                       │ HTTP API
┌──────────────────────┴─────────────────────┐
│        TaskDock Server（Python + SQLite）    │
│  认证 / 任务同步 / 共享组 / 编辑锁 / 消息     │
└───────────────┬──────────────────┬─────────┘
                │                  │
      ┌─────────┴────────┐  ┌──────┴─────────┐
      │ 清心任务客户端 A  │  │ 清心任务客户端 B │
      │ Windows / Tkinter│  │ Windows / Tkinter│
      └──────────────────┘  └────────────────┘
```

### 技术栈

- Python 3.8+
- Tkinter（Windows 桌面客户端）
- 标准库 `ThreadingHTTPServer` + SQLite（管理服务）
- 原生 HTML / CSS / JavaScript（管理端）
- PyInstaller（Windows 打包）
- 可选：`beautifulsoup4`、`pywin32`（DPAPI）

---

## 快速开始

### 方式一：使用发布包

1. 从 GitHub Releases 下载 `清心任务管理-v2.0-win64-整合包-*.zip`。
2. 解压后进入 `主管理端`，运行 `清心任务管理终端.exe`。
3. 本机浏览器打开 `http://127.0.0.1:8787/admin`，创建管理账号。
4. 在「账户」中创建成员账号。
5. 进入 `子客户端`，运行 `清心任务客户端.exe`。
6. 在客户端「协作网络」中填写服务地址，例如 `http://192.168.1.20:8787`，登录即可。

> 首次使用只能在本机浏览器打开管理端完成初始化。

### 方式二：源码运行

```powershell
git clone https://github.com/<YOUR_GITHUB>/<YOUR_REPO>.git
cd <YOUR_REPO>

python -m pip install -r requirements.txt

# 启动管理服务
python -m taskdock_server --host 0.0.0.0 --port 8787

# 另开终端，启动客户端
python app.py
```

管理端默认地址：

```text
http://127.0.0.1:8787/admin
```

---

## 构建 Windows 包

```powershell
# 客户端
python -m PyInstaller --noconfirm --clean --windowed --onedir `
  --name TaskDock --icon assets/icon.ico `
  --add-data "assets;assets" app.py

# 管理端
python -m PyInstaller --noconfirm --clean --console --onedir `
  --name TaskDockServer `
  --add-data "taskdock_server/templates;taskdock_server/templates" `
  --add-data "taskdock_server/static;taskdock_server/static" `
  server_main.py
```

产物：

```text
dist/TaskDock/           客户端
dist/TaskDockServer/     管理端
```

---

## 测试

```powershell
$env:PYTHONIOENCODING='utf-8'
python -m unittest discover -s tests -q
```

当前基线：**97 个测试全部通过**。

测试覆盖：

- 任务 / 子任务规则
- 完成、流失、恢复、时间与筛选
- 邮件解析与本地规则分析
- AI 周报差异与子任务内容
- 认证、权限、好友、共享、转交
- 管理端任务汇聚、编辑锁、版本同步
- 私聊隔离与历史消息
- 桌面 UI 关键流程

---

## 目录结构

```text
.
├── app.py                      客户端入口
├── server_main.py              管理端入口
├── taskdock/                   客户端源码
│   ├── model.py                任务模型与规则
│   ├── store.py                本地数据与同步合并
│   ├── analyzer.py             邮件 / AI 分析
│   ├── page_tasks.py           任务页、编辑器、子任务
│   ├── page_mail.py            邮件、AI 项目梳理
│   ├── page_collab.py          好友、私聊、共享/转交
│   ├── ui_app.py               客户端主应用
│   └── ...
├── taskdock_server/            管理服务
│   ├── app.py                  HTTP API
│   ├── db.py                   SQLite / 认证 / 任务 / 锁 / 消息
│   ├── templates/admin.html    管理端页面
│   └── static/                 管理端 JS / CSS
├── tests/                      自动化测试
├── assets/                     图标等资源
├── requirements.txt
└── README.md
```

---

## 数据与安全

- 客户端数据：`%APPDATA%\TaskDock\data.json`
- 服务端数据：`%APPDATA%\TaskDockServer\server.db`
- 邮件密码可选使用 Windows DPAPI 加密；未使用 DPAPI 时只使用本地编码回退。
- AI API Key 使用 DPAPI 保存，不写入源码、日志或发布包。
- 不要把 `data.json`、`server.db`、`.env`、API Key 或邮箱密码提交到 Git。
- 跨公网部署时请使用 HTTPS 反向代理或 VPN，并放行所需端口。
- 生产环境请定期备份 SQLite 数据库。

详细说明见 [SECURITY.md](SECURITY.md)。

---

## 协作模型

### 共享 vs 转交

| | 共享协作 | 转交任务 |
| --- | --- | --- |
| 原端任务 | 保留 | 归档 |
| 接收端 | 生成共享副本 | 生成接收任务 |
| 共享组 | 有 | 无 |
| 后续同步 | 全字段同步 | 不双向同步 |
| 适用场景 | 共同推进 | 换负责人 |

### 编辑锁与版本

1. A 打开共享任务编辑器，服务端加锁。
2. B 可以查看任务，但点击编辑会被提示「A 账户编辑中，请稍后更新重试」。
3. A 保存后，服务端把标题、要求、负责人、截止时间等全字段写回所有副本，并递增 `revision`。
4. B 未同步就点编辑，会提示「任务已更新，请先点状态更新后再编辑」。
5. B 点击「状态更新」，拉取最新 revision 和字段后即可编辑。

更多细节见 [docs/COLLABORATION.md](docs/COLLABORATION.md)。

---

## AI 周报梳理

```text
钉钉邮件 / 周报
      │
      ▼
本地规则 + 可选 AI 分析
      │
      ├── 项目背景 / 进展 / 情况 / 要求 / 交付物
      ├── 与已有任务的差异 changes
      └── suggest_subtask / subtask_title
      │
      ▼
AI 项目梳理窗口
      │
      ├── 新建任务
      ├── 追加到现有
      ├── 作为子任务
      └── 忽略
```

周报差异子任务会同时保存标题和内容，内容包含差异点与相关要求。

更多细节见 [docs/AI_WEEKLY_REPORT.md](docs/AI_WEEKLY_REPORT.md)。

---

## 开发基线

- 版本：`2.0.0`
- 基线：`baseline-54`
- 测试：`97`
- 客户端：Python 3.8 / Tkinter / Windows
- 管理端：Python 3.8 / SQLite / 原生 Web
- 当前不包含云托管服务，部署即自托管

---

## 已知边界

- 共享任务不是实时协同文档，依赖手动「状态更新」和管理端主动收取。
- 管理端汇聚采用共享组优先、标题关键词相似度兜底；极端同名项目需要人工确认。
- AI 分析质量取决于模型和邮件内容，重要结论仍需人工复核。
- 当前发布包面向 Windows；服务端可运行在 Python 支持的平台。

---

## 参与贡献

欢迎提交 Issue 和 Pull Request。开始前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 安全

如发现安全问题，请阅读 [SECURITY.md](SECURITY.md)，不要在公开 Issue 中提交密钥、账号或数据库。

## 许可证

本项目采用 **All Rights Reserved（保留所有权利）** 的专有许可。未经授权，不得复制、分发或用于商业用途。若你希望以开源方式发布，请将 [LICENSE](LICENSE) 替换为 MIT、Apache-2.0 等许可证。

---

## 致谢

感谢所有参与需求验收、测试和现场使用的同事。

如果这个项目对你有帮助，欢迎点一个 Star。



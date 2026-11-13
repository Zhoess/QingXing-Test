# 部署指南

## 1. 环境要求

- Windows 10/11（客户端与管理端发布包）
- 或 Python 3.8+（源码运行）
- 局域网内可访问的服务器 / 主机
- 建议 2 GB 以上内存，预留 SQLite 数据目录空间

## 2. 启动管理端

源码：

```powershell
python -m taskdock_server --host 0.0.0.0 --port 8787
```

发布包：

```text
主管理端\清心任务管理终端.exe
```

首次启动后，在本机浏览器打开：

```text
http://127.0.0.1:8787/admin
```

按页面提示创建最高管理员账号。

## 3. 防火墙

允许局域网访问 8787 端口：

```powershell
New-NetFirewallRule -DisplayName "TaskDock Server 8787" `
  -Direction Inbound -Protocol TCP -LocalPort 8787 -Action Allow
```

生产环境建议只允许指定网段访问。

## 4. HTTPS 反向代理

不要直接把 8787 暴露到公网。推荐 Nginx / Caddy / IIS 做 HTTPS，并将请求转发到本机 8787。

Caddy 示例：

```caddyfile
task.example.com {
    reverse_proxy 127.0.0.1:8787
}
```

## 5. 客户端连接

在客户端「协作网络」中填写：

```text
https://task.example.com
```

不要填写 `/admin`。

## 6. 数据与备份

- 管理端数据库：`%APPDATA%\TaskDockServer\server.db`
- 客户端数据：`%APPDATA%\TaskDock\data.json`

备份建议：

1. 停止管理端服务，或使用 SQLite 在线备份。
2. 复制 `server.db` 到受控备份目录。
3. 不要将备份提交到 Git。
4. 定期验证恢复流程。

## 7. 升级

1. 备份 `server.db`。
2. 停止旧服务。
3. 替换管理端程序目录。
4. 启动新服务，确认数据库迁移成功。
5. 更新客户端。
6. 抽查任务、账号、消息、共享任务和历史对话。

## 8. 反向代理注意事项

- 保证 WebSocket 不必须；本项目使用 HTTP 轮询与请求。
- 增加请求体大小限制以容纳任务/邮件同步数据。
- 配置合理的超时（建议 60 秒以上）。
- 保留 `X-Forwarded-For` 仅用于运维审计，不用于权限判断。

## 9. 生产检查清单

- [ ] 管理员强密码
- [ ] 关闭公网直接访问 8787
- [ ] HTTPS 证书有效
- [ ] 数据目录权限最小化
- [ ] 定期备份
- [ ] API Key 已轮换
- [ ] 邮件密码未写入脚本
- [ ] 客户端机器磁盘加密
- [ ] 日志中不包含敏感正文

---
description: 生产环境 Docker 部署后的调试与日志查看指南。
---

# 生产环境调试指南 (Production Debugging Guide)

如果在服务器上部署后遇到问题，或需要检查系统运行状态，请参考以下步骤。

## 1. 快速查看实时日志 (Quick Log Check)
查看当前正在发生什么：

```bash
# 查看所有服务 (后端 API + 前端 Nginx) 的实时日志
docker-compose logs -f --tail=100

# 只查看后端服务 (Python 交易逻辑) 的日志
docker-compose logs -f --tail=100 backend
```

## 2. 查看历史日志文件 (Persistent Log Files)
即使容器重启，日志也会保存在项目目录下的 `logs/` 文件夹中（映射自容器内的 `/app/logs`）。

-   **应用日志**: 查看 `logs/app.log`。这是最主要的分析和交易日志。
-   **Trace 数据**: 原始的执行链路数据存储在 SQLite 数据库中。如果有需要，您可以下载 `data/trace_store.db` 到本地，使用 SQLite 浏览器进行深度分析。

## 3. 进入容器手动排查 (Manual Inspection)
如果您需要手动运行脚本（例如 `trigger.py`）或检查环境变量配置是否正确：

```bash
# 1. 进入后端容器的命令行
docker-compose exec backend /bin/bash

# 进入后，您可以执行命令：
# 检查环境变量（确认 API Key 是否读取成功）
env | grep BINANCE

# 手动运行触发器脚本（测试逻辑）
python trigger.py

# 检查数据库连接
python -c "import sqlite3; print(sqlite3.connect('data/trader_round_memory.db').cursor().execute('SELECT 1').fetchone())"
```

## 4. 常见问题与修复 (Common Issues)

### "Order's position side does not match..." (持仓方向报错)
-   **原因**: 币安账户的“双向持仓模式”与“单向模式”设置不匹配。
-   **修复**: 我们的代码现已支持自动检测。如果仍然报错，请尝试重启容器以清除缓存：
    `docker-compose restart backend`

### "Database Locked" (数据库被锁定)
-   **原因**: 多个进程同时尝试写入 SQLite 文件。
-   **修复**: 通常是暂时的。如果一直卡死，请停止服务 `docker-compose down`，检查并删除 `data/` 目录下的 `.wal` 临时文件（请小心操作），然后重启。

### 前端显示 "Network Error" (网络错误)
-   **原因**: 后端 API 未启动，或 Nginx 代理配置错误。
-   **检查**:
    1. 运行 `docker-compose ps` 确认 `backend` 状态是否为 `Up`。
    2. 运行 `docker-compose logs frontend` 查看 Nginx 是否有报错。

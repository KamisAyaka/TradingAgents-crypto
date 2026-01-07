# 🚀 Agentic Trading System - 服务器部署指南

本文档将指导您如何在 Linux 服务器（如 Ubuntu/Debian）上使用 Docker 部署整套交易系统。

---

## 1. 准备工作

### 服务器要求

- **系统**: Ubuntu 20.04+ / Debian 10+ (推荐)
- **配置**: 至少 2GB 内存 (推荐 4GB)，20GB 硬盘。
- **网络**: 必须能访问 Binance API 和 OpenAI/DeepSeek API。如果不通，需要配置 HTTP 代理。

### 安装 Docker

登录服务器，执行以下命令安装 Docker 和 Docker Compose：

```bash
# 1. 更新软件源
sudo apt-get update && sudo apt-get install -y curl

# 2. 官方脚本一键安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 3. 验证安装
sudo docker --version
sudo docker compose version
```

---

## 2. 上传代码

将本地的 `TradingAgents-crypto` 文件夹上传到服务器的 `/opt/trading-agent` (或其他目录)。
您可以使用 scp、FileZilla 或 Git。

**示例目录结构**：

```text
/opt/trading-agent/
├── .env                <-- 必须配置
├── docker-compose.yml  <-- 核心编排文件
├── Dockerfile          <-- 后端镜像配置
├── requirements.txt    <-- 后端依赖
├── server.py           <-- 启动入口
├── trigger.py
├── ...
└── web/
    ├── Dockerfile      <-- 前端镜像配置
    ├── nginx.conf      <-- Nginx 配置
    ├── package.json
    └── src/
```

---

## 3. 配置环境 (.env)

在服务器上的项目根目录下，创建或编辑 `.env` 文件。确保填入真实的 API Key。

```bash
cd /opt/trading-agent
nano .env
```

**参考配置内容**：

```ini
# --- 模型配置 (DeepSeek / OpenAI) ---
TRADINGAGENTS_DEEP_THINK_LLM=deepseek-ai/DeepSeek-V3.2
OPENAI_API_KEY=sk-xxxxxx
DEEPSEEK_API_KEY=sk-xxxxxx
# 如果国内服务器连不上 API，需配置反代地址
DEEP_BACKEND_URL=https://api.deepseek.com/v1

# --- 交易配置 (Binance) ---
BINANCE_API_KEY=xxxxxx
BINANCE_SECRET_KEY=xxxxxx
# 确保此 URL 在服务器网络可达
BINANCE_FUTURES_BASE_URL=https://fapi.binance.com

# --- 调度配置 ---
# 自动分析间隔 (秒)
LONGFORM_RUN_INTERVAL=86400

# --- 代理配置 (选用) ---
# 如果服务器连不上币安，需要 HTTP 代理
# HTTP_PROXY=http://127.0.0.1:7890
# HTTPS_PROXY=http://127.0.0.1:7890
```

---

## 4. 启动服务

一切就绪后，执行以下命令构建并启动容器：

```bash
# 后台启动 (第一次运行会进行构建，可能需要几分钟)
sudo docker compose up -d --build

sudo docker exec -it trading_backend /bin/sh
```

### 验证运行状态

```bash
sudo docker compose ps
```

如果看到 `trading_backend` 和 `trading_frontend` 的状态都是 `Up`，说明启动成功。

### 访问地址

由于为了避免与服务器上可能存在的 Nginx/Apache 冲突，我们将前端端口默认配置为了 **8080**。

**请访问**: `http://<服务器IP>:8080`

---

## 5. 使用说明

1.  **启动自动交易**:
    - 页面加载后，你会看到右上角有一个 **"启动调度器" (Start Scheduler)** 按钮。
    - 点击它！这会激活后台的定时任务（包括长文分析、K 线同步、价格监控）。
2.  **查看状态**:
    - 在左侧 "Trace 历史" 面板观察是否有新的分析记录生成。
    - "System Logs" 面板会显示实时的执行动作。

---

## 6. 常用运维命令

**查看实时日志**（排查报错神器）：

```bash
sudo docker compose logs -f --tail=100
```

**重启服务**（修改 .env 或代码后）：

```bash
sudo docker compose restart
```

**停止服务**：

```bash
sudo docker compose down
```

---

## 7. 故障排查 (Troubleshooting)

### 端口冲突 (Address already in use)

如果启动时提示 `Bind for 0.0.0.0:80 failed: port is already allocated`，说明端口被占用了。

**排查方法**：

```bash
# 查看 80 端口占用情况
sudo netstat -tulpn | grep :80
```

如果看到 `nginx` 或 `apache` 占用了 80 端口，我们的部署脚本默认使用了 **8080** 来避开此问题。如果 8080 也被占用，请修改 `docker-compose.yml` 中的端口映射：

```yaml
ports:
  - "你的端口:80"
```

### "Order's position side does not match"

> 这是一个已知问题，通常是因为币安的双向持仓模式配置。系统现在会自动检测模式。
> **解决**: 重启一次后端服务通常能解决缓存问题：`sudo docker compose restart backend`

### 前端白屏或无法访问

> 1. 检查防火墙是否开放了 **8080** 端口（尤其是云服务器的安全组设置）。
> 2. 检查 `backend` 容器是否启动成功 (`sudo docker compose logs backend`)。

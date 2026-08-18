# 活动分析助手 — 部署指南

## 目录

- [1. 系统架构](#1-系统架构)
- [2. 部署前提](#2-部署前提)
- [3. 开发机构建打包](#3-开发机构建打包)
- [4. 目标机离线部署](#4-目标机离线部署)
- [5. 配置说明](#5-配置说明)
- [6. 运维管理](#6-运维管理)
- [7. 故障排查](#7-故障排查)

---

## 1. 系统架构

```
┌──────────────────────────────────────────────┐
│              用户浏览器                        │
│           http://目标机:8000                   │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│          FastAPI 服务 (:8000)                  │
│  ┌─────────────┐  ┌────────────────────────┐ │
│  │  /api/*      │  │  /* (前端静态文件)      │ │
│  │  LangGraph   │  │  index.html + JS/CSS   │ │
│  │  多智能体    │  │                        │ │
│  └─────────────┘  └────────────────────────┘ │
└──────────────────┬───────────────────────────┘
                   │ HTTP
┌──────────────────▼───────────────────────────┐
│           内网 LLM 推理服务                     │
│      (OpenAI 兼容 API)                        │
└──────────────────────────────────────────────┘
```

## 2. 部署前提

### 目标机要求

| 条件 | 要求 |
|------|------|
| 操作系统 | Linux (CentOS 7+ / Ubuntu 20.04+) 或 macOS |
| Python | 3.10+ |
| 磁盘空间 | >= 2GB（含依赖） |
| 内存 | >= 4GB |
| 内网访问 | 可访问内网 LLM 服务 |
| 端口 | 8000（可自定义） |

## 3. 开发机构建打包

在**有网络**的开发机上执行：

### 3.1 克隆项目

```bash
git clone <repo-url>
cd <项目目录>
```

### 3.2 一键构建

```bash
cd backend
bash scripts/build.sh
```

脚本会依次执行：
1. 安装前端依赖（npm ci）
2. 构建前端静态文件（npm run build），并校验产物完整性
3. 复制 `frontend/dist/` → `backend/src/static/`
4. 下载 Python 依赖离线包到 `backend/wheels/`
5. 打包为 `activity-analysis-assistant-YYYYMMDD-HHMMSS.tar.gz`

如果靶机 Python 版本或平台与开发机不同，通过环境变量指定：

```bash
# 靶机 Python 3.10, Linux x86_64
TARGET_PYTHON_VERSION=310 TARGET_PLATFORM=manylinux2014_x86_64 bash scripts/build.sh

# 靶机 Python 3.12, macOS arm64
TARGET_PYTHON_VERSION=312 TARGET_PLATFORM=macosx_11_0_arm64 bash scripts/build.sh
```

若未指定，自动检测开发机 Python 版本。

### 3.3 产物

```
activity-analysis-assistant-YYYYMMDD-HHMMSS.tar.gz
├── backend/
│   ├── src/              # 后端源码 + 前端 static/
│   ├── wheels/           # Python 离线依赖包
│   ├── requirements.txt  # 依赖清单
│   ├── .env.example      # 配置模板
│   ├── scripts/
│   │   └── start.sh      # 目标机启动脚本
│   └── data/             # 数据目录（空）
└── frontend/
    └── package.json      # 前端依赖清单参考
```

## 4. 目标机离线部署

### 4.1 传输部署包

```bash
scp activity-analysis-assistant-*.tar.gz user@目标机:/opt/
ssh user@目标机
```

### 4.2 解压

```bash
cd /opt
tar -xzf activity-analysis-assistant-*.tar.gz
cd backend
```

### 4.3 配置 LLM

**方式一（推荐）：** 直接运行 `start.sh`，脚本在检测到 `.env` 未配置或包含占位值时，会**交互式引导**输入内网 LLM 地址、模型名称和 API Key，自动写入 `.env`。

**方式二（手动）：** 适合脚本化批量部署或高级用户。

```bash
cp .env.example .env
vim .env
```

关键配置项（填入内网大模型的实际信息）：

```env
LLM_API_KEY=            # 内网服务通常不需要 API Key，可留空
LLM_BASE_URL=http://内网LLM服务IP:端口/v1
LLM_MODEL=模型名称
```

内网常见配置示例：

```env
# Ollama 本地部署
LLM_BASE_URL=http://192.168.1.100:11434/v1
LLM_MODEL=qwen2.5:14b

# vLLM 内网部署
LLM_BASE_URL=http://192.168.1.100:8000/v1
LLM_MODEL=/models/qwen2.5-14b

# 企业内部 API（兼容 OpenAI 范式）
LLM_BASE_URL=http://10.0.0.50:8080/v1
LLM_MODEL=gpt-4
```

确认各项值：

```bash
grep -v '^#' .env | grep -v '^$'
```

### 4.4 启动服务

```bash
bash scripts/start.sh
```

首次运行会：
1. 检测 Python 版本
2. 创建虚拟环境 `venv/`
3. 从 `wheels/` 离线安装依赖
4. 检查 `.env` 配置，未配置则**交互式引导**输入内网 LLM 信息
5. 显示当前 LLM 配置摘要（API Key 脱敏）
6. 启动 uvicorn 服务

### 4.5 验证

```bash
# API 健康检查
curl http://localhost:8000/health
# 返回: {"status":"ok"}

# 获取可用分析组件
curl http://localhost:8000/api/components
# 返回: {"components":[{"type":"overview",...}]}

# 浏览器访问
open http://localhost:8000
```

## 5. 配置说明

### 5.1 环境变量完整列表

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | 全局 LLM API Key | `""` (选填，内网服务通常不需要) |
| `LLM_BASE_URL` | 全局 LLM 服务地址 | `""` (必填，无默认值) |
| `LLM_MODEL` | 全局模型名称 | `""` (必填，无默认值) |
| `SUPERVISOR_LLM_MODEL` | 主管 Agent 模型（覆盖全局） | 回退到 `LLM_MODEL` |
| `DATA_ANALYSIS_LLM_MODEL` | 数据分析 Agent 模型 | 回退到 `LLM_MODEL` |
| `REPORT_GENERATION_LLM_MODEL` | 报告生成 Agent 模型 | 回退到 `LLM_MODEL` |
| `REPORT_VALIDATION_LLM_MODEL` | 报告校验 Agent 模型 | 回退到 `LLM_MODEL` |
| `FINALIZE_LLM_MODEL` | 汇总 Agent 模型 | 回退到 `LLM_MODEL` |
| `DB_PATH` | SQLite 持久化路径 | `data/checkpoints.db` |
| `UPLOAD_DIR` | 文件上传目录 | `data/uploads` |
| `OUTPUT_DIR` | 报告输出目录 | `data/outputs` |
| `HOST` | 服务绑定地址 | `0.0.0.0` |
| `PORT` | 服务端口 | `8000` |

### 5.2 每个 Agent 独立配置模型

```env
# 全局默认
LLM_API_KEY=sk-default

# 主管用强推理模型
SUPERVISOR_LLM_MODEL=qwen2.5:32b

# 校验用小模型降成本
REPORT_VALIDATION_LLM_MODEL=qwen2.5:7b
```

不配的 Agent 自动回退到全局 `LLM_MODEL`。

### 5.3 银行营销外部 API 配置（v2 新增）

新版接入了行内活动业务 API，部署到生产环境时必须改为目标机可达的内网真实地址：

```env
BANK_MARKETING_ACTIVITY_LIST_URL=http://内网IP:端口/api2/campaigns/search
BANK_MARKETING_TEMPLATE_LIST_URL=http://内网IP:端口/api2/templates
BANK_MARKETING_COMPONENT_VALUES_URL=http://内网IP:端口/api2/component-values
BANK_MARKETING_OUTBOUND_ACTIVITY_DATA_URL=http://内网IP:端口/api2/dataservice/query/{trade_code}
```

详见 `backend/.env.example` 中的完整变量列表。

### 5.4 模型接入兼容性

服务端使用 `langchain-openai` 的 `ChatOpenAI` 客户端，兼容任何实现 OpenAI API 范式的推理服务，包括但不限于：

| 推理服务 | BASE_URL 示例 |
|---------|--------------|
| Ollama | `http://localhost:11434/v1` |
| vLLM | `http://localhost:8001/v1` |
| LocalAI | `http://localhost:8080/v1` |
| 通义千问 DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| DeepSeek API | `https://api.deepseek.com/v1` |
| OpenAI API | `https://api.openai.com/v1` |

## 6. 运维管理

### 6.1 后台运行

```bash
# 使用 nohup
nohup bash scripts/start.sh > logs/app.log 2>&1 &

# 或使用 systemd（推荐）
sudo tee /etc/systemd/system/activity-analysis-assistant.service << 'EOF'
[Unit]
Description=活动分析助手
After=network.target

[Service]
Type=simple
User=app
WorkingDirectory=/opt/backend
EnvironmentFile=/opt/backend/.env
ExecStart=/opt/backend/venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable activity-analysis-assistant
sudo systemctl start activity-analysis-assistant
```

### 6.2 查看日志

```bash
# systemd
journalctl -u activity-analysis-assistant -f

# nohup
tail -f logs/app.log
```

### 6.3 优雅重启

```bash
sudo systemctl restart activity-analysis-assistant
```

### 6.4 数据备份

```bash
# 备份数据库和上传文件
tar -czf backup-$(date +%Y%m%d).tar.gz \
    data/checkpoints.db \
    data/uploads/ \
    data/outputs/
```

### 6.5 更新部署

```bash
# 停服
sudo systemctl stop activity-analysis-assistant

# 备份旧版本
mv /opt/backend /opt/backend.bak

# 解压新版本
cd /opt && tar -xzf activity-analysis-assistant-*.tar.gz

# 恢复配置
cp /opt/backend.bak/.env /opt/backend/.env

# 恢复数据库
cp /opt/backend.bak/data/checkpoints.db /opt/backend/data/

# 安装依赖（如果有新依赖）
cd /opt/backend
source venv/bin/activate
pip install --no-index --find-links=wheels/ -r requirements.txt

# 启动
sudo systemctl start activity-analysis-assistant
```

## 7. 故障排查

### 7.1 服务无法启动

```bash
# 检查 Python 版本
python3 --version  # 需要 >= 3.10

# 检查端口占用
lsof -i :8000

# 手动启动查看详细错误
cd /opt/backend
source venv/bin/activate
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --log-level debug
```

### 7.2 LLM 连接失败

```bash
# 测试 LLM 服务连通性
curl http://内网LLM地址:端口/v1/models

# 检查 .env 配置（如果 BASE_URL 或 MODEL 为空，config.py 会在首次调用时报错）
cat .env | grep LLM_

# 重新运行交互式配置
rm .env && bash scripts/start.sh
```

如果启动时看到 `connection refused` 或 HTTP 状态码错误，通常是 `LLM_BASE_URL` 地址不可达或路径格式不对，注意末尾是否需要 `/v1`。

### 7.3 文件上传失败

```bash
# 确认上传目录存在且有写权限
ls -la data/uploads/
chmod 755 data/uploads/
```

### 7.4 前端页面 404

确认 `backend/src/static/` 目录存在且包含 `index.html`：

```bash
ls backend/src/static/
# 应有: index.html  assets/
```

如缺失，在开发机上重新执行构建脚本：
```bash
cd frontend && npm run build
cp -r dist ../backend/src/static/
```

### 7.6 会话数据丢失

SQLite 数据库路径配置为 `data/checkpoints.db`，确认文件存在且可读写：

```bash
ls -la data/checkpoints.db
```

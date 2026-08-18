# agent_v3 P4 设计：openJiuwen 版离线部署包重做

> 日期：2026-08-12
> 前置：`2026-08-07-openjiuwen-agent-core-migration-research.md` §4（P4 收尾定义）、`2026-08-11-agent-v3-p3-acceptance.md`（部署警告 #2：requirements-offline.txt 未含 openjiuwen，P4 完成前不得出离线包）
> 范围说明：调研文档中 P4 的另两项（删 deepagents/langchain-*、框架相关测试重写）已在 P3 完成（langchain 全系已删、全量 301 passed）。**本设计只覆盖剩余项：离线 wheel 集重做与验证。**

## 1. 目标与约束

- **目标**：产出基于 openJiuwen 运行时的完整离线部署 tar.gz，并在本机 Docker 容器内完成「断网安装 + 启动 + 业务冒烟」验收。
- **环境约束**：本机 macOS；wheel 集目标平台 ky10 x86_64 / Python 3.12 / manylinux。经用户确认：
  1. 构建与验证均在本机 Docker（`linux/amd64`）执行，不依赖额外 Linux 构建机；
  2. openjiuwen 重依赖（transformers/pymilvus/trafilatura 等）按声明 **全量闭包**下载，不做裁剪；
  3. 验收深度 = 断网安装 + uvicorn 启动 + API 级业务冒烟。
- **全新建原则（用户明确要求）**：旧 `offline-bundle/`（109 个 langchain 系 wheel）与旧 `scripts/build-offline-package.sh` **一字不动**，作为历史归档；P4 产物全部放入新建专用目录 `offline-v3/`。

## 2. 目录与文件

新建专用目录，承载 P4 全部内容：

```
offline-v3/
├── build.sh          # 新构建脚本（Docker 容器内执行）
├── verify.sh         # 两阶段验证脚本（断网安装 + 业务冒烟）
├── requirements.txt  # 离线依赖清单（= backend/requirements.txt 内容，钉版一致）
├── wheels/           # openJiuwen 全量闭包 wheel 集（pip download 产物）
├── python/           # 便携解释器 tarball（复用旧 offline-bundle/python 缓存）
└── dist/             # 产物 activity-analysis-assistant-offline-<date>.tar.gz
```

**产物 tar 内部布局与旧包完全一致**（`backend/` + `ops/` + `offline-bundle/{python,wheels}` + `deploy-offline.sh`），因此目标机侧 `deploy-offline.sh`、`backend/scripts/start-offline.sh` 均无需修改。

唯一原地修改的既有文件：**`backend/requirements-offline.txt`** 补两行（与 `requirements.txt` 对齐）：

```
cryptography==46.0.7
openjiuwen==0.1.16.post2
```

原因：目标机安装时 `start-offline.sh` 读取的是包内 `backend/requirements-offline.txt`。ops-assistant 复用主应用 venv，其第三方依赖（fastapi/httpx/pydantic/python-dotenv/pyyaml）需确认被闭包覆盖——下载后检查 wheels 目录，缺 `pyyaml` 则显式补入。

## 3. 构建链路（offline-v3/build.sh）

本机执行流程：

```bash
# 1. 本机构建前端（工具链现成）
cd frontend && npm ci && npm run build

# 2. 容器内执行构建（脚本自带前端产物校验，不做 npm）
docker run --rm --platform linux/amd64 \
  -v "$REPO":/workspace -w /workspace \
  python:3.12-bookworm bash offline-v3/build.sh
```

`build.sh` 步骤（容器内，等价旧脚本语义、全新编写）：

1. 前置校验：`uname -s/m` = Linux/x86_64；`frontend/dist/index.html` 存在（`SKIP_FRONTEND` 语义内置，无 npm 依赖）。
2. 暂存区组装：拷贝 `backend/`（除 venv/.env/data/src/static）、`ops/`（除 data/.env/__pycache__）、`frontend/dist` → `backend/src/static`、`deploy-offline.sh`、`data/mysql`。
3. 便携 Python：优先从旧 `offline-bundle/python/cpython-3.12.13-*.tar.gz` 拷贝缓存；缺失则按旧脚本同 URL 下载；`gzip -t` 校验。
4. `pip download --only-binary=:all: --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 --python-version 312 --implementation cp --abi cp312` 从 `offline-v3/requirements.txt` 下载全量闭包 → 暂存区 `offline-bundle/wheels/`；同时留档到 `offline-v3/wheels/`（本机缓存，重复构建提速）。
5. 生成 `MANIFEST.sha256` → 打 tar.gz → 落 `offline-v3/dist/`。

**已知风险预案**：`--only-binary=:all:` 遇闭包内某包无 manylinux cp312 wheel 会硬失败。应对顺序：① 该依赖换有 wheel 的兼容版本并钉版（记录钉版原因）；② 无替代版本才考虑单包 sdist（目标机无编译链，尽量避免）。构建期实测发现，逐案记录于验收文档。

## 4. 验证（offline-v3/verify.sh）

对 `offline-v3/dist/` 产物做两阶段容器验证。

### 阶段 ① 断网安装验证（闭包完备性铁证）

- 镜像 `debian:buster-slim`（glibc 2.28，与 ky10 V10 对齐）。
- 容器以 **`--network none`** 启动，挂载产物 tar.gz。
- 解压 → 预置最小 `.env`（占位 LLM 配置，使后续无交互）→ 在容器内手动执行与 `start-offline.sh` 等价的安装序列（解压便携 Python → 建 venv → `pip install --no-index --find-links=offline-bundle/wheels -r backend/requirements-offline.txt`）→ `python -c "import src.main"` 通过即断言成功。阶段①不启动服务。
- 断网安装通过 = wheel 闭包自洽，不依赖 pip 解析器承诺。

### 阶段 ② 业务冒烟

- 同镜像、可出网容器（经宿主机 NAT 访问行内内网）。
- 预置 `backend/.env`：LLM = 行内 deepseek-v4-flash 端点（与 P3 验收同源）；营销接口 = `host.docker.internal:8005`（本机 mock 服务，冒烟前在本机拉起）；`INPUT_START_OPS=n`（ops 不独立冒烟——其依赖安装已被阶段①覆盖，且 venv 复用关系已确认）。
- `bash deploy-offline.sh` 全自动跑通（预置 .env 后无交互）→ 服务起来后 API 级冒烟：
  1. 健康检查；
  2. 建会话 + 一轮对话（search_activities 命中）；
  3. 写工具审批 approve 一次（如 add_to_analysis_queue）；
  4. generate_report 全流程（管线步骤帧成对、报告落库）。
  复用 P3 验收的 API 手法（curl + SSE 帧断言）。
- **降级预案**：容器内若不可达行内 LLM 端点，本机起端口转发（经 `host.docker.internal` 暴露）后继续，不因网络拓扑阻塞验收。

## 5. 文档与交付

- `DEPLOY-OFFLINE-KYLIN.md` **新增**「openJiuwen 版（agent_v3）离线部署」章节：新构建命令（npm build + docker run build.sh）、verify.sh 用法、沿用 P3 的 `.env` 删除 `AGENT_V3_ENABLED` 残留键警告；旧章节内容原样保留，开头加一行指向新章节。
- 交付物：
  1. `offline-v3/dist/activity-analysis-assistant-offline-<date>.tar.gz`；
  2. P4 验收记录 `docs/superpowers/specs/2026-08-12-agent-v3-p4-acceptance.md`（含闭包清单体积、断网安装证据、冒烟逐项结果）。
- 验收通过后关闭 P3 验收文档部署警告 #2。

## 6. 明确不做

- 不删除/不改动旧 `offline-bundle/` 与 `scripts/build-offline-package.sh`。
- 不做依赖裁剪（全量闭包是既定决策）。
- 不做 ops-assistant 独立冒烟、不做 ky10 实机验收（交付后由部署方执行）。
- 不改 `deploy-offline.sh` / `start-offline.sh`（产物内部布局与旧包一致，天然兼容）。

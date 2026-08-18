# LLM API Key 密文配置使用文档

> 适用范围：backend 主应用（`backend/.env`）与 ops 运维助手（`ops/.env` / 复用 `backend/.env`）
> 配套代码：`backend/src/secrets.py`、`ops/src/secrets.py`、`backend/scripts/env_secret.py`

## 1. 背景与目标

`backend/.env` 中的 LLM API Key（全局 `LLM_API_KEY` 及 8 个 Agent 角色 `*_LLM_API_KEY`）
原先以明文保存。本方案将其改为**密文存储**：

- 配置文件 / 备份 / 误发文件中不再出现明文密钥；
- 明文只在进程内存中出现，解密发生在配置加载时；
- 主密钥与密文**物理分离**（不在 `.env` 同一文件、不进 git）；
- 完全兼容旧明文配置：不含 `enc:v1:` 前缀的值原样使用，无需一次性迁移。

## 2. 方案概述

| 项 | 说明 |
|---|---|
| 算法 | AES-256-GCM（`cryptography`，项目已钉版 `46.0.7`，离线 wheel 已含） |
| 密文格式 | `enc:v1:<base64(nonce ‖ ciphertext ‖ tag)>`（每次加密随机 nonce，防篡改） |
| 主密钥 | 32 字节（AES-256），hex 64 字符或 base64 44 字符 |
| 主密钥来源（按优先级） | ① 环境变量 `LLM_MASTER_KEY` → ② 环境变量 `LLM_MASTER_KEY_FILE` 指定文件 → ③ 默认密钥文件 `backend/data/secrets/master.key` |
| 失败策略 | 配置含密文但主密钥缺失 → 进程**启动即失败**（fail-fast），绝不把密文当明文发出 |

密文覆盖的字段（backend `Settings` 自动解密）：

```
LLM_API_KEY
SUPERVISOR_LLM_API_KEY
DATA_ANALYSIS_LLM_API_KEY
REPORT_GENERATION_LLM_API_KEY
REPORT_VALIDATION_LLM_API_KEY
FINALIZE_LLM_API_KEY
AGENT_V2_MAIN_LLM_API_KEY
AGENT_V2_CHEAP_LLM_API_KEY
AGENT_V2_FALLBACK_LLM_API_KEY
```

ops 侧仅读取 `llm_api_key`（`OPS_LLM_API_KEY` 或回退 `backend/.env` 的 `LLM_API_KEY`），
使用同一套主密钥解密，默认密钥文件取主应用目录下的 `backend/data/secrets/master.key`。

## 3. 快速开始

所有命令在 `backend/` 目录下执行（或任意目录用 `--env` / `--key-file` 指定路径）。
工具使用项目自带依赖，无需额外安装。

### 3.1 生成主密钥

```bash
cd backend
python scripts/env_secret.py init
# 输出：主密钥已写入 backend/data/secrets/master.key（chmod 600）
```

- 默认写入 `backend/data/secrets/master.key`（该目录已 gitignore）；
- 需要输出到别处：`--file /path/master.key`；仅打印不落盘：`--print`；
- **妥善保管**：主密钥是解密的唯一凭据，丢失后密文无法恢复。

### 3.2 加密 .env

```bash
python scripts/env_secret.py encrypt --env backend/.env --key-file backend/data/secrets/master.key
# 输出：backend/.env: 加密 N 个字段，跳过已加密 M 个，明文残留 K 个
```

- 默认处理 `LLM_API_KEY` 及所有 `*_LLM_API_KEY`；已加密的字段自动跳过（可重复执行）；
- 只处理指定字段：`--fields LLM_API_KEY,SUPERVISOR_LLM_API_KEY`；
- 注释、空行、无关行原样保留。

### 3.3 校验

```bash
python scripts/env_secret.py check --env backend/.env --key-file backend/data/secrets/master.key --require-encrypted
# 严格模式：所有目标字段必须为密文且可解密；不加 --require-encrypted 仅验证密文可解
```

### 3.4 启动应用

主密钥注入（二选一）：

```bash
# 方式一：环境变量
export LLM_MASTER_KEY=<hex64 字符>
python src/main.py

# 方式二：密钥文件（默认路径即可被识别，无需额外配置）
#   backend/data/secrets/master.key 已存在时自动读取
python src/main.py
```

启动后 `get_settings()` 即得到解密后的明文密钥，业务代码零改动。

### 3.5 审计查看明文

```bash
python scripts/env_secret.py decrypt --env backend/.env --key-file backend/data/secrets/master.key
# 注意：会输出真实密钥，仅限受控环境使用
```

## 4. 部署场景

### 4.1 Docker Compose（`deploy/docker/`）

Compose 通过 `env_file` 把 `backend/.env` 原样注入容器——密文随文件进入容器，没问题。
**主密钥不能写进 `backend/.env`**（与密文同文件即失去意义），需独立注入：

- 宿主机设置环境变量后传给容器（在 compose 文件中 `environment:` 引用 `LLM_MASTER_KEY: ${LLM_MASTER_KEY}`），或
- 把密钥文件只读挂载进容器并设置 `LLM_MASTER_KEY_FILE` 指向挂载路径。

### 4.2 Kylin / systemd 离线部署

- 主密钥放独立的 `EnvironmentFile`（权限 600），如 `/etc/njbank/master.env`，内容 `LLM_MASTER_KEY=...`；
- 或密钥文件 `/opt/njbank/keys/master.key`（chmod 600）+ 设置 `LLM_MASTER_KEY_FILE`；
- 与 `backend/.env` 物理分离即可。

### 4.3 ops 运维助手

ops 读取同一份 `backend/.env` 中的 `LLM_API_KEY`（或 `ops/.env` 的 `OPS_LLM_API_KEY`），
主密钥解析规则与 backend 一致（环境变量 → `LLM_MASTER_KEY_FILE` → 主应用 `data/secrets/master.key`）。
部署时给 ops 进程注入与 backend 相同的主密钥即可。

## 5. 密钥轮换

```bash
# 用旧密钥解密、自动生成新密钥重加密（新密钥会打印出来，请安全保管）
python scripts/env_secret.py rotate --env backend/.env --old-key-file backend/data/secrets/master.key --generate-new

# 或显式指定新旧密钥
python scripts/env_secret.py rotate --env backend/.env \
  --old-key-file /path/old.key --new-key <hex64 新密钥>
```

轮换后需把新主密钥部署到所有运行 backend / ops 的机器，再重启服务。

## 6. 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 启动报 `MasterKeyMissingError: 配置值以 enc:v1: 开头（密文）但未找到主密钥` | 配置是密文但进程没拿到主密钥 | 设置 `LLM_MASTER_KEY` 或 `LLM_MASTER_KEY_FILE`，或确认默认密钥文件存在 |
| 启动报 `ValueError: 密文解密失败：主密钥不匹配或密文被篡改` | 主密钥不对，或密文被改动 | 核对主密钥；用 `check` 逐字段定位；必要时用 `decrypt` 对照 |
| `encrypt` 报 `缺少主密钥` | 命令行未提供密钥且环境变量/默认文件都没有 | `--key` / `--key-file` 或设置环境变量 |
| `check` 严格模式报 `仍是明文` | 目标字段还有明文残留 | 重新执行 `encrypt` |
| 轮换后旧密钥校验失败 | 正常现象，说明轮换生效 | 用新密钥部署并校验 |

## 7. 安全边界与注意事项

- 本方案解决「静态配置泄露」（仓库、备份、误发文件），**防不住服务器被攻破**——那是 KMS/HSM 的范畴；
- 主密钥必须与密文物理分离，并限制文件权限（`chmod 600`）、不进 git；
- 日志与异常信息不含明文密钥（异常只报错不打印值）；
- 前端配置页（`/env-config`）编辑的是 `.env` 原始内容，密文原样往返，不会被意外改回明文；
- 明文配置完全兼容：未加密的环境可继续使用，不影响现有部署与单元测试。

## 8. 扩展到其他敏感字段

CLI 已支持任意字段（`--fields`），但**运行时解密目前只接入了 `*_LLM_API_KEY`**。
如需把 `BANK_MARKETING_API_TOKEN`、`DATABASE_PASSWORD` 等也密文化：

1. `backend/src/config.py`：把字段名加入 `_API_KEY_FIELDS` 列表（validator 自动生效）；
2. `ops/src/config.py`：对相应取值处包一层 `maybe_decrypt`；
3. 用 `encrypt --fields BANK_MARKETING_API_TOKEN` 加密。

## 9. 相关测试

```bash
cd backend && pytest tests/test_secrets.py tests/test_config_secrets.py
cd ops     && pytest tests/test_secrets.py tests/test_config.py
```

覆盖：加解密往返、篡改检测、错误密钥拒绝、明文透传、密文缺主密钥 fail-fast、
轮换后旧密钥失效、ops 侧从加密 `backend/.env` 加载等。

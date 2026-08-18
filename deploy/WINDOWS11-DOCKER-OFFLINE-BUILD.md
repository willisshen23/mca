# Windows 11 使用 Docker 构建麒麟离线部署包

## 1. 文档用途

本文用于在 Windows 11 开发机上，通过 Docker 的 Linux x86_64 容器构建银河麒麟 V10 可使用的完整离线部署包。

最终离线包包含：

- Vue 前端生产静态文件；
- Linux x86_64 便携 Python 3.12；
- Python 3.12 / manylinux x86_64 离线依赖；
- 后端代码、数据库脚本和一键部署脚本；
- 离线资源 SHA-256 完整性清单。

> 不要直接在 PowerShell、CMD 或 Git Bash 中绕过平台检查运行
> `scripts/build-offline-package.sh`。该脚本必须在 Linux x86_64 环境中执行，
> 否则可能生成与麒麟服务器不兼容的二进制依赖。

---

## 2. 前置条件

Windows 11 开发机需要满足：

1. 已安装 Docker Desktop；
2. Docker Desktop 使用 Linux containers；
3. BIOS 和 Windows 已启用虚拟化；
4. Docker Desktop 后端使用 WSL2；
5. 可访问 npm、PyPI 和 GitHub；
6. 建议至少保留 5 GB 可用磁盘空间；
7. 在项目根目录执行本文命令。

项目根目录示例：

```text
E:\code\njbank_Marketing_Campaign_Analysis
```

---

## 3. 启动并检查 Docker

启动 Docker Desktop，等待任务栏中的 Docker 图标显示运行正常。

在项目根目录打开 PowerShell，执行：

```powershell
docker info --format "server={{.ServerVersion}} os={{.OSType}} arch={{.Architecture}}"
```

正常结果应包含：

```text
os=linux arch=x86_64
```

如果提示无法连接 `docker_engine`，说明 Docker Desktop 尚未启动或仍在初始化。

---

## 4. 准备 Linux x86_64 构建镜像

### 4.1 默认方式

```powershell
docker pull --platform linux/amd64 python:3.12-bookworm
```

### 4.2 Docker Hub 下载缓慢时

可通过 DaoCloud 镜像地址下载：

```powershell
docker pull --platform linux/amd64 `
  docker.m.daocloud.io/library/python:3.12-bookworm

docker tag `
  docker.m.daocloud.io/library/python:3.12-bookworm `
  python:3.12-bookworm
```

### 4.3 验证镜像

```powershell
docker run --rm --platform linux/amd64 `
  python:3.12-bookworm `
  bash -lc "uname -s; uname -m; python3.12 --version"
```

正常结果：

```text
Linux
x86_64
Python 3.12.x
```

只有输出为 `Linux` 和 `x86_64` 时，才能继续构建麒麟离线包。

---

## 5. 执行完整离线构建

在项目根目录打开 PowerShell，执行以下命令：

```powershell
$ProjectRoot = (Resolve-Path ".").Path

$BuildCommand = @'
set -euo pipefail

apt-get update
apt-get install -y --no-install-recommends \
  nodejs \
  npm \
  curl \
  ca-certificates \
  coreutils \
  findutils \
  tar \
  gzip \
  grep

mkdir -p /work/project

tar -C /source \
  --exclude=.git \
  --exclude=.venv \
  --exclude=.idea \
  --exclude=backend/venv \
  --exclude=backend/data \
  --exclude=frontend/node_modules \
  --exclude=frontend/dist \
  --exclude=activity-analysis-assistant-offline-*.tar.gz \
  -cf - . |
  tar -C /work/project -xf -

cd /work/project
bash scripts/build-offline-package.sh
cp activity-analysis-assistant-offline-*.tar.gz /output/
'@

docker run --rm `
  --name njbank-offline-builder `
  --platform linux/amd64 `
  -v "${ProjectRoot}:/source:ro" `
  -v "${ProjectRoot}:/output" `
  -w /work `
  python:3.12-bookworm `
  bash -lc $BuildCommand
```

### 5.1 隔离方式说明

构建命令使用两个挂载点：

| 挂载点 | 权限 | 用途 |
|---|---|---|
| `/source` | 只读 | 读取项目源码 |
| `/output` | 读写 | 只写回最终压缩包 |

实际构建在容器的 `/work/project` 临时目录中完成，不会在 Windows 项目目录生成 Linux 版本的 `node_modules` 或虚拟环境。

容器退出后会自动删除，只保留最终压缩包和 Docker 基础镜像缓存。

### 5.2 构建过程

项目脚本会依次执行：

1. `npm ci` 安装前端依赖；
2. `npm run build` 构建前端；
3. 复制前端产物到后端静态资源目录；
4. 准备 Linux x86_64 便携 Python；
5. 下载 Python 3.12 / manylinux x86_64 wheels；
6. 生成内部 `MANIFEST.sha256`；
7. 生成最终 `.tar.gz`。

构建时间受网络速度影响，通常需要数分钟到十几分钟。

---

## 6. 查看构建结果

构建成功后，项目根目录会出现：

```text
activity-analysis-assistant-offline-YYYYMMDD-HHMMSS.tar.gz
```

查找最新生成的离线包：

```powershell
$Package = Get-ChildItem `
  -Filter "activity-analysis-assistant-offline-*.tar.gz" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

$Package | Select-Object Name, Length, LastWriteTime
```

---

## 7. 校验离线包

### 7.1 计算整个压缩包的 SHA-256

```powershell
$Package = Get-ChildItem `
  -Filter "activity-analysis-assistant-offline-*.tar.gz" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

$Hash = Get-FileHash -LiteralPath $Package.FullName -Algorithm SHA256
$Hash
```

生成外部校验文件：

```powershell
$ChecksumFile = "$($Package.FullName).sha256"
"$($Hash.Hash.ToLower())  $($Package.Name)" |
  Set-Content -LiteralPath $ChecksumFile -Encoding ASCII
```

### 7.2 在 Linux 容器中验证内部资源

```powershell
$ProjectRoot = (Resolve-Path ".").Path
$PackageName = $Package.Name

$ValidateCommand = @"
set -e
mkdir -p /tmp/package-check
tar -xzf '/input/$PackageName' -C /tmp/package-check

test -f /tmp/package-check/activity-analysis-assistant/backend/src/static/index.html
test -f /tmp/package-check/activity-analysis-assistant/offline-bundle/MANIFEST.sha256
test ! -e /tmp/package-check/activity-analysis-assistant/backend/.env
test -x /tmp/package-check/activity-analysis-assistant/deploy-offline.sh

cd /tmp/package-check/activity-analysis-assistant/offline-bundle
sha256sum -c MANIFEST.sha256

echo 'validation=passed'
"@

docker run --rm `
  --platform linux/amd64 `
  -v "${ProjectRoot}:/input:ro" `
  python:3.12-bookworm `
  bash -lc $ValidateCommand
```

最后出现以下内容表示校验通过：

```text
validation=passed
```

---

## 8. 上传并部署到麒麟服务器

将以下文件传输到麒麟服务器：

```text
activity-analysis-assistant-offline-YYYYMMDD-HHMMSS.tar.gz
activity-analysis-assistant-offline-YYYYMMDD-HHMMSS.tar.gz.sha256
```

在麒麟服务器中校验：

```bash
sha256sum -c activity-analysis-assistant-offline-*.tar.gz.sha256
```

解压并部署：

```bash
tar -xzf activity-analysis-assistant-offline-*.tar.gz
cd activity-analysis-assistant
bash deploy-offline.sh
```

部署脚本会完成：

- 校验内部离线资源；
- 解压便携 Python；
- 创建后端虚拟环境；
- 离线安装 Python 依赖；
- 引导配置 LLM 和银行营销接口；
- 启动后端服务。

> 若目标机 `backend/.env` 使用 `enc:v1:` 密文密钥（推荐），启动后端前需在
> 进程环境注入主密钥 `LLM_MASTER_KEY`（或设置 `LLM_MASTER_KEY_FILE` 指向密钥
> 文件），否则后端启动会 fail-fast 报 `MasterKeyMissingError`。
> 详见 `docs/LLM-API-KEY-密文配置使用文档.md`。

---

## 9. 麒麟服务器部署后检查

### 9.1 检查服务

```bash
curl http://127.0.0.1:8000/health
```

正常返回：

```json
{"status":"ok"}
```

## 10. 常见问题

### 10.1 无法连接 Docker 引擎

错误示例：

```text
failed to connect to the docker API
```

处理方法：

1. 启动 Docker Desktop；
2. 等待 Docker Desktop 初始化完成；
3. 确认使用 Linux containers；
4. 重新执行 `docker info`。

### 10.2 Docker 镜像一直停留在 Pulling fs layer

优先改用本文第 4.2 节的 DaoCloud 地址。

也可以查看 Docker 配置的镜像源：

```powershell
docker info | Select-String `
  -Pattern "Registry Mirrors|HTTP Proxy|HTTPS Proxy" `
  -Context 0,3
```

### 10.3 提示容器名称已被占用

查看遗留容器：

```powershell
docker ps -a --filter "name=njbank-offline-builder"
```

确认该容器不是正在运行的有效构建任务后，再删除：

```powershell
docker rm -f njbank-offline-builder
```

然后重新执行构建。

### 10.4 npm 或 pip 下载失败

通常由网络、代理或证书拦截导致。

检查：

```powershell
docker run --rm --platform linux/amd64 `
  python:3.12-bookworm `
  bash -lc "curl -I https://pypi.org; curl -I https://registry.npmjs.org"
```

如果公司网络使用代理，需要在 Docker Desktop 中配置 HTTP/HTTPS Proxy。

### 10.5 构建脚本提示必须在 Linux x86_64 执行

说明脚本没有在容器内部运行。不要删除平台检查，应确认命令中存在：

```powershell
--platform linux/amd64
```

并确认实际调用的是：

```bash
bash scripts/build-offline-package.sh
```

### 10.6 清理 Docker 镜像缓存

如果后续不再构建，可以删除本次基础镜像：

```powershell
docker image rm python:3.12-bookworm
```

如果还会定期重新打包，建议保留镜像，可节省下次下载时间。

---

## 11. 日常重新构建的最短流程

后续代码更新后，只需：

1. 启动 Docker Desktop；
2. 在项目根目录打开 PowerShell；
3. 确认 `docker info` 显示 `linux/x86_64`；
4. 执行第 5 节完整构建命令；
5. 执行第 7 节完整性校验；
6. 将 `.tar.gz` 和 `.sha256` 文件上传到麒麟服务器。

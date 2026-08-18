# MySQL 业务库版本管理

项目默认使用 SQLite 作为业务数据库，也支持 MySQL 8.0 及以上版本。

数据库脚本分为两个版本：

- `schema.sql`：当前版本的完整表结构，用于新环境全量初始化。
- `auto_migrations/*.sql`：已有环境的增量升级脚本。部署 Shell 按文件名顺序自动执行，只执行尚未成功执行的版本。

执行成功的增量版本记录在业务库的 `schema_migrations` 表中。数据库部署由 `backend/scripts/migrate-db.sh` 完成，不耦合 FastAPI 或 Python 业务代码。

## 新环境全量初始化

`schema.sql` 不创建或切换数据库，避免在脚本中写死数据库名。

```sql
CREATE DATABASE njbank_aa CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

```bash
mysql -u root -p njbank_aa < data/mysql/schema.sql
```

完整部署可以直接执行：

```bash
bash backend/scripts/migrate-db.sh full
```

该命令会创建数据库、执行当前全量 SQL，再执行所有尚未记录的增量 SQL。

## 已有环境自动升级

标准部署脚本会在启动 Uvicorn 前调用：

```bash
bash backend/scripts/migrate-db.sh auto
```

`auto` 会自动判断：

- 数据库或核心业务表不存在：执行全量 SQL，再执行增量 SQL；
- 已有完整数据库：只执行尚未执行的增量 SQL。

也可以只升级已有数据库：

```bash
bash backend/scripts/migrate-db.sh upgrade
```

执行流程：

1. 从 `backend/.env` 读取五个 `DATABASE_*` 配置；
2. 按文件名顺序查找 `.sql` 文件；
3. 跳过 `schema_migrations` 中已有记录的版本；
4. 使用 MySQL 命令行客户端执行待升级脚本；
5. 成功后记录版本，再由部署脚本启动后端。

新增升级脚本时使用递增名称，例如：

```text
data/mysql/auto_migrations/20260730_001_add_model_name.sql
```

脚本必须支持失败后重复执行。`migrations/` 目录保留历史手工脚本，不参与部署自动执行。

目标服务器必须安装 `mysql` 客户端。SQLite 本地模式会跳过 MySQL SQL 部署，继续依据 SQLAlchemy ORM 模型创建本地表。

如果绕过正式部署脚本，直接运行 `python -m uvicorn`，不会执行版本化 SQL；应先手工运行 `migrate-db.sh auto`。

## 数据库连接配置

然后在 `backend/.env` 中配置五个字段，系统会安全拼接连接参数：

```env
DATABASE_HOST=127.0.0.1
DATABASE_PORT=3306
DATABASE_USERNAME=njbank
DATABASE_PASSWORD="your_password"
DATABASE_NAME=njbank_aa
```

密码可以直接填写，不需要 URL 编码；包含 `#` 或空格时请使用引号。
清空 `DATABASE_HOST` 即可切回 SQLite，其他 MySQL 配置可以保留。
`DB_PATH` 是 LangGraph 检查点数据库路径，当前仍使用 SQLite，不受上述配置影响。

# SKILL 数据库设计

## 目标

SKILL 界面包含分类管理、技能管理、模板维护、标签筛选、默认分析框架和后续使用统计。数据库默认使用 SQLite，生产环境可通过 SQLAlchemy 切换到 MySQL 等关系型数据库。

默认连接：

```env
BUSINESS_DATABASE_URL=sqlite:///data/skills.db
```

MySQL 示例：

```env
BUSINESS_DATABASE_URL=mysql+pymysql://user:password@host:3306/njbank?charset=utf8mb4
```

## 表结构

| 表名 | 说明 |
| --- | --- |
| `skill_categories` | SKILL 分类，支持父子分类、启停和排序 |
| `skills` | SKILL 主表，保存名称、分类、简述、执行模板、JSON schema 字符串、状态和版本 |
| `skill_versions` | SKILL 模板版本记录，用于回滚和审计 |
| `skill_tags` | 标签字典，可用于搜索、筛选和视觉标识 |
| `skill_tag_links` | SKILL 与标签多对多关系 |
| `analysis_frameworks` | 可复用分析框架，如线上/线下默认框架 |
| `framework_skills` | 框架中的 SKILL 编排顺序及自定义配置 |
| `skill_usage_logs` | SKILL 使用记录，支撑热度、耗时和成功率统计 |

## 兼容策略

- 主键使用 `Integer autoincrement`，SQLite/MySQL 都支持。
- JSON 配置字段使用 `Text` 存储 JSON 字符串，避免 SQLite/MySQL JSON 方言差异。
- 布尔字段使用 SQLAlchemy `Boolean`，由方言适配到 SQLite integer 或 MySQL boolean/tinyint。
- 时间字段使用 `DateTime(timezone=True)` 与 `func.now()`，由方言生成默认值。
- 外键行为只使用通用的 `CASCADE`、`SET NULL`、`RESTRICT`。
- 所有业务唯一约束和常用查询字段均建立索引，方便迁移到 MySQL 后继续使用。

## 初始化

```bash
cd backend
python scripts/init_skill_db.py
```

初始化会创建业务库表，并写入当前 SKILL 界面的默认分类、8 个默认 SKILL 和默认线上分析框架。

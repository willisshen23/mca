# MySQL 不可达

## 常见原因
- MySQL 服务未启动或重启中
- 网络隔离/防火墙变更（生产 MySQL 在独立网段）
- 连接信息变更（host/port/密码轮换）

## 处置步骤
1. 联系 DBA 确认 MySQL 实例状态
2. 确认 `backend/.env` 的 DATABASE_HOST/PORT/USERNAME/PASSWORD 与 DBA 提供的一致
3. 若是密码轮换：更新 .env 后重启主应用
4. 数据库恢复前，主应用的会话历史与技能库功能不可用，但已生成报告不受影响

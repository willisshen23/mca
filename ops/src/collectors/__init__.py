from __future__ import annotations

from src.collectors import bank_api, database, llm_gateway, logs, process, system

COLLECTORS = {
    "process": process.collect,
    "logs": logs.collect,
    "system": system.collect,
    "database": database.collect,
    "llm_gateway": llm_gateway.collect,
    "bank_api": bank_api.collect,
}

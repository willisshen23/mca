# Backend Layering

The backend is organized by dependency direction and responsibility:

## `agent/`

Agent orchestration and LangGraph runtime code.

- Contains graph state, node registry, workflow selection, workflow execution, prompts, and agent capability nodes.
- Agent nodes may call `services/` to fetch data, read uploads, export reports, or persist/query state.
- Agent nodes must not directly implement or call low-level HTTP, file, or database logic.

## `domain/`

Pure business rules and domain transformations.

- Contains component definitions and report/template rules.
- Must not depend on FastAPI, LangGraph, SQLAlchemy, databases, or LLM clients.
- Should be deterministic and easy to unit test with plain Python data.

## `services/`

Application coordination layer.

- Owns use-case level coordination between agent/API and infrastructure.
- May open database sessions, call integration gateways, or delegate to file adapters.
- Should keep complex scoring/parsing/business algorithms in `domain/`.

## `infrastructure/`

External systems and technical adapters.

- Contains SQLAlchemy models/session/seed data, bank marketing integrations, function-call adapters, static files, file readers, and format converters.
- May depend on external libraries.
- Should not contain agent workflow orchestration or business process decisions.

## `shared/`

Business-neutral helpers only.

- Use for generic utilities with no marketing, agent, report, database, or HTTP meaning.
- If a helper needs business vocabulary, place it in `domain/` or `services/` instead.

## API Boundary

`api/` remains the FastAPI transport layer. Routers should validate HTTP inputs/outputs and delegate work to `services/`.

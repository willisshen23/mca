from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.infrastructure.db.models import Base
from src.infrastructure.db.seed import seed_default_skills
from src.infrastructure.db.session import SessionLocal, engine


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_default_skills(db)
    print(f"Business database initialized ({engine.dialect.name}).")


if __name__ == "__main__":
    main()

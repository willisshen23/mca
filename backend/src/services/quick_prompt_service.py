from __future__ import annotations

from sqlalchemy.orm import Session

from src.infrastructure.db.models import QuickPrompt

MAX_TEXT_LENGTH = 500


def list_enabled_quick_prompts(db: Session) -> list[str]:
    rows = (
        db.query(QuickPrompt)
        .filter(QuickPrompt.is_enabled.is_(True))
        .filter(QuickPrompt.text != "")
        .order_by(QuickPrompt.sort_order.asc(), QuickPrompt.id.asc())
        .all()
    )
    return [row.text.strip() for row in rows if row.text.strip()]


def list_all_quick_prompts(db: Session) -> list[QuickPrompt]:
    return db.query(QuickPrompt).order_by(QuickPrompt.sort_order.asc(), QuickPrompt.id.asc()).all()


def save_quick_prompts(db: Session, items: list[dict]) -> list[QuickPrompt]:
    # 校验
    for index, item in enumerate(items):
        text = str(item.get("text") or "").strip()
        if not text:
            raise ValueError(f"第 {index + 1} 条话术不能为空")
        if len(text) > MAX_TEXT_LENGTH:
            raise ValueError(f"第 {index + 1} 条话术超过 {MAX_TEXT_LENGTH} 字")

    # 删除现有记录
    db.query(QuickPrompt).delete()

    # 按传入顺序重建
    saved = []
    for index, item in enumerate(items):
        prompt = QuickPrompt(
            text=str(item.get("text") or "").strip(),
            sort_order=index,
            is_enabled=bool(item.get("is_enabled", True)),
        )
        db.add(prompt)
        saved.append(prompt)

    db.commit()
    for prompt in saved:
        db.refresh(prompt)
    return saved

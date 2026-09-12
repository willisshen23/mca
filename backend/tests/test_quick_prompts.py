from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.infrastructure.db.models import Base, QuickPrompt
from src.infrastructure.db.session import get_db
from src.main import app

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function")
def client():
    Base.metadata.create_all(bind=engine)
    yield TestClient(app)
    Base.metadata.drop_all(bind=engine)


def test_list_enabled_prompts_returns_empty_by_default(client):
    response = client.get("/activity/api/quick-prompts")
    assert response.status_code == 200
    assert response.json() == {"prompts": []}


def test_admin_save_and_list(client):
    payload = {
        "prompts": [
            {"text": "话术一", "is_enabled": True},
            {"text": "话术二", "is_enabled": False},
        ]
    }
    response = client.put("/activity/api/quick-prompts/admin", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["prompts"]) == 2
    assert data["prompts"][0]["text"] == "话术一"
    assert data["prompts"][1]["is_enabled"] is False

    response = client.get("/activity/api/quick-prompts")
    assert response.status_code == 200
    assert response.json() == {"prompts": ["话术一"]}


def test_admin_save_rejects_empty_text(client):
    payload = {
        "prompts": [
            {"text": "话术一", "is_enabled": True},
            {"text": "  ", "is_enabled": True},
        ]
    }
    response = client.put("/activity/api/quick-prompts/admin", json=payload)
    assert response.status_code == 400


def test_admin_save_reorders(client):
    payload = {
        "prompts": [
            {"text": "A", "is_enabled": True},
            {"text": "B", "is_enabled": True},
        ]
    }
    client.put("/activity/api/quick-prompts/admin", json=payload)

    # 交换顺序后保存
    payload = {
        "prompts": [
            {"text": "B", "is_enabled": True},
            {"text": "A", "is_enabled": True},
        ]
    }
    response = client.put("/activity/api/quick-prompts/admin", json=payload)
    data = response.json()
    assert data["prompts"][0]["text"] == "B"
    assert data["prompts"][0]["sort_order"] == 0
    assert data["prompts"][1]["text"] == "A"
    assert data["prompts"][1]["sort_order"] == 1


def test_admin_save_deletes_missing_items(client):
    payload = {
        "prompts": [
            {"text": "A", "is_enabled": True},
            {"text": "B", "is_enabled": True},
        ]
    }
    client.put("/activity/api/quick-prompts/admin", json=payload)

    payload = {
        "prompts": [
            {"text": "A", "is_enabled": True},
        ]
    }
    response = client.put("/activity/api/quick-prompts/admin", json=payload)
    data = response.json()
    assert len(data["prompts"]) == 1

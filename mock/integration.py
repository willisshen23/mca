"""Integrate mock campaign API into the main backend app.

Usage in backend/src/api/routers/__init__.py:
    from mock.integration import include_mock_router
    include_mock_router(router)
"""
from __future__ import annotations

from fastapi import APIRouter

from mock.router import router as campaign_router


def include_mock_router(parent_router: APIRouter, prefix: str = "/mock") -> None:
    """Register mock campaign routes under the given parent router.

    Args:
        parent_router: The parent APIRouter to attach to.
        prefix: URL prefix for mock endpoints (default: /mock).
    """
    parent_router.include_router(campaign_router, prefix=prefix)

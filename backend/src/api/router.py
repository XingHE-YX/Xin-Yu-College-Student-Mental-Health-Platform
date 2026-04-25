"""Versioned business API router aggregation for the Xinyu backend."""

from fastapi import APIRouter

from src.api.routes.consents import router as consent_router
from src.api.routes.student_auth import router as student_auth_router

api_router = APIRouter()
api_router.include_router(consent_router)
api_router.include_router(student_auth_router)

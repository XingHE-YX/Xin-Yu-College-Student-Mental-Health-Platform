"""Versioned business API router aggregation for the Xinyu backend."""

from fastapi import APIRouter

from src.api.routes.admin_alerts import router as admin_alerts_router
from src.api.routes.admin_auth import router as admin_auth_router
from src.api.routes.admin_dashboard import router as admin_dashboard_router
from src.api.routes.admin_posts import router as admin_posts_router
from src.api.routes.consents import router as consent_router
from src.api.routes.questionnaires import router as questionnaire_router
from src.api.routes.reports import router as report_router
from src.api.routes.student_auth import router as student_auth_router
from src.api.routes.treehole import router as treehole_router

api_router = APIRouter()
api_router.include_router(admin_auth_router)
api_router.include_router(admin_alerts_router)
api_router.include_router(admin_dashboard_router)
api_router.include_router(admin_posts_router)
api_router.include_router(consent_router)
api_router.include_router(questionnaire_router)
api_router.include_router(report_router)
api_router.include_router(student_auth_router)
api_router.include_router(treehole_router)

from apps.admin_custom.api import router as admin_router
from apps.homeworks.api import router as homework_router
from apps.mental_health.api import router as mental_health_router
from apps.modules.api import router as module_router
from apps.quizzes.api import router as quiz_router
from apps.users.api import router as user_router

API_ROUTERS = [
    ("/users/", user_router),
    ("/modules/", module_router),
    ("/quizzes/", quiz_router),
    ("/homeworks/", homework_router),
    ("/mental-health/", mental_health_router),
    ("/admin/", admin_router),
]

__all__ = [API_ROUTERS]


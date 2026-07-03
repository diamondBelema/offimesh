"""FastAPI router modules."""
from app.routers.auth import router as auth_router
from app.routers.users import router as users_router
from app.routers.devices import router as devices_router
from app.routers.tokens import router as tokens_router
from app.routers.transactions import router as transactions_router
from app.routers.settlements import router as settlements_router
from app.routers.wallet import router as wallet_router
from app.routers.webhooks import router as webhooks_router
from app.routers.health import router as health_router

__all__ = [
    "auth_router",
    "users_router",
    "devices_router",
    "tokens_router",
    "transactions_router",
    "settlements_router",
    "wallet_router",
    "webhooks_router",
    "health_router",
]

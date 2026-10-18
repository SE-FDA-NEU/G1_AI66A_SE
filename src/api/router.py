
"""Main API router combining all v1 route endpoints."""

from fastapi import APIRouter

from src.api.auth import router as auth_router
from src.api.cart import router as cart_router
from src.api.health import router as health_router
from src.api.orders import router as orders_router
from src.api.products import router as products_router
from src.api.seller_orders import router as seller_orders_router
from src.api.seller_products import router as seller_products_router

api_router = APIRouter(prefix="/api/v1")

# Include sub-routers
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(cart_router)
api_router.include_router(products_router)
api_router.include_router(orders_router)
api_router.include_router(seller_orders_router)
api_router.include_router(seller_products_router)

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views_api import ProductViewSet, SaleViewSet

router = DefaultRouter()
router.register("productos", ProductViewSet, basename="api-producto")
router.register("ventas", SaleViewSet, basename="api-venta")

urlpatterns = [
    path("", include(router.urls)),
]
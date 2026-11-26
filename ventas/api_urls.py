from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views_api import ProductViewSet, SaleViewSet
from .views_es04 import AnalisisIAView, AnalyticsSummaryView

router = DefaultRouter()
router.register("productos", ProductViewSet, basename="api-producto")
router.register("ventas", SaleViewSet, basename="api-venta")

urlpatterns = [
    path("", include(router.urls)),
    path("analytics/resumen/", AnalyticsSummaryView.as_view(), name="api-analytics-resumen"),
    path("ia/analisis/", AnalisisIAView.as_view(), name="api-ia-analisis"),
]
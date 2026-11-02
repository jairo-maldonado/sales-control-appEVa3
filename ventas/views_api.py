import logging

from django.db import transaction
from django.db.models import ProtectedError
from django.utils.dateparse import parse_date
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Producto, Venta
from .serializers import ProductSerializer, SaleSerializer

logger = logging.getLogger(__name__)


class IsStaffOrReadOnly(permissions.BasePermission):
    """Authenticated users can read; only staff can create, edit or delete."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return user.is_staff


class SalePermission(permissions.BasePermission):
    """Authenticated users can list, create and edit sales; only staff can delete."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method == "DELETE":
            return user.is_staff
        return True


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Producto.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsStaffOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["codigo", "nombre"]
    ordering_fields = ["nombre", "precio", "stock"]
    ordering = ["nombre"]

    def destroy(self, request, *args, **kwargs):
        product = self.get_object()
        try:
            product.delete()
        except ProtectedError:
            logger.warning("Product %s not deleted: it has sales associated", product.pk)
            return Response(
                {"detail": "No se puede eliminar un producto que tiene ventas asociadas."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], url_path="low-stock")
    def low_stock(self, request):
        queryset = self.filter_queryset(
            self.get_queryset().filter(stock__lte=Producto.LOW_STOCK_THRESHOLD)
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(queryset, many=True).data)


class SaleViewSet(viewsets.ModelViewSet):
    serializer_class = SaleSerializer
    permission_classes = [SalePermission]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        queryset = Venta.objects.prefetch_related("detalles__producto")

        date_from = self.request.query_params.get("fecha_desde")
        date_to = self.request.query_params.get("fecha_hasta")

        if date_from:
            parsed_from = parse_date(date_from)
            if parsed_from is None:
                raise ValidationError({"fecha_desde": "Formato inválido. Use YYYY-MM-DD."})
            queryset = queryset.filter(fecha__gte=parsed_from)

        if date_to:
            parsed_to = parse_date(date_to)
            if parsed_to is None:
                raise ValidationError({"fecha_hasta": "Formato inválido. Use YYYY-MM-DD."})
            queryset = queryset.filter(fecha__lte=parsed_to)

        return queryset

    def destroy(self, request, *args, **kwargs):
        sale = self.get_object()
        with transaction.atomic():
            sale.delete()
        logger.info("Sale %s deleted via API by user %s", sale.folio, request.user.pk)
        return Response(status=status.HTTP_204_NO_CONTENT)
import logging
from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ventas.models import AnalisisIA, DetalleVenta, Producto, Venta
from ventas.services.groq_service import GroqServiceError, ejecutar_analisis_groq

logger = logging.getLogger(__name__)


def _parse_dias(raw_value, default=30):
    if raw_value in (None, ""):
        return default, None
    try:
        dias = int(raw_value)
    except (TypeError, ValueError):
        return None, "El parámetro 'dias' debe ser un número entero."
    if dias < 1 or dias > 365:
        return None, "El parámetro 'dias' debe estar entre 1 y 365."
    return dias, None


def _serialize_analisis(obj):
    return {
        "id": obj.pk,
        "usuario": obj.usuario.username if obj.usuario else None,
        "fecha_creacion": obj.fecha_creacion.isoformat(),
        "enfoque": obj.enfoque,
        "modelo": obj.modelo,
        "estado": obj.estado,
        "datos_entrada": obj.datos_entrada,
        "resultado": obj.resultado,
        "mensaje_error": obj.mensaje_error,
    }


class AnalyticsSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        dias, error = _parse_dias(request.query_params.get("dias"), default=30)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        hoy = timezone.localdate()
        fecha_inicio = hoy - timedelta(days=dias)

        productos = list(Producto.objects.all().order_by("stock", "nombre"))
        total_productos = len(productos)
        sin_stock = sum(1 for p in productos if p.stock == 0)
        stock_bajo = sum(
            1 for p in productos if 0 < p.stock <= Producto.LOW_STOCK_THRESHOLD
        )
        valor_inventario = sum(float(p.precio) * p.stock for p in productos)

        ventas_qs = Venta.objects.filter(fecha__gte=fecha_inicio)
        total_ventas = ventas_qs.count()
        ingresos_periodo = (
            DetalleVenta.objects.filter(venta__fecha__gte=fecha_inicio).aggregate(
                total=Sum("subtotal")
            )["total"]
            or 0
        )

        ventas_por_fecha_qs = (
            ventas_qs.values("fecha")
            .annotate(
                cantidad_ventas=Count("id", distinct=True),
                ingresos=Sum("detalles__subtotal"),
            )
            .order_by("fecha")
        )
        ventas_por_fecha = [
            {
                "fecha": str(row["fecha"]),
                "cantidad_ventas": row["cantidad_ventas"],
                "ingresos": float(row["ingresos"] or 0),
            }
            for row in ventas_por_fecha_qs
        ]

        stock_por_producto = [
            {
                "id": p.pk,
                "codigo": p.codigo,
                "nombre": p.nombre,
                "stock": p.stock,
                "precio": float(p.precio),
                "estado": (
                    "sin_stock"
                    if p.stock == 0
                    else "bajo"
                    if p.stock <= Producto.LOW_STOCK_THRESHOLD
                    else "normal"
                ),
            }
            for p in productos[:15]
        ]

        top_productos_qs = (
            DetalleVenta.objects.filter(venta__fecha__gte=fecha_inicio)
            .values("producto__codigo", "producto__nombre")
            .annotate(unidades=Sum("cantidad"), ingresos=Sum("subtotal"))
            .order_by("-unidades")[:5]
        )
        top_productos = [
            {
                "codigo": row["producto__codigo"],
                "nombre": row["producto__nombre"],
                "unidades": row["unidades"],
                "ingresos": float(row["ingresos"] or 0),
            }
            for row in top_productos_qs
        ]

        return Response(
            {
                "periodo_dias": dias,
                "fecha_inicio": str(fecha_inicio),
                "fecha_fin": str(hoy),
                "kpis": {
                    "total_productos": total_productos,
                    "sin_stock": sin_stock,
                    "stock_bajo": stock_bajo,
                    "valor_inventario": round(valor_inventario, 2),
                    "total_ventas_periodo": total_ventas,
                    "ingresos_periodo": float(ingresos_periodo),
                },
                "ventas_por_fecha": ventas_por_fecha,
                "stock_por_producto": stock_por_producto,
                "top_productos": top_productos,
            },
            status=status.HTTP_200_OK,
        )


class AnalisisIAView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        historial = AnalisisIA.objects.select_related("usuario").all()[:10]
        return Response(
            {"results": [_serialize_analisis(item) for item in historial]},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        enfoque = str(request.data.get("enfoque", "general")).strip().lower()
        dias, error = _parse_dias(request.data.get("dias"), default=30)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        try:
            data = ejecutar_analisis_groq(enfoque=enfoque, dias=dias)
        except GroqServiceError as exc:
            logger.warning("Groq analysis failed (%s): %s", exc.status_code, exc)
            if exc.status_code != status.HTTP_400_BAD_REQUEST:
                AnalisisIA.objects.create(
                    usuario=request.user,
                    enfoque=enfoque,
                    estado=AnalisisIA.ESTADO_ERROR,
                    mensaje_error=str(exc),
                )
            return Response({"detail": str(exc)}, status=exc.status_code)

        registro = AnalisisIA.objects.create(
            usuario=request.user,
            enfoque=enfoque,
            modelo=data["modelo"],
            estado=AnalisisIA.ESTADO_OK,
            datos_entrada=data["datos_entrada"],
            resultado=data["resultado"],
        )
        return Response(_serialize_analisis(registro), status=status.HTTP_201_CREATED)
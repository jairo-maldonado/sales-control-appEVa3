from decimal import Decimal

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.template.response import TemplateResponse
from django.urls import path

from .forms import (
    BaseDetalleVentaFormSet,
    DetalleVentaForm,
    ProductoForm,
    SalesReportForm,
    VentaForm,
)
from .models import DetalleVenta, Producto, Venta

admin.site.site_header = "Control de Ventas - Administración"
admin.site.site_title = "Control de Ventas"
admin.site.index_title = "Gestión de productos y ventas"


def format_clp(value):
    return "$" + f"{value:,.0f}".replace(",", ".")


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    form = ProductoForm
    list_display = ("codigo", "nombre", "precio", "stock")
    search_fields = ("codigo", "nombre")
    ordering = ("nombre",)


class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    form = DetalleVentaForm
    formset = BaseDetalleVentaFormSet
    extra = 1
    fields = ("producto", "cantidad", "precio_unitario", "subtotal")
    readonly_fields = ("subtotal",)


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    form = VentaForm
    inlines = [DetalleVentaInline]
    list_display = ("folio", "cliente", "fecha", "total_display")
    list_filter = ("fecha",)
    date_hierarchy = "fecha"
    search_fields = ("folio", "cliente")
    fields = ("folio", "cliente", "fecha", "total_display")
    readonly_fields = ("folio", "total_display")
    change_list_template = "admin/ventas/venta/change_list.html"

    @admin.display(description="Monto total")
    def total_display(self, obj):
        return format_clp(obj.total)

    def get_urls(self):
        custom_urls = [
            path(
                "sales-report/",
                self.admin_site.admin_view(self.sales_report_view),
                name="ventas_venta_sales_report",
            ),
        ]
        return custom_urls + super().get_urls()

    def sales_report_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied

        form = SalesReportForm(request.GET or None)
        context = {
            **self.admin_site.each_context(request),
            "title": "Reporte de ventas por rango de fechas",
            "form": form,
            "report_ready": False,
        }

        if form.is_valid():
            sales = (
                Venta.objects.filter(
                    fecha__range=(
                        form.cleaned_data["start_date"],
                        form.cleaned_data["end_date"],
                    )
                )
                .annotate(total_amount=Sum("detalles__subtotal"))
                .order_by("fecha", "id")
            )
            grand_total = sum(
                (sale.total_amount or Decimal("0") for sale in sales), Decimal("0")
            )
            context.update(
                {
                    "report_ready": True,
                    "sales": sales,
                    "sales_count": len(sales),
                    "grand_total": grand_total,
                }
            )

        return TemplateResponse(request, "admin/ventas/sales_report.html", context)
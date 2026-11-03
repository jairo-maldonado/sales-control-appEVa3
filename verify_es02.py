from decimal import Decimal

from django.conf import settings
from django.contrib import admin
from django.db import transaction
from django.template.loader import get_template
from django.urls import get_resolver

from ventas.models import DetalleVenta, Producto, Venta


class RollbackSignal(Exception):
    pass


results = []


def record(label, ok, detail=""):
    results.append(ok)
    suffix = " -> " + detail if detail else ""
    print(("[OK]   " if ok else "[FAIL] ") + label + suffix)


registry = admin.site._registry
record("Producto registered in admin", Producto in registry)
record("Venta registered in admin", Venta in registry)

venta_admin = registry.get(Venta)
inline_models = [inline.model for inline in getattr(venta_admin, "inlines", [])]
record("Venta admin has DetalleVenta inline", DetalleVenta in inline_models, str(inline_models))

default_headers = {"Django administration", "Administración de Django"}
header = str(admin.site.site_header)
template_origin = str(get_template("admin/base_site.html").origin.name)
project_templates = str(settings.BASE_DIR / "templates")
branding_in_code = header not in default_headers
branding_in_template = template_origin.startswith(project_templates)
record(
    "Admin branding present",
    branding_in_code or branding_in_template,
    "site_header='" + header + "' | base_site=" + template_origin,
)

try:
    with transaction.atomic():
        product = Producto.objects.create(
            codigo="ZZ-VERIFY-001",
            nombre="Verify product",
            precio=Decimal("1000.00"),
            stock=10,
        )
        sale = Venta.objects.create(cliente="Verify client")
        DetalleVenta.objects.create(venta=sale, producto=product, cantidad=3)
        product.refresh_from_db()
        record("Sale total computed", sale.total == Decimal("3000.00"), str(sale.total))
        record("Stock decremented on sale", product.stock == 7, str(product.stock))
        raise RollbackSignal()
except RollbackSignal:
    print("[INFO] Test data rolled back")

root_names = [str(key) for key in get_resolver().reverse_dict.keys() if isinstance(key, str)]
admin_names = [getattr(url, "name", "") or "" for url in venta_admin.get_urls()]
report_routes = [name for name in root_names + admin_names if "report" in name.lower()]
record("Date report route found", len(report_routes) > 0, str(report_routes))

print("")
print("RESULT: " + str(sum(results)) + "/" + str(len(results)) + " checks passed")
import logging

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import ProtectedError, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from .forms import DetalleVentaFormSet, ProductoForm, VentaForm
from .models import Producto, Venta

logger = logging.getLogger(__name__)

ITEMS_PER_PAGE = 8


def paginate(request, queryset):
    paginator = Paginator(queryset, ITEMS_PER_PAGE)
    return paginator.get_page(request.GET.get("page"))


# ---------------------------------------------------------------- Products

def producto_list(request):
    query = request.GET.get("q", "").strip()
    products = Producto.objects.all()
    if query:
        products = products.filter(
            Q(codigo__icontains=query) | Q(nombre__icontains=query)
        )

    low_stock_count = Producto.objects.filter(
        stock__lte=Producto.LOW_STOCK_THRESHOLD
    ).count()
    if low_stock_count:
        messages.warning(
            request,
            f"Hay {low_stock_count} producto(s) con stock crítico "
            f"({Producto.LOW_STOCK_THRESHOLD} unidades o menos).",
        )

    context = {"page_obj": paginate(request, products), "q": query}
    return render(request, "ventas/producto_list.html", context)


def producto_detail(request, pk):
    product = get_object_or_404(Producto, pk=pk)
    recent_lines = product.detalles.select_related("venta").order_by(
        "-venta__fecha", "-id"
    )[:10]
    context = {"product": product, "recent_lines": recent_lines}
    return render(request, "ventas/producto_detail.html", context)


def producto_create(request):
    if request.method == "POST":
        form = ProductoForm(request.POST)
        if form.is_valid():
            product = form.save()
            logger.info("Product created: %s", product.codigo)
            messages.success(request, f"Producto «{product.nombre}» creado correctamente.")
            return redirect("producto_list")
        messages.error(request, "No se pudo guardar el producto. Revisa los errores.")
    else:
        form = ProductoForm()
    context = {"form": form, "title": "Nuevo producto"}
    return render(request, "ventas/producto_form.html", context)


def producto_update(request, pk):
    product = get_object_or_404(Producto, pk=pk)
    if request.method == "POST":
        form = ProductoForm(request.POST, instance=product)
        if form.is_valid():
            product = form.save()
            logger.info("Product updated: %s", product.codigo)
            messages.success(request, f"Producto «{product.nombre}» actualizado.")
            if product.is_low_stock:
                messages.warning(
                    request,
                    f"Stock crítico: «{product.nombre}» tiene {product.stock} unidad(es).",
                )
            return redirect("producto_list")
        messages.error(request, "No se pudo actualizar el producto. Revisa los errores.")
    else:
        form = ProductoForm(instance=product)
    context = {"form": form, "title": f"Editar producto: {product.nombre}"}
    return render(request, "ventas/producto_form.html", context)


def producto_delete(request, pk):
    product = get_object_or_404(Producto, pk=pk)
    if request.method == "POST":
        name = product.nombre
        try:
            product.delete()
        except ProtectedError:
            messages.error(
                request,
                f"No se puede eliminar «{name}» porque está asociado a ventas registradas.",
            )
            return redirect("producto_list")
        logger.info("Product deleted: %s", name)
        messages.success(request, f"Producto «{name}» eliminado.")
        return redirect("producto_list")
    return render(request, "ventas/producto_confirm_delete.html", {"product": product})


# ------------------------------------------------------------------- Sales

def venta_list(request):
    query = request.GET.get("q", "").strip()
    sales = Venta.objects.annotate(total_amount=Sum("detalles__subtotal"))
    if query:
        sales = sales.filter(Q(folio__icontains=query) | Q(cliente__icontains=query))
    context = {"page_obj": paginate(request, sales), "q": query}
    return render(request, "ventas/venta_list.html", context)


def venta_detail(request, pk):
    sale = get_object_or_404(Venta, pk=pk)
    context = {
        "sale": sale,
        "details": sale.detalles.select_related("producto"),
        "total": sale.total,
    }
    return render(request, "ventas/venta_detail.html", context)


def warn_low_stock_for_sale(request, sale):
    for product in Producto.objects.filter(detalles__venta=sale).distinct():
        if product.is_low_stock:
            messages.warning(
                request,
                f"Stock crítico: «{product.nombre}» quedó con {product.stock} unidad(es).",
            )


def venta_create(request):
    if request.method == "POST":
        form = VentaForm(request.POST)
        formset = DetalleVentaFormSet(request.POST)
        form_is_valid = form.is_valid()
        formset_is_valid = formset.is_valid()
        if form_is_valid and formset_is_valid:
            with transaction.atomic():
                sale = form.save()
                formset.instance = sale
                formset.save()
            messages.success(request, f"Venta {sale.folio} registrada correctamente.")
            warn_low_stock_for_sale(request, sale)
            return redirect("venta_detail", pk=sale.pk)
        messages.error(request, "No se pudo registrar la venta. Revisa los errores.")
    else:
        form = VentaForm()
        formset = DetalleVentaFormSet()
    context = {"form": form, "formset": formset, "title": "Nueva venta"}
    return render(request, "ventas/venta_form.html", context)


def venta_update(request, pk):
    sale = get_object_or_404(Venta, pk=pk)
    if request.method == "POST":
        form = VentaForm(request.POST, instance=sale)
        formset = DetalleVentaFormSet(request.POST, instance=sale)
        form_is_valid = form.is_valid()
        formset_is_valid = formset.is_valid()
        if form_is_valid and formset_is_valid:
            with transaction.atomic():
                form.save()
                formset.save()
            messages.success(request, f"Venta {sale.folio} actualizada.")
            warn_low_stock_for_sale(request, sale)
            return redirect("venta_detail", pk=sale.pk)
        messages.error(request, "No se pudo actualizar la venta. Revisa los errores.")
    else:
        form = VentaForm(instance=sale)
        formset = DetalleVentaFormSet(instance=sale)
    context = {"form": form, "formset": formset, "title": f"Editar venta {sale.folio}"}
    return render(request, "ventas/venta_form.html", context)


def venta_delete(request, pk):
    sale = get_object_or_404(Venta, pk=pk)
    if request.method == "POST":
        folio = sale.folio
        with transaction.atomic():
            sale.delete()
        logger.info("Sale deleted: %s", folio)
        messages.success(request, f"Venta {folio} eliminada. El stock fue restituido.")
        return redirect("venta_list")
    return render(request, "ventas/venta_confirm_delete.html", {"sale": sale})
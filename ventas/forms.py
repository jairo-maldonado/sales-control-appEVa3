from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone

from .models import DetalleVenta, Producto, Venta


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            css_class = "form-select" if isinstance(widget, forms.Select) else "form-control"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css_class}".strip()


class ProductoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Producto
        fields = ["codigo", "nombre", "descripcion", "precio", "stock"]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 3})}

    def clean_codigo(self):
        return self.cleaned_data["codigo"].strip().upper()

    def clean(self):
        cleaned_data = super().clean()
        precio = cleaned_data.get("precio")
        stock = cleaned_data.get("stock")
        if precio is not None and precio < 0:
            self.add_error("precio", "El precio no puede ser negativo.")
        if stock is not None and stock < 0:
            self.add_error("stock", "El stock no puede ser negativo.")
        return cleaned_data


class VentaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Venta
        fields = ["cliente", "fecha"]
        widgets = {
            "fecha": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        cliente = (cleaned_data.get("cliente") or "").strip()
        fecha = cleaned_data.get("fecha")
        if "cliente" in cleaned_data:
            if len(cliente) < 2:
                self.add_error("cliente", "Ingresa el nombre del cliente (mínimo 2 caracteres).")
            else:
                cleaned_data["cliente"] = cliente
        if fecha and fecha > timezone.localdate():
            self.add_error("fecha", "La fecha de la venta no puede ser futura.")
        return cleaned_data


class DetalleVentaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = DetalleVenta
        fields = ["producto", "cantidad", "precio_unitario"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["precio_unitario"].required = False

    def clean(self):
        cleaned_data = super().clean()
        producto = cleaned_data.get("producto")
        cantidad = cleaned_data.get("cantidad")
        precio_unitario = cleaned_data.get("precio_unitario")

        if precio_unitario is not None and precio_unitario < 0:
            self.add_error("precio_unitario", "El precio no puede ser negativo.")

        if producto is None or cantidad is None:
            return cleaned_data

        if cantidad <= 0:
            self.add_error("cantidad", "La cantidad debe ser mayor que 0.")
            return cleaned_data

        available = producto.stock
        if self.instance.pk:
            previous = (
                DetalleVenta.objects.filter(pk=self.instance.pk)
                .values("producto_id", "cantidad")
                .first()
            )
            if previous and previous["producto_id"] == producto.pk:
                available += previous["cantidad"]

        if cantidad > available:
            self.add_error(
                "cantidad",
                f"Stock insuficiente para {producto.nombre}: disponible {available}.",
            )
        return cleaned_data


class BaseDetalleVentaFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        requested = {}
        for form in self.forms:
            data = getattr(form, "cleaned_data", None)
            if not data or data.get("DELETE"):
                continue
            producto = data.get("producto")
            cantidad = data.get("cantidad")
            if producto is None or cantidad is None:
                continue
            requested[producto] = requested.get(producto, 0) + cantidad

        if not requested:
            raise ValidationError("La venta debe incluir al menos un producto.")

        for producto, total_quantity in requested.items():
            stored = 0
            if self.instance.pk:
                stored = (
                    DetalleVenta.objects.filter(venta=self.instance, producto=producto)
                    .aggregate(total=Sum("cantidad"))["total"]
                    or 0
                )
            available = producto.stock + stored
            if total_quantity > available:
                raise ValidationError(
                    f"Stock insuficiente para {producto.nombre}: "
                    f"solicitado {total_quantity}, disponible {available}."
                )


DetalleVentaFormSet = inlineformset_factory(
    Venta,
    DetalleVenta,
    form=DetalleVentaForm,
    formset=BaseDetalleVentaFormSet,
    extra=1,
    can_delete=True,
)


class SalesReportForm(BootstrapFormMixin, forms.Form):
    start_date = forms.DateField(
        label="Desde",
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    end_date = forms.DateField(
        label="Hasta",
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and start_date > end_date:
            raise ValidationError("La fecha inicial no puede ser posterior a la final.")
        return cleaned_data
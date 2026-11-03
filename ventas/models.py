import logging
import uuid
from decimal import Decimal

from django.db import models, transaction
from django.db.models import F, Sum
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)


class Producto(models.Model):
    LOW_STOCK_THRESHOLD = 5

    codigo = models.CharField("código", max_length=30, unique=True)
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField("descripción", blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)

    class Meta:
        ordering = ["nombre"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(precio__gte=0),
                name="producto_precio_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(stock__gte=0),
                name="producto_stock_gte_0",
            ),
        ]

    def __str__(self):
        return f"{self.codigo} - {self.nombre} (stock: {self.stock})"

    @property
    def is_low_stock(self):
        return self.stock <= self.LOW_STOCK_THRESHOLD


class Venta(models.Model):
    folio = models.CharField(max_length=20, unique=True, blank=True, editable=False)
    cliente = models.CharField(max_length=120)
    fecha = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.folio} - {self.cliente}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        needs_folio = is_new and not self.folio

        if needs_folio:
            self.folio = f"TMP-{uuid.uuid4().hex[:12]}"

        with transaction.atomic():
            super().save(*args, **kwargs)
            if needs_folio:
                self.folio = f"V-{self.pk:06d}"
                super().save(update_fields=["folio"])

        if is_new:
            logger.info("Sale created: %s (client: %s)", self.folio, self.cliente)

    @property
    def total(self):
        if not self.pk:
            return Decimal("0")
        result = self.detalles.aggregate(total=Sum("subtotal"))["total"]
        return result or Decimal("0")


class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="detalles")
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        default=0,
        help_text="Dejar en 0 para usar el precio actual del producto.",
    )
    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, editable=False
    )

    class Meta:
        verbose_name = "detalle de venta"
        verbose_name_plural = "detalles de venta"

    def __str__(self):
        return f"{self.cantidad} x {self.producto.nombre}"

    def save(self, *args, **kwargs):
        with transaction.atomic():
            previous = (
                DetalleVenta.objects.filter(pk=self.pk).first() if self.pk else None
            )
            if previous:
                Producto.objects.filter(pk=previous.producto_id).update(
                    stock=F("stock") + previous.cantidad
                )
            if not self.precio_unitario:
                self.precio_unitario = self.producto.precio
            self.subtotal = Decimal(self.cantidad) * self.precio_unitario
            super().save(*args, **kwargs)
            Producto.objects.filter(pk=self.producto_id).update(
                stock=F("stock") - self.cantidad
            )
            logger.info(
                "Stock updated: product %s, sold %s units (sale %s)",
                self.producto_id,
                self.cantidad,
                self.venta_id,
            )


@receiver(pre_delete, sender=DetalleVenta)
def restore_stock_on_delete(sender, instance, **kwargs):
    stored = (
        DetalleVenta.objects.filter(pk=instance.pk)
        .values("producto_id", "cantidad")
        .first()
    )
    if stored:
        Producto.objects.filter(pk=stored["producto_id"]).update(
            stock=F("stock") + stored["cantidad"]
        )
        logger.info(
            "Stock restored: product %s, +%s units", stored["producto_id"], stored["cantidad"]
        )
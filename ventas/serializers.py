import logging
from collections import defaultdict

from django.db import transaction
from rest_framework import serializers

from .models import DetalleVenta, Producto, Venta

logger = logging.getLogger(__name__)


class ProductSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Producto
        fields = [
            "id",
            "codigo",
            "nombre",
            "descripcion",
            "precio",
            "stock",
            "is_low_stock",
        ]

    def validate_precio(self, value):
        if value < 0:
            raise serializers.ValidationError("El precio no puede ser negativo.")
        return value

    def validate_stock(self, value):
        if value < 0:
            raise serializers.ValidationError("El stock no puede ser negativo.")
        return value


class SaleItemReadSerializer(serializers.ModelSerializer):
    producto_codigo = serializers.CharField(source="producto.codigo", read_only=True)
    producto_nombre = serializers.CharField(source="producto.nombre", read_only=True)

    class Meta:
        model = DetalleVenta
        fields = [
            "id",
            "producto",
            "producto_codigo",
            "producto_nombre",
            "cantidad",
            "precio_unitario",
            "subtotal",
        ]
        read_only_fields = fields


class SaleItemWriteSerializer(serializers.Serializer):
    producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.all())
    cantidad = serializers.IntegerField(min_value=1)
    precio_unitario = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        required=False,
        default=0,
    )


class SaleSerializer(serializers.ModelSerializer):
    detalles = SaleItemWriteSerializer(many=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Venta
        fields = ["id", "folio", "cliente", "fecha", "detalles", "total"]
        read_only_fields = ["id", "folio", "total"]

    def validate_cliente(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("El cliente es obligatorio.")
        return value

    def validate_detalles(self, value):
        if not value:
            raise serializers.ValidationError("La venta debe tener al menos un producto.")
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        items = instance.detalles.select_related("producto").order_by("id")
        data["detalles"] = SaleItemReadSerializer(items, many=True).data
        return data

    def create(self, validated_data):
        items = validated_data.pop("detalles")

        requested = defaultdict(int)
        for item in items:
            requested[item["producto"].pk] += item["cantidad"]

        with transaction.atomic():
            locked_products = {
                product.pk: product
                for product in Producto.objects.select_for_update()
                .filter(pk__in=requested.keys())
                .order_by("pk")
            }

            stock_errors = []
            for product_id, quantity in requested.items():
                product = locked_products[product_id]
                if product.stock < quantity:
                    stock_errors.append(
                        f"Stock insuficiente para '{product.nombre}' "
                        f"(disponible: {product.stock}, solicitado: {quantity})."
                    )
            if stock_errors:
                logger.warning("Sale rejected, insufficient stock: %s", stock_errors)
                raise serializers.ValidationError({"detalles": stock_errors})

            sale = Venta.objects.create(**validated_data)
            for item in items:
                DetalleVenta.objects.create(
                    venta=sale,
                    producto=locked_products[item["producto"].pk],
                    cantidad=item["cantidad"],
                    precio_unitario=item["precio_unitario"],
                )

        logger.info("Sale %s completed via API with %s line(s)", sale.folio, len(items))
        return sale

    def update(self, instance, validated_data):
        if "detalles" in validated_data:
            raise serializers.ValidationError(
                {"detalles": "Los detalles no se pueden modificar. Elimine la venta y créela de nuevo."}
            )
        instance.cliente = validated_data.get("cliente", instance.cliente)
        instance.fecha = validated_data.get("fecha", instance.fecha)
        instance.save()
        return instance
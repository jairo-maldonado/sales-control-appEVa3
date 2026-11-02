from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from ventas.models import DetalleVenta, Producto, Venta

# (code, name, category, price, stock)
SAMPLE_PRODUCTS = [
    ("BEB-001", "Bebida cola 1.5 L", "Bebidas", 1800, 40),
    ("BEB-002", "Agua mineral 500 ml", "Bebidas", 900, 60),
    ("SNK-001", "Papas fritas 150 g", "Snacks", 1500, 25),
    ("SNK-002", "Galletas de chocolate", "Snacks", 1200, 30),
    ("LAC-001", "Leche entera 1 L", "Lácteos", 1100, 35),
    ("LAC-002", "Yogurt natural 150 g", "Lácteos", 650, 4),
    ("ABA-001", "Arroz grado 1 - 1 kg", "Abarrotes", 1700, 50),
    ("ABA-002", "Fideos espagueti 400 g", "Abarrotes", 990, 45),
    ("ABA-003", "Aceite vegetal 1 L", "Abarrotes", 2800, 3),
    ("ASE-001", "Detergente líquido 1 L", "Aseo", 3500, 15),
    ("ASE-002", "Papel higiénico 4 un.", "Aseo", 2600, 20),
    ("PAN-001", "Pan de molde", "Panadería", 2200, 0),
]

# (client, days_ago, [(product_code, quantity), ...])
SAMPLE_SALES = [
    ("María González", 6, [("BEB-001", 2), ("SNK-001", 3)]),
    ("Pedro Soto", 3, [("ABA-001", 2), ("ABA-002", 4), ("LAC-001", 2)]),
    ("Camila Rojas", 1, [("ASE-001", 1), ("BEB-002", 6)]),
    ("Cliente mostrador", 0, [("SNK-002", 2), ("LAC-002", 1)]),
]


class Command(BaseCommand):
    help = "Load sample products and sales for demo purposes."

    @transaction.atomic
    def handle(self, *args, **options):
        created_products = 0
        for code, name, category, price, stock in SAMPLE_PRODUCTS:
            _, created = Producto.objects.get_or_create(
                codigo=code,
                defaults={
                    "nombre": name,
                    "descripcion": f"Categoría: {category}",
                    "precio": price,
                    "stock": stock,
                },
            )
            created_products += int(created)

        created_sales = 0
        if not Venta.objects.exists():
            products = Producto.objects.in_bulk(
                [code for code, *_ in SAMPLE_PRODUCTS], field_name="codigo"
            )
            today = timezone.localdate()
            for client, days_ago, lines in SAMPLE_SALES:
                sale = Venta.objects.create(
                    cliente=client, fecha=today - timedelta(days=days_ago)
                )
                for code, quantity in lines:
                    DetalleVenta(
                        venta=sale, producto=products[code], cantidad=quantity
                    ).save()
                created_sales += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed completed: {created_products} products and "
                f"{created_sales} sales created."
            )
        )
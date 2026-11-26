import json
import os
import urllib.error
import urllib.request
from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from ventas.models import DetalleVenta, Producto, Venta

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
ENFOQUES_VALIDOS = {"general", "reposicion", "ventas"}


class GroqServiceError(Exception):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


def construir_contexto_negocio(dias=30):
    hoy = timezone.localdate()
    fecha_inicio = hoy - timedelta(days=dias)

    productos = list(Producto.objects.all())
    sin_stock = [
        {"codigo": p.codigo, "nombre": p.nombre, "stock": p.stock, "precio": float(p.precio)}
        for p in productos
        if p.stock == 0
    ]
    stock_bajo = [
        {"codigo": p.codigo, "nombre": p.nombre, "stock": p.stock, "precio": float(p.precio)}
        for p in productos
        if 0 < p.stock <= Producto.LOW_STOCK_THRESHOLD
    ]

    ventas_periodo = Venta.objects.filter(fecha__gte=fecha_inicio)
    total_ventas_periodo = ventas_periodo.count()
    ingresos_periodo = (
        DetalleVenta.objects.filter(venta__fecha__gte=fecha_inicio).aggregate(
            total=Sum("subtotal")
        )["total"]
        or 0
    )

    top_productos = list(
        DetalleVenta.objects.filter(venta__fecha__gte=fecha_inicio)
        .values("producto__codigo", "producto__nombre", "producto__stock")
        .annotate(unidades=Sum("cantidad"), ingresos=Sum("subtotal"))
        .order_by("-unidades")[:5]
    )
    for item in top_productos:
        item["ingresos"] = float(item["ingresos"] or 0)

    return {
        "fecha_corte": str(hoy),
        "dias_analizados": dias,
        "total_productos": len(productos),
        "cantidad_sin_stock": len(sin_stock),
        "cantidad_stock_bajo": len(stock_bajo),
        "productos_sin_stock": sin_stock[:10],
        "productos_stock_bajo": stock_bajo[:10],
        "total_ventas_periodo": total_ventas_periodo,
        "ingresos_periodo": float(ingresos_periodo),
        "top_productos_vendidos": top_productos,
    }


def _validar_respuesta_ia(data):
    if not isinstance(data, dict):
        raise GroqServiceError("La respuesta del modelo no tiene formato JSON válido.", 502)

    campos_requeridos = {
        "resumen_ejecutivo",
        "nivel_riesgo",
        "acciones_prioritarias",
        "productos_criticos",
    }
    if not campos_requeridos.issubset(data.keys()):
        raise GroqServiceError("La respuesta del modelo está incompleta.", 502)

    if data["nivel_riesgo"] not in {"BAJO", "MEDIO", "ALTO"}:
        data["nivel_riesgo"] = "MEDIO"

    if not isinstance(data["acciones_prioritarias"], list):
        raise GroqServiceError("El campo acciones_prioritarias debe ser una lista.", 502)

    if not isinstance(data["productos_criticos"], list):
        raise GroqServiceError("El campo productos_criticos debe ser una lista.", 502)

    return {
        "resumen_ejecutivo": str(data["resumen_ejecutivo"]).strip(),
        "nivel_riesgo": data["nivel_riesgo"],
        "acciones_prioritarias": [str(a).strip() for a in data["acciones_prioritarias"][:5]],
        "productos_criticos": [str(p).strip() for p in data["productos_criticos"][:5]],
    }


def ejecutar_analisis_groq(enfoque="general", dias=30):
    if enfoque not in ENFOQUES_VALIDOS:
        raise GroqServiceError(
            "Enfoque inválido. Valores permitidos: general, reposicion, ventas.", 400
        )

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise GroqServiceError(
            "Servicio de IA no configurado en el servidor (falta GROQ_API_KEY).", 503
        )

    modelo = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b").strip()
    try:
        timeout = int(os.environ.get("GROQ_TIMEOUT", "10"))
    except ValueError:
        timeout = 10

    contexto = construir_contexto_negocio(dias=dias)

    prompt_sistema = (
        "Eres un analista senior de inventario y ventas para un comercio minorista en Chile. "
        "Analiza estrictamente los datos entregados sin inventar cifras ni productos. "
        "Responde UNICAMENTE con un objeto JSON válido con estas claves exactas: "
        "resumen_ejecutivo (string de 2 a 3 frases claras en español), "
        "nivel_riesgo (exactamente 'BAJO', 'MEDIO' o 'ALTO'), "
        "acciones_prioritarias (lista de 3 a 5 acciones concretas en español), "
        "productos_criticos (lista con nombres de productos que requieren atención inmediata)."
    )

    prompt_usuario = (
        f"Enfoque solicitado: {enfoque}. "
        f"Datos reales del sistema: {json.dumps(contexto, ensure_ascii=False)}"
    )

    payload = {
        "model": modelo,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": prompt_usuario},
        ],
    }

    req = urllib.request.Request(
        GROQ_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "SalesControlES04/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise GroqServiceError(
                "Límite de uso de GroqCloud alcanzado. Intenta nuevamente en unos segundos.",
                429,
            )
        if exc.code in (401, 403):
            raise GroqServiceError(
                "Credenciales de GroqCloud rechazadas por el proveedor.", 502
            )
        raise GroqServiceError(
            f"Error HTTP {exc.code} al consultar el servicio de IA.", 502
        )
    except urllib.error.URLError:
        raise GroqServiceError(
            "No fue posible conectar con GroqCloud o se superó el tiempo de espera.", 504
        )
    except TimeoutError:
        raise GroqServiceError(
            "Tiempo de espera agotado al consultar GroqCloud.", 504
        )

    try:
        contenido = body["choices"][0]["message"]["content"]
        parsed = json.loads(contenido)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        raise GroqServiceError(
            "El proveedor de IA devolvió una respuesta inválida o malformada.", 502
        )

    resultado_validado = _validar_respuesta_ia(parsed)
    return {
        "modelo": modelo,
        "datos_entrada": contexto,
        "resultado": resultado_validado,
    }
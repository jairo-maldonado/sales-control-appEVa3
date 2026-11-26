import json
import os
import urllib.error
import urllib.request
from typing import Any


class GroqServiceError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _build_system_prompt(enfoque: str) -> str:
    enfoque_map = {
        "general": "diagnostico integral de ventas, rotacion e inventario",
        "reposicion": "priorizacion de reposicion de stock, quiebres y productos criticos",
        "rentabilidad": "margenes, productos mas vendidos e impulso de ingresos",
    }
    foco = enfoque_map.get(enfoque, enfoque_map["general"])
    return (
        "Eres un analista de inteligencia comercial para una tienda en Chile. "
        f"Responde unicamente con un objeto JSON valido (sin markdown ni texto extra) enfocado en {foco}. "
        "El JSON debe contener exactamente estas claves: "
        '"resumen_ejecutivo" (string breve y claro en espanol), '
        '"nivel_riesgo" (string: "BAJO", "MEDIO" o "ALTO"), '
        '"acciones_prioritarias" (lista de 3 a 5 strings cortos), '
        '"productos_criticos" (lista de strings con nombres de productos en riesgo o sin stock).'
    )


def _build_user_prompt(contexto: dict[str, Any], enfoque: str) -> str:
    return (
        f"Enfoque solicitado: {enfoque}\n"
        f"Datos comerciales reales:\n{json.dumps(contexto, ensure_ascii=False, default=str)}"
    )


def _extract_json_payload(raw_text: str) -> dict[str, Any]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise GroqServiceError("La respuesta del modelo no contiene un JSON valido.", 502)
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise GroqServiceError("La respuesta del modelo esta incompleta.", 502) from exc

    if not isinstance(parsed, dict):
        raise GroqServiceError("El formato JSON devuelto por el modelo no es valido.", 502)

    resumen = str(parsed.get("resumen_ejecutivo") or parsed.get("resumen") or "").strip()
    riesgo = str(parsed.get("nivel_riesgo") or parsed.get("riesgo") or "MEDIO").strip().upper()
    if riesgo not in {"BAJO", "MEDIO", "ALTO"}:
        riesgo = "MEDIO"

    acciones_raw = parsed.get("acciones_prioritarias") or parsed.get("acciones") or []
    if isinstance(acciones_raw, str):
        acciones = [acciones_raw.strip()] if acciones_raw.strip() else []
    elif isinstance(acciones_raw, list):
        acciones = [str(item).strip() for item in acciones_raw if str(item).strip()]
    else:
        acciones = []

    criticos_raw = parsed.get("productos_criticos") or parsed.get("criticos") or []
    if isinstance(criticos_raw, str):
        criticos = [criticos_raw.strip()] if criticos_raw.strip() else []
    elif isinstance(criticos_raw, list):
        criticos = [str(item).strip() for item in criticos_raw if str(item).strip()]
    else:
        criticos = []

    if not resumen and not acciones:
        raise GroqServiceError("La respuesta del modelo esta incompleta.", 502)

    if not resumen:
        resumen = "Analisis generado con recomendaciones operativas para ventas e inventario."

    return {
        "resumen_ejecutivo": resumen,
        "nivel_riesgo": riesgo,
        "acciones_prioritarias": acciones[:5],
        "productos_criticos": criticos[:8],
    }


def generar_diagnostico_groq(contexto: dict[str, Any], enfoque: str = "general") -> dict[str, Any]:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise GroqServiceError(
            "Servicio de IA no configurado en el servidor (falta GROQ_API_KEY).",
            503,
        )

    model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b").strip() or "openai/gpt-oss-20b"
    timeout_raw = os.environ.get("GROQ_TIMEOUT", "15").strip()
    try:
        timeout = max(5, min(60, int(timeout_raw)))
    except ValueError:
        timeout = 15

    url = "[https://api.groq.com/openai/v1/chat/completions](https://api.groq.com/openai/v1/chat/completions)"
    payload = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 1500,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _build_system_prompt(enfoque)},
            {"role": "user", "content": _build_user_prompt(contexto, enfoque)},
        ],
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise GroqServiceError(
            f"Error HTTP {exc.code} al consultar el servicio de IA. {detail[:180]}".strip(),
            502,
        ) from exc
    except urllib.error.URLError as exc:
        raise GroqServiceError(
            f"No fue posible conectar con GroqCloud: {exc.reason}",
            502,
        ) from exc
    except TimeoutError as exc:
        raise GroqServiceError(
            "El servicio de IA excedio el tiempo de espera configurado.",
            504,
        ) from exc
    except Exception as exc:
        raise GroqServiceError(
            f"Error inesperado al consultar el servicio de IA: {exc}",
            502,
        ) from exc

    choices = body.get("choices") or []
    if not choices:
        raise GroqServiceError("La respuesta del modelo esta incompleta.", 502)

    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if not str(content).strip():
        raise GroqServiceError("La respuesta del modelo esta incompleta.", 502)

    resultado = _extract_json_payload(str(content))
    resultado["modelo"] = model
    return resultado
def ejecutar_analisis_groq(contexto: dict[str, Any], enfoque: str = "general") -> dict[str, Any]:
    return generar_diagnostico_groq(contexto, enfoque=enfoque)
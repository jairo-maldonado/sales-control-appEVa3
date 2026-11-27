# Control de Ventas — Inteligencia Comercial (ES04)

Aplicación web full-stack desarrollada con **Django**, **Django REST Framework**, **SimpleJWT**, **Bootstrap 5**, **Chart.js** y **GroqCloud API** para gestión comercial, analítica de ventas e inventario y diagnóstico inteligente asistido por IA.

## Arquitectura del sistema

- **Frontend SPA (`templates/spa/index.html`, `static/spa/app.js`, `static/spa/es04_dashboard.js`):** consume la API mediante `Bearer JWT` y `JSON`, renderiza KPIs, evolución de ingresos y estado de inventario con **Chart.js**, y muestra el diagnóstico IA e historial persistido.
- **Backend Django + DRF (`core/`, `ventas/`):** autentica con **SimpleJWT** (`/api/token/`, `/api/token/refresh/`), expone `/api/productos/`, `/api/ventas/`, `/api/analytics/resumen/` y `/api/ia/analisis/`, delega la consulta a **GroqCloud** en `ventas/services/groq_service.py` y persiste los datos mediante el ORM de Django.
- **Infraestructura y servicios externos:** base de datos **PostgreSQL** en **Supabase**, modelo `openai/gpt-oss-20b` en **GroqCloud Chat Completions API** (`https://api.groq.com/openai/v1/chat/completions`) y despliegue productivo en **Vercel** (`https://sales-control-app-e-va3.vercel.app/app/`).

## Estructura principal del proyecto

- `core/`: configuración de Django (`settings.py`, `urls.py`, `wsgi.py`) con variables de entorno vía `python-dotenv` y conexión PostgreSQL vía `dj-database-url`.
- `ventas/`: modelos (`Producto`, `Venta`, `DetalleVenta`, `AnalisisIA`), vistas REST y de analítica/IA (`views_es04.py`), integración GroqCloud (`services/groq_service.py`) y migraciones.
- `static/spa/` y `templates/spa/`: interfaz SPA con `Chart.js` para KPIs, evolución de ingresos, estado de inventario, diagnóstico IA e historial persistido.
- `test_es04_endpoints.py`: pruebas automatizadas para `/api/analytics/resumen/` y `/api/ia/analisis/`.

## Variables de entorno (`.env.example`)

- `SECRET_KEY`: clave secreta de Django (`cambia-esta-clave-por-una-segura`).
- `DJANGO_DEBUG`: estado de depuración (`False`).
- `ALLOWED_HOSTS`: dominios autorizados (`localhost,127.0.0.1,.vercel.app`).
- `CSRF_TRUSTED_ORIGINS`: orígenes confiables CSRF (`http://localhost:8000,http://127.0.0.1:8000`).
- `DATABASE_URL`: conexión PostgreSQL / Supabase (`postgresql://usuario:clave@host:6543/postgres?sslmode=require`).
- `CORS_ALLOWED_ORIGINS`: orígenes permitidos en CORS (`http://localhost:8000,http://127.0.0.1:8000`).
- `JWT_ACCESS_MINUTES`: duración token de acceso JWT (`30`).
- `JWT_REFRESH_DAYS`: duración token de refresco JWT (`1`).
- `GROQ_API_KEY`: clave API de GroqCloud (`gsk_tu_clave_de_groq_aqui`).
- `GROQ_MODEL`: modelo de lenguaje en GroqCloud (`openai/gpt-oss-20b`).
- `GROQ_TIMEOUT`: tiempo máximo de espera en segundos (`15`).

## Ejecución local y pruebas

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py runserver

Ejecución de pruebas de ES04:
python manage.py test test_es04_endpoints --keepdb -v 2

Despliegue
Aplicación desplegada en Vercel (https://sales-control-app-e-va3.vercel.app/app/) conectada a PostgreSQL en Supabase y GroqCloud (openai/gpt-oss-20b).

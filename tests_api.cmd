@echo off
setlocal EnableExtensions

rem ---------------------------------------------------------------
rem API test collection - Sales Control API (ES03)
rem Usage in CMD (venv active, server running):
rem   set API_USER=your_username
rem   set API_PASS=your_password
rem   set BASE_URL=https://your-project.vercel.app   (optional, no trailing slash)
rem   tests_api.cmd
rem ---------------------------------------------------------------

if "%BASE_URL%"=="" set "BASE_URL=http://127.0.0.1:8000"
if "%ALLOWED_ORIGIN%"=="" set "ALLOWED_ORIGIN=%BASE_URL%"
set "BLOCKED_ORIGIN=http://evil.example.com"
set "SALE_FILE=%TEMP%\sales_api_test_response.json"
set "ACCESS="
set "REFRESH="
set "PRODUCT_ID="
set "SALE_ID="

if "%API_USER%"=="" goto :missing_credentials
if "%API_PASS%"=="" goto :missing_credentials

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: python no esta en el PATH. Active el entorno con venv\Scripts\activate
  goto :cleanup
)

set "PY_LOGIN=import json,os,urllib.request as r;q=r.Request(os.environ['BASE_URL']+'/api/token/',json.dumps({'username':os.environ['API_USER'],'password':os.environ['API_PASS']}).encode(),{'Content-Type':'application/json'});d=json.load(r.urlopen(q));print(d['access'],d['refresh'])"
for /f "usebackq tokens=1,2" %%a in (`python -c "%PY_LOGIN%"`) do (
  set "ACCESS=%%a"
  set "REFRESH=%%b"
)
if "%ACCESS%"=="" (
  echo ERROR: no se pudo obtener el token. Revise API_USER, API_PASS y BASE_URL.
  goto :cleanup
)

echo.
echo ===== Sales Control API tests contra %BASE_URL% =====

echo.
echo [1] JWT: credenciales invalidas - esperado 401
curl -s -w "\nHTTP status: %%{http_code}\n" -X POST "%BASE_URL%/api/token/" -H "Content-Type: application/json" -d "{\"username\":\"%API_USER%\",\"password\":\"invalid-password-123\"}"

echo.
echo [2] JWT: login valido en /api/token/ - esperado 200
curl -s -o NUL -w "HTTP status: %%{http_code}\n" -X POST "%BASE_URL%/api/token/" -H "Content-Type: application/json" -d "{\"username\":\"%API_USER%\",\"password\":\"%API_PASS%\"}"

echo.
echo [3] JWT: refresh en /api/token/refresh/ - esperado 200
curl -s -o NUL -w "HTTP status: %%{http_code}\n" -X POST "%BASE_URL%/api/token/refresh/" -H "Content-Type: application/json" -d "{\"refresh\":\"%REFRESH%\"}"

echo.
echo [4] Auth: productos sin token - esperado 401
curl -s -w "\nHTTP status: %%{http_code}\n" "%BASE_URL%/api/productos/"

echo.
echo [5] Auth: token invalido - esperado 401
curl -s -w "\nHTTP status: %%{http_code}\n" "%BASE_URL%/api/productos/" -H "Authorization: Bearer invalid.token.value"

echo.
echo [6] Productos con Bearer token y paginacion - esperado 200
curl -s -w "\nHTTP status: %%{http_code}\n" "%BASE_URL%/api/productos/" -H "Authorization: Bearer %ACCESS%"

echo.
echo [7] Busqueda de productos - esperado 200
curl -s -o NUL -w "HTTP status: %%{http_code}\n" "%BASE_URL%/api/productos/?search=a" -H "Authorization: Bearer %ACCESS%"

echo.
echo [8] Ventas filtradas por fechas validas - esperado 200
curl -s -o NUL -w "HTTP status: %%{http_code}\n" "%BASE_URL%/api/ventas/?fecha_desde=2020-01-01&fecha_hasta=2030-12-31" -H "Authorization: Bearer %ACCESS%"

echo.
echo [9] Ventas con fecha invalida - esperado 400
curl -s -w "\nHTTP status: %%{http_code}\n" "%BASE_URL%/api/ventas/?fecha_desde=not-a-date" -H "Authorization: Bearer %ACCESS%"

set "PY_PRODUCT=import json,os,urllib.request as r;q=r.Request(os.environ['BASE_URL']+'/api/productos/?ordering=nombre',headers={'Authorization':'Bearer '+os.environ['ACCESS']});d=json.load(r.urlopen(q));print(next(p['id'] for p in d['results'] if p['stock']>0))"
for /f "usebackq delims=" %%i in (`python -c "%PY_PRODUCT%"`) do set "PRODUCT_ID=%%i"
if "%PRODUCT_ID%"=="" (
  echo.
  echo AVISO: no hay productos con stock; se omiten las pruebas de ventas.
  goto :cors_tests
)

echo.
echo [10] Venta con stock insuficiente - esperado 400
curl -s -w "\nHTTP status: %%{http_code}\n" -X POST "%BASE_URL%/api/ventas/" -H "Authorization: Bearer %ACCESS%" -H "Content-Type: application/json" -d "{\"cliente\":\"cURL test\",\"detalles\":[{\"producto\":%PRODUCT_ID%,\"cantidad\":999999}]}"

echo.
echo [11] Venta valida con transaccion atomica - esperado 201
curl -s -o "%SALE_FILE%" -w "HTTP status: %%{http_code}\n" -X POST "%BASE_URL%/api/ventas/" -H "Authorization: Bearer %ACCESS%" -H "Content-Type: application/json" -d "{\"cliente\":\"cURL test\",\"detalles\":[{\"producto\":%PRODUCT_ID%,\"cantidad\":1}]}"
type "%SALE_FILE%"
echo.

for /f "usebackq delims=" %%i in (`python -c "import json,os;print(json.load(open(os.environ['SALE_FILE']))['id'])"`) do set "SALE_ID=%%i"
if "%SALE_ID%"=="" (
  echo AVISO: la venta no se creo; se omiten las pruebas dependientes.
  goto :cors_tests
)

echo.
echo [12] Detalle de la venta creada - esperado 200
curl -s -o NUL -w "HTTP status: %%{http_code}\n" "%BASE_URL%/api/ventas/%SALE_ID%/" -H "Authorization: Bearer %ACCESS%"

echo.
echo [13] Eliminar la venta de prueba y restaurar stock - esperado 204
curl -s -o NUL -w "HTTP status: %%{http_code}\n" -X DELETE "%BASE_URL%/api/ventas/%SALE_ID%/" -H "Authorization: Bearer %ACCESS%"

:cors_tests
echo.
echo [14] CORS origen permitido - debe mostrar Access-Control-Allow-Origin
curl -s -i -X OPTIONS "%BASE_URL%/api/productos/" -H "Origin: %ALLOWED_ORIGIN%" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: authorization" | findstr /i "HTTP/ access-control-allow-origin"

echo.
echo [15] CORS origen NO permitido - NO debe mostrar Access-Control-Allow-Origin
curl -s -i -X OPTIONS "%BASE_URL%/api/productos/" -H "Origin: %BLOCKED_ORIGIN%" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: authorization" | findstr /i "HTTP/ access-control-allow-origin"

echo.
echo [16] Django Admin ES02 accesible - esperado 200
curl -s -o NUL -w "HTTP status: %%{http_code}\n" "%BASE_URL%/admin/login/"

echo.
echo [17] Cliente SPA accesible - esperado 200
curl -s -o NUL -w "HTTP status: %%{http_code}\n" "%BASE_URL%/app/"

echo.
echo ===== Pruebas finalizadas =====
goto :cleanup

:missing_credentials
echo ERROR: defina las credenciales antes de ejecutar:
echo   set API_USER=su_usuario
echo   set API_PASS=su_clave
exit /b 1

:cleanup
if exist "%SALE_FILE%" del /q "%SALE_FILE%"
endlocal
exit /b 0
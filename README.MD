# Airline Reservation System

Sistema de reservas aéreas con API FastAPI, PostgreSQL y frontend web estático.
El panel gerencial puede trabajar en modo local contra PostgreSQL o en modo AWS
contra una tabla de métricas en Amazon Athena.

## Funcionalidad implementada

### Cliente

- Catálogo de vuelos con asientos disponibles.
- Búsqueda por origen, destino y fecha.
- Reserva con control transaccional de capacidad.
- Clases de reserva: Económica, Ejecutiva y Primera.
- Confirmación con UUID.
- Consulta de una reserva desde el backend.

### API

| Método | Endpoint | Resultado |
| --- | --- | --- |
| `GET` | `/health` | Estado de la aplicación |
| `POST` | `/admin/flights` | Crea un vuelo; acepta `price_cents` y compatibilidad con `price_cent` |
| `GET` | `/flights/search?origin=BOG&destination=MDE&date=YYYY-MM-DD` | Vuelos con asientos |
| `GET` | `/flights/available` | Catálogo de vuelos disponibles |
| `POST` | `/reservations` | Crea una reserva; devuelve `201` |
| `GET` | `/reservations/{id}` | Consulta una reserva o devuelve `404` |
| `GET` | `/analytics/occupancy?route=BOG-MDE&month=YYYY-MM` | Ocupación, vendidos y capacidad |

Los endpoints de vuelos devuelven `price_cents`, tal como exige el contrato del
parcial. La columna física heredada de PostgreSQL se llama `price_cent`; la API
la expone con el nombre contractual.

## Estructura

```text
backend/
  app/
    main.py
    db.py
    models.py
    routes/
      admin.py
      flights.py
      reservations.py
      analytics.py
  tests/
frontend/
  index.html
  manager.html
  css/style.css
  js/app.js
  js/manager.js
cost_projection.yaml
.env.example
```

## Requisitos locales

- Python 3.12 o compatible.
- PostgreSQL 14+ ejecutándose en `localhost:5432`.
- Base de datos `airline_db`.
- Usuario con permisos de lectura/escritura sobre `flights` y `reservations`.
- Node.js no es necesario para ejecutar la aplicación; Playwright se ejecuta
  desde Python para las pruebas E2E.

Instalar dependencias:

```powershell
cd C:\Users\josen\OneDrive\Desktop\airline-project
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

Configurar las variables de entorno copiando `.env.example` a la configuración
local del sistema. No se deben guardar contraseñas reales en el repositorio.
En PowerShell, por ejemplo:

```powershell
$env:DB_HOST = "localhost"
$env:DB_NAME = "airline_db"
$env:DB_USER = "airline_app"
$env:DB_PASSWORD = "tu-password"
```

La aplicación mantiene `DB_PASSWORD=localdev123` como valor heredado únicamente
para facilitar el entorno de desarrollo actual. Debe sobrescribirse siempre en
AWS.

## Ejecución local

Terminal 1, backend:

```powershell
cd C:\Users\josen\OneDrive\Desktop\airline-project\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host :: --port 8000 --reload
```

Terminal 2, frontend:

```powershell
cd C:\Users\josen\OneDrive\Desktop\airline-project\frontend
python -m http.server 5500 --bind 127.0.0.1
```

Abrir:

- Cliente: <http://localhost:5500/index.html>
- Manager: <http://localhost:5500/manager.html>
- Documentación API: <http://localhost:8000/docs>

El backend debe iniciarse con `--host ::` porque las pruebas usan `localhost` y
Windows puede resolverlo primero mediante IPv6.

## Pruebas

Con backend y frontend ejecutándose:

```powershell
cd C:\Users\josen\OneDrive\Desktop\airline-project\backend
pytest tests/test_r1_latency.py -v -s
pytest tests/test_concurrency.py -v -s
pytest tests/test_e2e_frontend.py -v -s
```

Las pruebas E2E cubren búsqueda, reserva, lectura de la reserva y panel
gerencial. Los identificadores `data-testid` se mantienen según el contrato:

- Cliente: `search-origin`, `search-destination`, `search-date`,
  `search-submit`, `flight-row`, `reserve-button`, `passenger-name`,
  `confirm-submit`, `confirmation-id`.
- Manager: `manager-route`, `manager-month`, `manager-load`,
  `occupancy-value`.

## Configuración de analítica

### Desarrollo local

```text
ANALYTICS_BACKEND=postgres
```

En este modo `/analytics/occupancy` calcula el resultado desde PostgreSQL. Es
útil para desarrollo y pruebas, pero no cumple por sí solo la parte de Athena
del despliegue final.

### AWS

```text
ANALYTICS_BACKEND=athena
AWS_REGION=us-east-1
ATHENA_DATABASE=airline_analytics
ATHENA_METRICS_TABLE=route_month_metrics
ATHENA_OUTPUT_LOCATION=s3://<bucket>/athena-results/
```

En este modo el endpoint inicia una consulta Athena, espera su finalización y
devuelve `route`, `month`, `occupancy`, `seats_sold` y `seats_capacity`. La
identidad IAM de la aplicación necesita:

- `athena:StartQueryExecution`
- `athena:GetQueryExecution`
- `athena:GetQueryResults`
- `s3:GetObject` y `s3:PutObject` en el bucket de resultados

No se incluyen credenciales AWS en código; boto3 utiliza el rol IAM de EC2,
ECS o el mecanismo estándar de credenciales del entorno.

## Estado del despliegue AWS

La opción económica que conserva el contrato actual es:

| Componente | Servicio recomendado | Configuración |
| --- | --- | --- |
| Backend FastAPI | EC2 | `t3.small`, una instancia, security group HTTP |
| Frontend | La misma EC2 | Servir archivos estáticos con Nginx |
| PostgreSQL transaccional | RDS | `db.t4g.micro`, single-AZ, almacenamiento pequeño |
| Raw y Parquet | S3 | Buckets separados por prefijo |
| Procesamiento batch | EMR | Solo `m4.large`, terminación automática |
| Catálogo | Glue Data Catalog | Tablas Parquet con partición `month` |
| Consultas | Athena | Tabla `route_month_metrics` |

Variables de producción mínimas:

```text
DB_HOST=<endpoint-rds>
DB_PORT=5432
DB_NAME=airline_db
DB_USER=airline_app
DB_PASSWORD=<secret-manager-or-parameter-store>
ANALYTICS_BACKEND=athena
AWS_REGION=<region>
ATHENA_DATABASE=airline_analytics
ATHENA_METRICS_TABLE=route_month_metrics
ATHENA_OUTPUT_LOCATION=s3://<bucket>/athena-results/
```

Checklist antes de publicar:

1. Crear RDS single-AZ y restringir el security group al backend.
2. Crear buckets S3 privados para raw, curated y resultados Athena.
3. Crear el rol IAM de EC2 con acceso mínimo a Athena y S3.
4. Ejecutar el job EMR y terminar el cluster automáticamente.
5. Registrar en Glue `reservations_curated` y `route_month_metrics`.
6. Cambiar `ANALYTICS_BACKEND` a `athena`.
7. Servir frontend y API detrás de HTTPS y un dominio.
8. Verificar `/health`, R1, R2, R3, R7, R8 y R9.

La cuenta del Learner Lab quedó validada con el harness del parcial usando el
seed `6089` y la región `us-east-1`:

- EC2 `t3.micro`: backend FastAPI y frontend Nginx en una sola instancia.
- RDS PostgreSQL `db.t3.micro`, single-AZ: datos transaccionales.
- S3 `airline-datos`: raw oficial (`flights.csv`, `reservations.csv`) y Parquet.
- EMR `m4.large`: un cluster de 1 master + 2 core, con `--auto-terminate`.
- Glue Data Catalog: `reservations_curated` con 24 particiones y
  `route_month_metrics` con el esquema exacto del contrato.
- Athena: workgroup `primary`, resultados en `s3://airline-proyect/athena-results/`.

El job corregido se encuentra en [spark_job.py](spark_job.py) y aplica C1-C5,
cruza reservas con vuelos para calcular capacidad, y escribe los nombres
contractuales `price_cents` y `revenue_cents`. El endpoint de analítica usa
Athena en producción y devuelve 404 para rutas sin datos.

La validación final ejecutada con el harness fue **23 passed, 70.0/70.0**.
El informe generado está en
[parcial2-harness-estudiantes/parcial2-harness/report.md](parcial2-harness-estudiantes/parcial2-harness/report.md).

## Costos

[cost_projection.yaml](cost_projection.yaml) contiene la proyección inicial sin
un campo total, como exige el enunciado. Se recomienda detener RDS, EC2 y EMR
fuera de las sesiones de trabajo y usar una ejecución pequeña de EMR antes de
procesar los 2 millones de filas.

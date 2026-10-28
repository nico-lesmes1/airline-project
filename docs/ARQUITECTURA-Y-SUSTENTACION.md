# Arquitectura y sustentación del Airline Reservation System

## Flujo general

```text
Navegador
  ├─ Cliente /              ── HTTP ──> EC2: Nginx + frontend estático
  └─ Manager /              ── HTTP ──> EC2: FastAPI :8000
                                      ├─ RDS PostgreSQL (reservas y vuelos)
                                      └─ Athena ──> Glue Catalog ──> S3 Parquet

S3 raw CSV ──> EMR Spark ──> S3 curated Parquet ──> Glue/Athena
```

## Responsabilidad de cada componente

- **EC2 t3.micro:** sirve Nginx y ejecuta FastAPI.
- **RDS PostgreSQL db.t3.micro:** guarda vuelos, reservas y transacciones de
  booking. `SELECT ... FOR UPDATE` impide vender el mismo asiento dos veces.
- **S3:** conserva CSV raw, Parquet curado y resultados de Athena.
- **EMR m4.large:** ejecuta `spark_job.py`, limpia C1-C5 y calcula métricas.
  Usa terminación automática para controlar costo.
- **Glue Data Catalog:** registra `reservations_curated` y
  `route_month_metrics`.
- **Athena:** consulta métricas sin afectar la base transaccional.

## Datos

El generador oficial usa `seed=6089` y `rows=2000000`. El dataset analítico
oficial cubre meses de **2023-01 a 2024-12**. El job aplica:

1. Ruta sin espacios y en mayúsculas.
2. Estado recortado y en mayúsculas.
3. Solo `CONFIRMED` y `CANCELLED`.
4. Precio presente y mayor que cero.
5. Un registro por `reservation_id`.

La capacidad se calcula desde `flights.csv`; vendidos y revenue cuentan solo
reservas `CONFIRMED`. Cancelaciones no ocupan asientos.

## Por qué aparecen fechas 2030

No es un error del dataset analítico. El raw oficial del harness contiene
vuelos históricos 2023-2024. Las fechas **2030** pertenecen a los vuelos
transaccionales cargados en PostgreSQL para permitir reservas y demostraciones
del frontend. Son dos flujos separados:

- **Operacional:** vuelos futuros de RDS, actualmente 2030.
- **Analítico:** histórico generado por el seed, 2023-2024.

Por eso se debe buscar una reserva en la página cliente con una fecha 2030 y
consultar el manager con una ruta/mes analítico, por ejemplo `MDE-ADZ` y
`2024-01`.

## Sustentación práctica

### Cliente y reserva

1. Abrir `http://IP/`.
2. Usar el catálogo inicial para ver vuelos disponibles, precio y asientos.
3. O buscar origen, destino y fecha.
4. Pulsar **Reservar**, completar nombre y clase, y confirmar.
5. Mostrar el `reservation_id`.
6. Consultar ese ID desde Swagger: `GET /reservations/{id}`.

### Manager

1. Abrir `http://IP/manager`.
2. Elegir una muestra sugerida o escribir ruta y mes.
3. Mostrar ocupación, vendidos, capacidad y cancelaciones.
4. Comparar con Swagger `GET /analytics/occupancy`.

### Athena

En Athena, base `airline_analytics`:

```sql
SELECT *
FROM route_month_metrics
WHERE route = 'MDE-ADZ' AND month = '2024-01';
```

Top 10:

```sql
SELECT route, SUM(seats_sold) / SUM(seats_capacity) AS occupancy
FROM route_month_metrics
GROUP BY route
ORDER BY occupancy DESC
LIMIT 10;
```

### Comandos de evidencia

```powershell
aws sts get-caller-identity
curl.exe http://IP:8000/health
aws emr list-clusters --region us-east-1 `
  --cluster-states STARTING BOOTSTRAPPING RUNNING WAITING TERMINATING
cd .\parcial2-harness-estudiantes\parcial2-harness
python -m pytest -q
```

El estado correcto de EMR para la sustentación es una lista vacía. La evidencia
completa queda en `report.md`: 23 pruebas aprobadas y 70/70.

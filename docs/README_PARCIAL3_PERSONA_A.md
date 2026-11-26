# Parcial 3 — Persona A: eventos, vista en vivo y landing zone

Este documento describe lo que implementa Persona A, cómo se relaciona con
R1–R4 y R11, y el orden para comprobarlo. No incluye el ETL ni el esquema en
estrella de Persona B. La semilla del equipo es **6089**.

> **Estado de validación de esta revisión:** `backend/tests/test_partial3_events.py`
> pasó: **5 passed** usando un entorno Python temporal y
> `DB_POOL_MIN=0`/`DB_POOL_MAX=1` (los casos sustituyen la conexión a la base).
> AWS CLI no está disponible en este entorno, así que no se ejecutaron el
> harness contra AWS ni consultas a la cuenta. Las cifras de ejecuciones
> anteriores que aparecían aquí siguen siendo históricas; vuelve a generar los
> informes siguiendo [la guía de consola](./GUIA-EJECUCION-PARCIAL3-CONSOLA.md)
> antes de afirmar resultados AWS actuales.

## Alcance y dependencias

| Requisito | Responsabilidad de Persona A | Estado observable en el repositorio |
|---|---|---|
| R1 | Contrato de eventos y publicación desde búsquedas, reservas y cancelaciones | Implementado en `backend/app/events.py` y las rutas FastAPI |
| R2 | Envío asíncrono para no bloquear búsquedas y manejo de ráfagas | Publicación en `ThreadPoolExecutor`; la comprobación de latencia y pérdida requiere ejecutar el harness |
| R3 | Consumidor de Kinesis, vista por tiempo del evento y conversión | Implementado en `backend/app/live_view.py` y `/analytics/live`; el umbral de 10 s requiere harness |
| R4 | Entrega de eventos JSON a S3 dentro de 5 minutos | Depende de Firehose u otro delivery configurado en AWS; el repositorio no crea Firehose ni el bucket |
| R11 | Stream provisionado mínimo | Scripts `infra/create_stream.sh` y `infra/delete_stream.sh`; el estado desplegado requiere AWS CLI/harness |
| R8 (integración con B) | Rutas HTTP para iniciar y consultar refresh | Adaptador a Glue implementado; solo funciona si Persona B despliega/configura el Glue job |

R8 y R5–R10 no se deben presentar como trabajo completado por Persona A: el
job que transforma la landing zone al star schema pertenece a Persona B. En
ausencia de `GLUE_STAR_JOB_NAME`, `POST /admin/refresh-star` devuelve 503 de
forma explícita; no simula que el ETL haya empezado.

## Qué se hizo, paso a paso

### 1. Se definió un único contrato de eventos

`backend/app/events.py` construye un envoltorio JSON común con `event_id`
UUID, `event_type`, `event_ts` UTC con precisión de segundos y
`schema_version: 1`. Los tipos admitidos son `search_performed`,
`reservation_created` y `reservation_cancelled`.

| Tipo | Campos propios | Partition key de Kinesis |
|---|---|---|
| `search_performed` | `session_id`, `origin`, `destination`, `travel_date`, `results_count` | `session_id` |
| `reservation_created` | `reservation_id`, `flight_id`, `route`, `flight_date`, `fare_class`, `price_cents` | `flight_id` |
| `reservation_cancelled` | Los mismos datos de la reserva original | `flight_id` |

En una búsqueda, `/flights/search` toma `X-Session-Id`; si el header no llega,
genera un identificador de sesión. El evento no lleva el nombre del pasajero
ni otros datos personales. La fecha del evento se genera al producirse la
acción, no al recibirla posteriormente el consumidor.

### 2. Se conectó la publicación con las operaciones de API

- `backend/app/routes/flights.py`: después de obtener el resultado de la
  búsqueda, construye y encola un `search_performed`. No espera la respuesta
  de Kinesis antes de responder al usuario.
- `backend/app/routes/reservations.py`: al crear una reserva, confirma la
  transacción PostgreSQL y después publica `reservation_created`. La
  cancelación bloquea/actualiza la reserva, confirma el cambio y publica
  `reservation_cancelled`.
- `/reservations/{id}/cancel`: la primera cancelación responde 200, una
  reserva desconocida responde 404 y una ya cancelada responde 409. La
  disponibilidad se calcula con reservas cuyo estado es `CONFIRMED`, por lo
  que una cancelación libera el asiento.

`EventPublisher` usa `put_record` con una partition key explícita. El productor
configura timeout de conexión/lectura mediante `KINESIS_PUBLISH_TIMEOUT_SECONDS`
(por defecto 1 segundo), dos intentos máximos del SDK y un pool de workers. Las
reservas/cancelaciones esperan brevemente (0,2 s); si el envío sigue pendiente,
continúa en background. La búsqueda no espera.

**Límite de fiabilidad que debe explicarse:** la cola de `ThreadPoolExecutor`
vive en memoria. Una caída del proceso puede perder eventos que todavía no se
publicaron; los errores del envío se registran en los logs. Esto es una
solución de laboratorio, no una garantía transaccional de producción. Para
evitar perder una reserva entre el `COMMIT` de PostgreSQL y Kinesis, una
solución de producción guardaría una fila de outbox en la misma transacción y
un dispatcher idempotente la publicaría con reintentos.

### 3. Se implementó el consumidor de la vista rápida

`backend/app/live_view.py` inicia `KinesisLiveConsumer` en el startup de
FastAPI. Usa polling estándar (`ListShards`, `GetShardIterator`,
`GetRecords`), no Enhanced Fan-Out. Los eventos válidos se insertan en
`live_stream_events`; `event_id` es clave primaria y los reintentos se
deduplican con `ON CONFLICT DO NOTHING`. El índice sobre `event_ts` ayuda al
filtro de ventana y los eventos de más de una hora se limpian periódicamente.

`GET /analytics/live?window=5` acepta ventanas de 1 a 60 minutos. El cálculo
filtra por `event_ts` entre la hora actual UTC y el límite de la ventana:

```json
{
  "window_minutes": 5,
  "searches": 10,
  "reservations": 3,
  "cancellations": 1,
  "conversion": 0.3
}
```

La conversión usa reservas creadas / búsquedas, y devuelve cero si no hay
búsquedas. Esta ruta rápida consulta PostgreSQL operacional, no Athena. La
consulta analítica del esquema en estrella es otra ruta y pertenece a Persona
B.

### 4. Se conectó la operación de refresh con Glue

`backend/app/routes/admin.py` expone `POST /admin/refresh-star` y
`GET /admin/refresh-status`. `backend/app/star_refresh.py` solicita y consulta
una ejecución de AWS Glue usando el rol IAM del backend y el nombre
`GLUE_STAR_JOB_NAME`. El inicio pasa `RAW_EVENTS_URI` y
`ATHENA_STAR_DATABASE` cuando existen. El estado se traduce a `RUNNING`,
`SUCCEEDED` o `FAILED`.

Esta parte es un adaptador, no el proceso ETL. Para completar R8, Persona B
debe crear el Glue job, IAM, catálogo y tablas; entonces se verifica que la
ejecución concluya dentro de 900 segundos. No se debe cambiar el 503 de
configuración ausente por una respuesta de éxito ficticia.

### 5. Se definió la landing zone como servicio de despliegue

La API publica en Kinesis; el repositorio no tiene un escritor propio a S3 ni
un script de provisionamiento de Firehose. El deployment debe configurar
Firehose (u otro consumidor de entrega) como destino del stream, escribir JSON
sin PII en `raw_events_uri` y usar compresión gzip si se desea. Configura el
buffer de Firehose a no más de 60 segundos para dejar margen al límite R4 de
300 segundos. La entrega puede repetirse, por lo que Persona B debe deduplicar
por `event_id`.

Comprueba el delivery real con:

```powershell
aws firehose describe-delivery-stream --region $env:AWS_REGION `
  --delivery-stream-name $env:FIREHOSE_NAME
aws s3 ls $env:RAW_EVENTS_URI --recursive
```

La respuesta debe mostrar Firehose activo, origen Kinesis correcto, destino
S3 correcto y buffer adecuado. La existencia de objetos en el prefijo no
demuestra que los 20.000 eventos del replay llegaron: R4 se valida contando
los `event_id` distintos con el harness.

### 6. Se añadieron scripts de ciclo de vida de Kinesis

- `infra/create_stream.sh` crea el stream si no existe, en modo provisionado
  con un shard. Si ya existe, verifica que sea `PROVISIONED`, tenga como máximo
  un shard, retención no mayor de 24 horas y cero consumidores EFO.
- `infra/delete_stream.sh` requiere `DELETE_STREAM_CONFIRM=yes` y espera a
  que AWS confirme el borrado.

Los scripts no modifican un stream existente que no cumpla el perfil: fallan
con un mensaje explícito. Ejecútalos con Git Bash, WSL o CloudShell y fija
`AWS_REGION` y `STREAM_NAME` de manera que coincidan exactamente con
`parcial3-harness-estudiantes/config.yaml`.

### 7. Se fijó la semilla del equipo

La semilla correcta es **6089**:

- `parcial3-harness-estudiantes/config.yaml` ya especifica `seed: 6089`.
- Se corrigieron `parcial3-harness-estudiantes/config.example.yaml` y el
  ejemplo de uso en `airline_data/generate_p3.py` para que coincidan con ella.
- Generación de referencias:

```powershell
Set-Location C:\Users\User\Desktop\airline-project\parcial3-harness-estudiantes
python -m airline_data.generate_p3 --seed 6089 --out ref/
```

El harness y la generación de referencias deben usar la misma semilla para
que los datos de referencia correspondan al equipo.

## Cómo comprobar cada requisito con AWS CLI

### Identidad y región

```powershell
aws sts get-caller-identity
aws configure list
```

Confirma que las credenciales temporales estén vigentes, y que cuenta/región
sean las esperadas antes de consultar o modificar recursos.

### R11: configuración mínima del stream

```powershell
aws kinesis describe-stream-summary --region $env:AWS_REGION `
  --stream-name $env:STREAM_NAME `
  --query "StreamDescriptionSummary.{Status:StreamStatus,Mode:StreamModeDetails.StreamMode,Shards:OpenShardCount,RetentionHours:RetentionPeriodHours,Consumers:ConsumerCount}" `
  --output table
aws kinesis list-shards --region $env:AWS_REGION `
  --stream-name $env:STREAM_NAME --output table
```

El resultado esperado es `ACTIVE`, `PROVISIONED`, un shard abierto, retención
menor o igual a 24 horas y `Consumers = 0`. El harness R11 es la comprobación
reproducible final.

### R1 y R2: registros de Kinesis

1. Envía búsqueda, reserva y cancelación por API, anotando `X-Session-Id`,
   `reservation_id` y hora UTC.
2. Usa `list-shards`, `get-shard-iterator` con
   `--shard-iterator-type AT_TIMESTAMP` y `get-records` para leer el stream.
3. Decodifica `Records[].Data` de Base64 a UTF-8/JSON y comprueba:
   `event_type`, `event_ts`, `schema_version`, campos obligatorios,
   partition key, ID único y ausencia de `passenger_name`.
4. Para R2, el harness envía 200 búsquedas en concurrencia 50 y mide p95; el
   criterio es p95 máximo de 1 segundo y 200 eventos.

La sección de lectura de stream en
[la guía de consola](./GUIA-EJECUCION-PARCIAL3-CONSOLA.md) incluye el bloque
PowerShell que decodifica `Data`. `GetRecords` puede requerir varias páginas.

### R3: ventana de la vista en vivo

```powershell
Invoke-RestMethod "$env:BACKEND_URL/analytics/live?window=5"
```

Compara la respuesta antes y después de emitir acciones. Debe aumentar dentro
de 10 segundos por eventos actuales; un replay con fechas antiguas no debe
contarse como actividad reciente. El harness verifica ambos casos y la
conversión.

### R4: entrega a S3

```powershell
aws firehose describe-delivery-stream --region $env:AWS_REGION `
  --delivery-stream-name $env:FIREHOSE_NAME
aws s3 ls $env:RAW_EVENTS_URI --recursive
```

Descarga un objeto `.gz` representativo y busca un `event_id` tras
descomprimirlo. Para el criterio de aceptación, ejecuta R4 del harness: debe
encontrar todos los IDs distintos del replay en no más de 300 segundos.

## Pruebas y estado verificable

Pruebas unitarias locales de Persona A:

```powershell
Set-Location C:\Users\User\Desktop\airline-project\backend
$env:DB_POOL_MIN = "0"
$env:DB_POOL_MAX = "1"
python -m pytest tests\test_partial3_events.py -q
```

Pruebas AWS de R1–R4 y R11:

```powershell
Set-Location C:\Users\User\Desktop\airline-project\parcial3-harness-estudiantes
python -m pytest tests\test_1_stream.py tests\test_3_cost.py -k "not test_projection" -q
```

El harness puede emitir eventos y crear objetos en tu cuenta; ejecútalo solo
contra recursos propios. Guarda `report.md` y `report.json`. R12 se ejecuta
aparte o quitando el filtro anterior. R8 no queda aprobado hasta que Persona B
entregue y despliegue el Glue job.

Las pruebas unitarias en `backend/tests/test_partial3_events.py` cubren la
construcción de eventos, keys, publicación JSON, parseo de `event_ts` y
cálculo de métricas. El resultado actual de esas pruebas y de las pruebas AWS
debe informarse a partir de una ejecución reciente, no de números copiados de
un informe antiguo.

## Pilares Well-Architected

- **Performance Efficiency (R2–R3):** publicación fuera de la ruta síncrona de
  búsquedas y contadores operacionales directamente desde el stream.
- **Reliability (R1–R4):** IDs de evento, partition keys de negocio, reintentos
  del SDK y deduplicación del consumidor; la cola en memoria no es durable y
  se documenta como limitación.
- **Security:** se excluyen datos personales de los eventos y se usan roles/
  credenciales estándar AWS, no claves codificadas en el repositorio.
- **Cost Optimization / Sustainability (R11):** un shard provisionado, sin
  Enhanced Fan-Out, retención por defecto y eliminación explícita del stream
  al finalizar las pruebas.

## Referencias

- [Contrato de eventos](./CONTRATO.md)
- [Guía de ejecución desde consola](./GUIA-EJECUCION-PARCIAL3-CONSOLA.md)
- [Contrato del harness parcial 3](../parcial3-harness-estudiantes/contract/EVENTS.md)
- [Harness parcial 3](../parcial3-harness-estudiantes/README.md)

# Parcial 3 — Implementación de Persona A

## Alcance

Este documento describe la parte de eventos y camino rápido del parcial 3:
publicar búsquedas, reservas y cancelaciones en Kinesis; calcular la vista
operacional desde un consumidor del stream; aterrizar los eventos en S3;
añadir cancelación y las rutas de administración; y validar que el stream
cumple R11.

El star schema y su ETL (R5–R10, además del trabajo de datos requerido por R8)
no se incluyen en esta parte. Las rutas de refresh delegan a un AWS Glue job
configurado por `GLUE_STAR_JOB_NAME`; ese job debe ser implementado y
desplegado en la parte de star schema.

## Flujo implementado

```text
Navegador
   |
   v
FastAPI
   |-- GET /flights/search
   |       `-- crea search_performed (session_id como partition key)
   |
   |-- POST /reservations
   |       `-- confirma transacción y crea reservation_created
   |
   `-- POST /reservations/{id}/cancel
           `-- cancela transacción y crea reservation_cancelled
                  |
                  v
          Publicador Kinesis
          (cola en proceso + timeout/retries SDK)
                  |
                  v
          Kinesis Data Stream
             |             \
             |              `--> Firehose --> S3 (JSON gzip)
             |
             `--> consumidor de polling
                    |
                    v
              PostgreSQL live_stream_events
              (event_id único, event_ts indexado)
                    |
                    v
              GET /analytics/live
```

El publicador crea el evento después de consultar los resultados de búsqueda o
de confirmar la operación transaccional. En particular, reservas y
cancelaciones se publican después del `COMMIT` y esperan como máximo 0.2 s por
la respuesta rápida del publicador; si vence ese tiempo, el envío continúa en
background. Las búsquedas se encolan sin esperar, para no penalizar el camino
de alta frecuencia. Los errores asíncronos se escriben en el log del backend;
las llamadas AWS tienen timeout configurable mediante
`KINESIS_PUBLISH_TIMEOUT_SECONDS`.

La cola en memoria satisface el camino de demostración, pero no es un outbox
durable: un cierre abrupto del proceso puede perder eventos que aún no se
enviaron. Para producción, se recomienda insertar una fila de outbox en la
misma transacción de la reserva/cancelación y publicar desde un dispatcher
idempotente; esto evita la ventana entre el commit de PostgreSQL y el envío a
Kinesis.

## Contrato de eventos

Cada registro JSON contiene:

| Campo | Descripción |
|---|---|
| `event_id` | UUID distinto por evento |
| `event_type` | `search_performed`, `reservation_created` o `reservation_cancelled` |
| `event_ts` | UTC, formato `YYYY-MM-DDTHH:MM:SSZ`, momento de la acción |
| `schema_version` | `1` |

| Acción | Datos específicos | Partition key |
|---|---|---|
| Búsqueda | `session_id`, origen, destino, fecha de viaje y cantidad de resultados | `session_id` del encabezado `X-Session-Id`; si falta, se genera uno |
| Reserva | `reservation_id`, `flight_id`, ruta, fecha, clase y precio en centavos | `flight_id` |
| Cancelación | Mismos campos de la reserva original | `flight_id` |

No se envía el nombre del pasajero ni otro dato personal. La implementación
está en `backend/app/events.py`; los puntos de publicación están en
`backend/app/routes/flights.py` y `backend/app/routes/reservations.py`.

## API

| Método y ruta | Comportamiento |
|---|---|
| `POST /reservations/{id}/cancel` | Devuelve la reserva cancelada con `200`; `404` si no existe; `409` si ya estaba cancelada. El conteo de asientos solo considera reservas confirmadas, por lo que la cancelación libera el asiento. |
| `GET /analytics/live?window=5` | Devuelve búsquedas, reservas, cancelaciones y `conversion` dentro de una ventana de 1–60 minutos. |
| `POST /admin/refresh-star` | Inicia el job indicado por `GLUE_STAR_JOB_NAME`, devuelve `202` con el `job_id`; devuelve `503` si el job no está configurado. |
| `GET /admin/refresh-status` | Traduce el estado de Glue a `RUNNING`, `SUCCEEDED` o `FAILED`. |

`/analytics/live` consulta una tabla operacional poblada exclusivamente por el
consumidor de Kinesis, no por Athena. La consulta compara `event_ts` con la
hora UTC actual, excluye eventos atrasados fuera de la ventana y calcula la
conversión como reservas creadas / búsquedas, con cero búsquedas igual a
`0.0`. El `event_id` es clave primaria para que varios workers no cuenten dos
veces el mismo registro.

El consumidor hace polling estándar (`GetRecords`) y no crea consumidores
Enhanced Fan-Out. El registro operacional conserva una hora de eventos para
consultas en vivo y se limpia periódicamente. El índice por `event_ts` acelera
el filtro temporal.

## Landing zone

La cuenta ya dispone de un Kinesis Data Stream y un Firehose con origen en ese
stream y destino en un bucket S3. Firehose escribe eventos comprimidos en
`s3://taller-kinesis-636683574371-20261111/sensores/`. El objeto existente en
esa ruta termina en `.gz`; el harness del parcial 3 descomprime gzip al leer.
La configuración de buffer observada es **1 MB o 60 segundos**, lo que ocurra
primero. Por eso el objetivo de entrega de cinco minutos deja margen para
entrega y polling de S3.

Firehose ofrece una landing administrada sin código de escritura S3. El costo
es una latencia por buffering y los cargos de Firehose/S3; para el volumen
pequeño del laboratorio resulta más simple que mantener un escritor propio.
La entrega puede repetirse, por lo que el ETL de la parte B debe deduplicar por
`event_id`.

## Validación de AWS y requisitos

AWS CLI se comprobó con `aws sts get-caller-identity`: la sesión está
autenticada en la cuenta `636683574371`, rol temporal `voclabs`, región
`us-east-1`. El backend respondió `200` en `/health` en la instancia EC2
`i-042430a53734dacab`.

Lectura AWS verificada antes de esta implementación:

| Requisito | Estado | Evidencia |
|---|---|---|
| R1 | Validado | Harness: 30/30 búsquedas y 4/4 eventos de 3 reservas más 1 cancelación; esquema, particiones, `event_ts` y ausencia de PII pasaron. |
| R2 | Validado | Harness: 200/200 eventos, HTTP 200 y p95 de 0.749 s con concurrencia 50 (límite: 1 s). |
| R3 | Validado | Harness: deltas de 10 búsquedas, 3 reservas y 1 cancelación; conversión correcta. Tras reproducir 17,000 eventos antiguos, la vista mostró 240 búsquedas, debajo del límite de 1,700. |
| R4 | Validado | Firehose `ACTIVE`, buffer 1 MB/60 s; el harness encontró 19,912/19,912 eventos distintos en S3 tras 61 s (límite: 300 s). |
| R11 | Validado | Harness: stream `PROVISIONED`, 1 shard, 24 h de retención, 0 consumidores EFO. |
| Refresh star | Integración preparada | Las rutas delegan a Glue; actualmente la cuenta no contiene un Glue job, por lo que no se afirma que el refresh ETL funcione. |

La ejecución parcial de `tests/test_1_stream.py` y `test_stream_is_minimal`
terminó con **6 passed**. Los requisitos de Persona A suman **27/27 puntos**
verificados; el informe global muestra 27/70 porque R5–R10 y R12 no forman
parte de esta selección. Se corrigió además el nombre de la columna de vuelos
para coincidir con el esquema PostgreSQL real (`price_cents`). Los dos workers
de Uvicorn serializan el DDL de inicialización y las escrituras por lote con
locks transaccionales de PostgreSQL; en la validación final ambos iniciaron
correctamente y no se registraron deadlocks.

Los endpoints de cancelación respondieron `200` al cancelar, `404` para un
UUID válido inexistente y `409` al cancelar de nuevo una reserva cancelada.
`GET /admin/refresh-status` respondió `200`; `POST /admin/refresh-star`
respondió `503` de forma explícita porque aún no existe/configuraron el Glue
job de la parte B.

No se eliminaron recursos AWS durante esta implementación porque el stream,
Firehose y el bucket de landing son necesarios para R1–R4. Tampoco se borraron
archivos existentes del proyecto. El ZIP temporal de despliegue se eliminará
tras terminar la validación. Ambos scripts pasaron `bash -n`; `create_stream.sh`
se ejecutó idempotentemente contra el stream existente y confirmó su perfil
mínimo. `delete_stream.sh` no se ejecutó porque borraría el stream requerido
por la API y Firehose; úsalo solo cuando el equipo ya no necesite esta parte.

## Ciclo de vida y costos

`infra/create_stream.sh` crea el stream solo si no existe, en modo provisionado
con un shard; la retención predeterminada es 24 horas. No registra consumidores
EFO. `infra/delete_stream.sh` elimina únicamente el stream indicado mediante
`STREAM_NAME` y requiere `DELETE_STREAM_CONFIRM=yes` para reducir el riesgo de
borrado accidental.

La proyección en `cost_projection.yaml` incluye Kinesis, S3 y Athena. La línea
de Kinesis estima 200 horas de uso al mes usando la tarifa ilustrativa de
$0.015 por shard-hora que figura en
`parcial3-harness-estudiantes/pricing.yaml`, equivalente a $3.00. Si se
confirma esa tarifa y el shard permanece activo durante 730 horas, el costo de
shard-hora sería aproximadamente $10.95, antes del volumen de escrituras y de
otros cargos. El propio archivo marca esos precios como ilustrativos y no
verificados. Verifica los precios vigentes con la
[página oficial de precios de Kinesis Data Streams](https://aws.amazon.com/kinesis/data-streams/pricing/)
o AWS Pricing Calculator. Si se suspende el trabajo, elimina el stream solo
después de detener los consumidores que lo necesitan y confirmar que no se
requiere la landing zone; no lo borres durante la validación de R1–R4.

Esto prioriza los pilares Well-Architected de **Performance Efficiency**
(consumo de eventos en segundos), **Reliability** (partition keys por clave
de negocio, reintentos SDK y deduplicación en la vista), **Security**
(sin PII en el stream y sin credenciales estáticas), **Cost Optimization**
(un shard, sin EFO, Firehose existente) y **Sustainability** (recursos
temporales eliminables y retención predeterminada).

## Comandos

Verificar sesión:

```powershell
aws sts get-caller-identity
aws kinesis describe-stream-summary --stream-name taller-kinesis-sensores-636683574371
aws firehose describe-delivery-stream --delivery-stream-name taller-kinesis-firehose-636683574371
```

Crear o validar el stream:

```bash
STREAM_NAME=taller-kinesis-sensores-636683574371 AWS_REGION=us-east-1 bash infra/create_stream.sh
```

Ejecutar pruebas unitarias nuevas:

```powershell
cd C:\Users\josen\OneDrive\Desktop\airline-project\backend
python -m pytest tests/test_partial3_events.py -q
```

Ejecutar únicamente R1–R4 y R11 del harness del parcial 3:

```powershell
cd C:\Users\josen\OneDrive\Desktop\airline-project\parcial3-harness-estudiantes
python -m pytest tests/test_1_stream.py tests/test_3_cost.py -k "not test_projection" -q
```

El harness inyecta hasta 20,000 registros en Kinesis y genera objetos en S3;
ejecútalo solo contra recursos propios y espera a que R4 termine. Los registros
del stream expiran según su retención de 24 horas.

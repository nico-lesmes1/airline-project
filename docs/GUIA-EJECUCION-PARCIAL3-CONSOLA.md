# Guía de ejecución del parcial 3 desde consola

Esta guía ejecuta la parte de Persona A (API, Kinesis, vista en vivo y landing
zone) usando PowerShell y AWS CLI. El star schema/ETL corresponde a Persona B.
Los comandos AWS modifican o consultan recursos de la cuenta configurada:
confirma siempre la cuenta, región, stream y bucket antes de ejecutarlos.

## 1. Herramientas y credenciales

Instala Python 3.10 o superior, Git, AWS CLI v2 y Git Bash. Para ejecutar la
aplicación localmente también se necesita PostgreSQL 14 o superior. La prueba
del harness parcial 3 usa `httpx`, `PyYAML` y otras dependencias que se
instalan desde su propio `requirements.txt`.

Abre PowerShell en la carpeta del proyecto:

```powershell
Set-Location C:\Users\User\Desktop\airline-project
python --version
aws --version
```

Inicia Learner Lab y usa sus credenciales temporales de AWS CLI. No las guardes
en archivos del repositorio ni las compartas. En PowerShell define las
variables indicadas por AWS Academy (no sustituyas por credenciales
permanentes):

```powershell
$env:AWS_ACCESS_KEY_ID = "<access-key-temporal>"
$env:AWS_SECRET_ACCESS_KEY = "<secret-key-temporal>"
$env:AWS_SESSION_TOKEN = "<session-token-temporal>"
$env:AWS_DEFAULT_REGION = "us-east-1"
aws sts get-caller-identity
aws configure list
```

Comprueba que el número de cuenta y el rol sean los del Learner Lab. Si
`get-caller-identity` informa `ExpiredToken`, renueva las credenciales desde
Learner Lab y vuelve a definir las variables.

## 2. Usar la semilla 6089

La configuración del parcial 3 debe mantener `seed: 6089` en
`parcial3-harness-estudiantes\config.yaml`. El ejemplo del harness también usa
esa semilla. Genera los archivos de referencia desde la carpeta del harness:

```powershell
Set-Location C:\Users\User\Desktop\airline-project\parcial3-harness-estudiantes
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m airline_data.generate_p3 --seed 6089 --out ref/
```

La salida debe incluir `routes_ref.csv`, `route_category_history.csv` y
`holidays_ref.csv`. La prueba completa del harness crea y reproduce eventos en
AWS; no la ejecutes contra recursos ajenos.

## 3. Configurar el harness y comprobar el destino AWS

Si no existe el archivo local de configuración, copia el ejemplo y edita los
valores de tu cuenta. En PowerShell:

```powershell
Copy-Item config.example.yaml config.yaml
notepad config.yaml
```

Verifica que contenga `seed: 6089`, la URL vigente del backend, el stream,
`raw_events_uri`, workgroup, base de datos Athena y la ruta al archivo de costos.
`config.yaml` contiene nombres de recursos propios del equipo; no lo reemplaces
por valores de otra cuenta.

Exporta los valores que usarán los comandos de esta guía. Usa los valores
exactos de `config.yaml`:

```powershell
$env:AWS_REGION = "us-east-1"
$env:STREAM_NAME = "<nombre-del-stream-de-config.yaml>"
$env:RAW_EVENTS_URI = "s3://<bucket>/<prefijo>/"
$env:BACKEND_URL = "http://<host-del-backend>:8000"
```

Confirma que el CLI encuentra el stream:

```powershell
aws kinesis describe-stream-summary `
  --region $env:AWS_REGION `
  --stream-name $env:STREAM_NAME `
  --query "StreamDescriptionSummary.{Name:StreamName,Status:StreamStatus,Mode:StreamModeDetails.StreamMode,Shards:OpenShardCount,RetentionHours:RetentionPeriodHours,Consumers:ConsumerCount}" `
  --output table
aws kinesis list-shards --region $env:AWS_REGION --stream-name $env:STREAM_NAME --output table
```

Para R11, el resumen debe mostrar `ACTIVE`, `PROVISIONED`, un shard abierto,
retención no mayor a 24 horas y cero consumidores Enhanced Fan-Out.

## 4. Crear/verificar o eliminar el stream

Los scripts están en Bash; ejecútalos desde Git Bash, WSL o AWS CloudShell (no
pegues sintaxis Bash directamente en PowerShell). Desde Git Bash, ve a la raíz
del repositorio y ejecuta:

```bash
export AWS_REGION=us-east-1
export STREAM_NAME="<nombre-del-stream-de-config.yaml>"
bash infra/create_stream.sh
```

El script crea un stream provisionado de un shard si no existe; si existe,
comprueba que cumpla el perfil mínimo y no lo modifica. Repite el resumen de
Kinesis del paso anterior para verificar el resultado.

El borrado es opcional y destruye el stream. Detén antes la API/consumidores y
confirma que ya no necesitas los eventos ni la entrega a S3:

```bash
export AWS_REGION=us-east-1
export STREAM_NAME="<nombre-del-stream-de-config.yaml>"
DELETE_STREAM_CONFIRM=yes bash infra/delete_stream.sh
```

No ejecutes el borrado mientras corras las pruebas R1–R4.

## 5. Arrancar la API

La API requiere una base PostgreSQL con las tablas de negocio `flights` y
`reservations`. Este repositorio no incluye un script que cree esas tablas
desde cero. Puedes usar la base de datos ya provisionada para el proyecto o
configurar una base cuya estructura ya esté inicializada; no asumas que una
instalación PostgreSQL vacía basta.

Para correr la API en local, instala las dependencias raíz en un entorno
virtual y define la conexión a esa base:

```powershell
Set-Location C:\Users\User\Desktop\airline-project
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:DB_HOST = "<host-postgresql>"
$env:DB_PORT = "5432"
$env:DB_NAME = "airline_db"
$env:DB_USER = "<usuario>"
$env:DB_PASSWORD = "<contraseña>"
$env:AWS_REGION = "us-east-1"
$env:KINESIS_STREAM_NAME = $env:STREAM_NAME
$env:KINESIS_PUBLISH_TIMEOUT_SECONDS = "1"
python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Si la API ya está desplegada en EC2, no la arranques otra vez en local: usa
`$env:BACKEND_URL` y verifica la instancia que ya ejecuta el servicio. El
consumidor de Kinesis de la vista en vivo se inicia junto con FastAPI, por lo
que el rol IAM del proceso debe poder leer el stream. No pongas claves AWS en
el código. Si Uvicorn corre en otra consola PowerShell, define allí también
las credenciales temporales de Learner Lab (o usa el rol IAM de EC2); las
variables de entorno solo se heredan del proceso donde fueron definidas.

Comprueba disponibilidad:

```powershell
Invoke-RestMethod "$env:BACKEND_URL/health"
Invoke-WebRequest "$env:BACKEND_URL/docs" -UseBasicParsing | Select-Object StatusCode
```

## 6. Prueba manual de búsqueda, reserva y cancelación

Usa una fecha para la cual exista un vuelo con asientos y cuyo identificador
conozcas. El endpoint de búsqueda acepta `X-Session-Id`; el valor aparecerá en
el evento. Swagger (`/docs`) también permite enviar las solicitudes.

Para evitar depender de datos de prueba preexistentes, crea un vuelo de prueba
con la API (esto agrega una fila de prueba a la base de datos):

```powershell
$flightId = "CLI-" + [guid]::NewGuid().ToString()
$origin = "BOG"
$destination = "MDE"
$date = "2031-03-10"
$flight = Invoke-RestMethod `
  -Method Post `
  -Uri "$env:BACKEND_URL/admin/flights" `
  -ContentType "application/json" `
  -Body (@{ flight_id = $flightId; route = "$origin-$destination"; flight_date = $date; capacity = 5; price_cents = 100000 } | ConvertTo-Json)
$sessionId = "manual-" + [guid]::NewGuid().ToString()
$search = Invoke-WebRequest `
  "$env:BACKEND_URL/flights/search?origin=$origin&destination=$destination&date=$date" `
  -Headers @{ "X-Session-Id" = $sessionId } -UseBasicParsing
$search.StatusCode

$reservation = Invoke-RestMethod `
  -Method Post `
  -Uri "$env:BACKEND_URL/reservations" `
  -ContentType "application/json" `
  -Body (@{ flight_id = $flightId; passenger_name = "Prueba"; fare_class = "ECONOMY" } | ConvertTo-Json)
$reservation
$reservationId = $reservation.reservation_id

curl.exe -i -X POST "$env:BACKEND_URL/reservations/$reservationId/cancel"
curl.exe -i -X POST "$env:BACKEND_URL/reservations/$reservationId/cancel"
$missingId = [guid]::NewGuid().ToString()
curl.exe -i -X POST "$env:BACKEND_URL/reservations/$missingId/cancel"
```

La primera cancelación debe responder 200 y dejar estado `CANCELLED`. Repetirla
debe responder 409. Un UUID inexistente debe responder 404. La reserva libera
el asiento porque la búsqueda solo cuenta reservas `CONFIRMED`.

Comprueba la vista en vivo antes y después de las acciones:

```powershell
Invoke-RestMethod "$env:BACKEND_URL/analytics/live?window=5"
```

Espera unos segundos después de las acciones. Las métricas se cuentan por
`event_ts`; `conversion` es `reservations / searches` (o cero cuando no hay
búsquedas). Eventos de prueba con timestamps antiguos no deben incrementar la
ventana actual.

## 7. Leer eventos del stream con AWS CLI

Obtén el ID del shard:

```powershell
$shardId = aws kinesis list-shards `
  --region $env:AWS_REGION `
  --stream-name $env:STREAM_NAME `
  --query "Shards[0].ShardId" --output text
$start = (Get-Date).ToUniversalTime().AddMinutes(-5).ToString("yyyy-MM-ddTHH:mm:ssZ")
$iterator = aws kinesis get-shard-iterator `
  --region $env:AWS_REGION `
  --stream-name $env:STREAM_NAME `
  --shard-id $shardId `
  --shard-iterator-type AT_TIMESTAMP `
  --timestamp $start `
  --query ShardIterator --output text
```

Lee y decodifica hasta 120 páginas (el límite del CLI por llamada es 10.000
registros). El bucle se detiene cuando encuentra la búsqueda y ambos eventos
de reserva de la prueba manual. Cada `Data` que devuelve AWS es JSON codificado
en Base64:

```powershell
$records = @()
for ($pageNumber = 0; $pageNumber -lt 120 -and $iterator; $pageNumber++) {
  $page = aws kinesis get-records `
    --region $env:AWS_REGION `
    --shard-iterator $iterator `
    --limit 1000 | ConvertFrom-Json
  foreach ($record in $page.Records) {
    $json = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($record.Data))
    $records += [pscustomobject]@{
      PartitionKey = $record.PartitionKey
      Event = ($json | ConvertFrom-Json)
    }
  }
  $iterator = $page.NextShardIterator
  $mine = @($records | Where-Object {
    $_.Event.session_id -eq $sessionId -or $_.Event.reservation_id -eq $reservationId
  })
  if ($mine.Count -ge 3) { break }
  Start-Sleep -Seconds 1
}
$records | ForEach-Object {
  [pscustomobject]@{
    PartitionKey = $_.PartitionKey
    EventType = $_.Event.event_type
    EventId = $_.Event.event_id
    EventTs = $_.Event.event_ts
    SessionId = $_.Event.session_id
    FlightId = $_.Event.flight_id
  }
} | Format-Table
```

Para las búsquedas manuales, encuentra el `session_id` que acabas de enviar:

```powershell
$records | Where-Object { $_.Event.session_id -eq $sessionId } |
  Select-Object PartitionKey, Event
```

La `PartitionKey` debe ser igual a `session_id` en búsquedas y a `flight_id`
en reservas/cancelaciones. Los registros no deben tener `passenger_name`.
`GetRecords` puede devolver menos de 1.000 registros por llamada; por eso el
bucle solicita páginas sucesivas. Si los eventos no aparecen, comprueba la
región, stream, rol IAM, hora UTC y el log del backend.

## 8. Verificar Firehose y S3 (R4)

El código del repositorio no crea Firehose ni el bucket; R4 requiere que la
entrega de Kinesis a S3 esté configurada en la cuenta. Usa el nombre de
Firehose de tu despliegue:

```powershell
$env:FIREHOSE_NAME = "<nombre-del-delivery-stream>"
$firehose = aws firehose describe-delivery-stream `
  --region $env:AWS_REGION `
  --delivery-stream-name $env:FIREHOSE_NAME | ConvertFrom-Json
$firehose.DeliveryStreamDescription | Select-Object DeliveryStreamStatus, DeliveryStreamType
$firehose.DeliveryStreamDescription | ConvertTo-Json -Depth 10
$firehose.DeliveryStreamDescription.Destinations |
  ForEach-Object { $_.ExtendedS3DestinationDescription } |
  Select-Object BucketARN, Prefix, BufferingHints, CompressionFormat
aws s3 ls $env:RAW_EVENTS_URI --recursive
```

Debe estar activo, usar el stream correcto como origen, apuntar al prefijo
`raw_events_uri` correcto y tener intervalo de buffer no superior a 60 segundos.
La llegada a S3 debe suceder dentro de los 300 segundos de R4.

Para revisar un objeto gzip específico desde PowerShell, copia primero su URI
completa de `aws s3 ls`:

```powershell
$env:S3_OBJECT = "s3://<bucket>/<objeto>.gz"
aws s3 cp $env:S3_OBJECT .\landing-sample.gz
python -c "import gzip; print(gzip.open('landing-sample.gz','rt',encoding='utf-8').read()[:2000])"
```

Busca el `event_id` de tu acción dentro del texto descomprimido. Para validar
el conjunto de 20.000 eventos del replay, usa el test R4 del harness; listar
objetos por sí solo no prueba que cada `event_id` llegó.

## 9. Ejecutar el harness de Persona A

Abre una segunda consola PowerShell y, desde la raíz del proyecto:

```powershell
Set-Location C:\Users\User\Desktop\airline-project\parcial3-harness-estudiantes
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest tests\test_1_stream.py tests\test_3_cost.py -k "not test_projection" -q
```

Ese selector ejecuta R1–R4 y R11, pero excluye deliberadamente R12 (proyección
de costos). Para correr también R12:

```powershell
python -m pytest tests\test_1_stream.py tests\test_3_cost.py -q
```

El harness escribe `report.md` y `report.json` en su carpeta y reproduce
20.000 eventos en el stream. Conserva ambos informes con la entrega. Los
umbrales y pruebas son la evidencia final para R1–R4 y R11; una prueba manual
no los sustituye.

R8 (refresh del star schema) depende del job Glue de Persona B. El adaptador
`POST /admin/refresh-star` devuelve 503 si `GLUE_STAR_JOB_NAME` no está
configurado. No declares R8 ni la reconstrucción analítica como completa hasta
que exista el job, sus argumentos IAM/S3 estén configurados y pase la prueba
correspondiente.

## 10. Detener procesos

Detén Uvicorn con `Ctrl+C`. Cuando finalice toda la validación del equipo,
decide si el stream se debe conservar; si no hace falta y Firehose ya no lo
consume, elimínalo usando la confirmación del paso 4. No borres buckets ni
objetos de S3 con estos pasos.

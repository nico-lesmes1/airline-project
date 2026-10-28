# Guía para usar el entorno desde otro computador

## Qué permanece en AWS

El entorno desplegado ya contiene EC2, RDS, S3, Glue, Athena y las tablas
Parquet. El segundo computador no debe recrear esos recursos. Solo necesita
acceso a Internet, el repositorio, Python, AWS CLI y las credenciales
temporales del Learner Lab.

## Instalación inicial

```powershell
git clone https://github.com/nico-lesmes1/airline-project.git
cd airline-project
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r .\parcial2-harness-estudiantes\parcial2-harness\requirements.txt
python -m playwright install chromium
```

Si el repositorio no incluye los últimos cambios, copia la carpeta completa
desde el computador original. No copies `.venv`; créalo de nuevo.

## Credenciales y región

Inicia el Learner Lab y copia sus credenciales de **AWS Details > AWS CLI**:

```powershell
$env:AWS_ACCESS_KEY_ID="..."
$env:AWS_SECRET_ACCESS_KEY="..."
$env:AWS_SESSION_TOKEN="..."
$env:AWS_DEFAULT_REGION="us-east-1"
aws sts get-caller-identity
```

Las credenciales son temporales. Si aparece `ExpiredToken`, vuelve a copiarlas.
Nunca las guardes en el repositorio.

## Actualizar la IP

La IP pública puede cambiar:

```powershell
aws ec2 describe-instances --region us-east-1 `
  --filters Name=instance-state-name,Values=running `
  --query "Reservations[].Instances[].PublicIpAddress" --output text
```

Actualiza esa IP en
`parcial2-harness-estudiantes/parcial2-harness/config.yaml`:

```yaml
backend:
  base_url: "http://IP:8000"
frontend:
  base_url: "http://IP"
```

## Verificación y pruebas

```powershell
curl.exe http://IP:8000/health
cd .\parcial2-harness-estudiantes\parcial2-harness
python -m pytest -q
```

El resultado esperado es `23 passed` y `HARNESS SCORE: 70.0 / 70.0`.
El informe queda en `report.md` y `report.json`.

Los tests pueden ejecutarse desde cualquier computador, EC2, CloudShell o CI.
Para R8 y R9 se requiere Chromium/Playwright; por eso un computador local o una
EC2 preparada es más sencillo que CloudShell.

## Interfaces

Con la IP vigente:

- Cliente: `http://IP/`
- Panel gerencial: `http://IP/manager`
- Swagger: `http://IP:8000/docs`

## Datos y EMR

Los datos ya procesados están en:

```text
s3://airline-datos/raw/flights.csv
s3://airline-datos/raw/reservations.csv
s3://airline-datos/curated/reservations_curated/
s3://airline-datos/curated/route_month_metrics/
```

No regeneres los 2 millones ni ejecutes EMR para las pruebas normales. Si se
requiere reconstruirlos, usa el seed oficial:

```powershell
cd .\parcial2-harness-estudiantes\parcial2-harness
python -m airline_data.generate --seed 6089 --rows 2000000 --out raw
```

Después habría que subir los CSV a S3 y ejecutar el job EMR con terminación
automática. EMR no debe quedar en estado `RUNNING` o `WAITING`.

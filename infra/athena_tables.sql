-- 1. Base de datos
CREATE DATABASE IF NOT EXISTS airline_analytics;

-- 2. Tabla de reservas curadas (La que genera el PySpark de B1)
CREATE EXTERNAL TABLE IF NOT EXISTS airline_analytics.reservations_curated (
  reservation_id string,
  flight_id string,
  route string,
  fare_class string,
  price_cents bigint,
  status string
)
PARTITIONED BY (month string)
STORED AS PARQUET
LOCATION 's3://airline-datos/curated/reservations_curated/';

-- 3. Tabla de métricas (La que consultará el endpoint /analytics/occupancy)
CREATE EXTERNAL TABLE IF NOT EXISTS airline_analytics.route_month_metrics (
  route string,
  month string,
  seats_capacity bigint,
  seats_sold bigint,
  occupancy double,
  revenue_cents bigint,
  bookings bigint,
  cancellations bigint
)
STORED AS PARQUET
LOCATION 's3://airline-datos/curated/route_month_metrics/';

MSCK REPAIR TABLE airline_analytics.reservations_curated;
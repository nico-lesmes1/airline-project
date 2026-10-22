# CONTRATO – Parcial 2 Airline Reservation System

Fecha: <hoy>
Firmantes: A (backend + frontend + transaccional), B (data + analítica)

## 1. API (Apéndice A.1 del PDF)

### POST /admin/flights
Request: {flight_id: str, route: str, flight_date: "YYYY-MM-DD", capacity: int, price_cent: int}
Response 201: {flight_id, route, flight_date, capacity, price_cent}
Response 409: {"detail": "flight_id already exists"}

### GET /flights/search?origin=&destination=&date=
Response 200: [{flight_id, route, flight_date, seats_available, price_cent}]
- Vuelos sin asientos se omiten.
- date en formato "YYYY-MM-DD".

### POST /reservations
Request: {flight_id: str, passenger_name: str, fare_class: str}
Response 201: {reservation_id, flight_id, status: "CONFIRMED", passenger_name}
Response 409: {"detail": "no seats available"}
Response 404: {"detail": "flight not found"}

### GET /reservations/{id}
Response 200: mismo shape que POST /reservations
Response 404: {"detail": "reservation not found"}

### GET /analytics/occupancy?route=&month=
Response 200: {route, month, occupancy (0..1), seats_sold, seats_capacity}
Response 404: {"detail": "no data"}
- Implementado por B en backend/app/routes/analytics.py
- A solo lo monta en main.py.

### GET /health
Response 200: {"status": "ok"}

## 2. Esquema BD transaccional (A)

flights(flight_id VARCHAR PK, route VARCHAR, flight_date DATE, capacity INT, price_cent BIGINT)
reservations(reservation_id UUID PK, flight_id VARCHAR FK, passenger_name VARCHAR,
             fare_class VARCHAR, status VARCHAR DEFAULT 'CONFIRMED', created_at TIMESTAMP)

Índices:
- idx_flights_route_date (route, flight_date)
- idx_reservations_flight_status (flight_id, status)

## 3. Tablas Glue (B) – pendiente de que B confirme nombres exactos
- reservations_curated
- route_month_metrics

## 4. Selectores frontend (Apéndice A.3)
Customer (/): search-origin, search-destination, search-date, search-submit,
              flight-row, reserve-button, passenger-name, confirm-submit, confirmation-id
Manager (/manager): manager-route, manager-month, manager-load, occupancy-value

## 5. Definiciones congeladas
- month: string "YYYY-MM" (mes de flight_date)
- occupancy: confirmed_seats_sold / total_capacity (cancelled NO cuentan)
- seats_sold y bookings: solo status='CONFIRMED'
- confirmation-id en frontend: texto exacto del reservation_id (sin espacios extra)
- occupancy-value en frontend: porcentaje con al menos 1 decimal, ej. "78.4%"

## 6. Reglas de convivencia
- B es dueño de: spark/, infra/emr/, infra/glue/, infra/athena/, cost_projection.yaml,
  backend/app/routes/analytics.py, prompt_log/B.md
- A es dueño de: backend/app/main.py, models.py, db.py, routes/admin.py,
  routes/flights.py, routes/reservations.py, frontend/, config.yaml (URLs), prompt_log/A.md
- Cambios al contrato requieren PR y aprobación del otro.
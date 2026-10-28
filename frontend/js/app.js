// Cambia esta URL si sirves el backend desde otro host/puerto
const API = window.AIRLINE_API_URL || `${window.location.protocol}//${window.location.hostname}:8000`;

let selectedFlightId = null;

function addReserveListeners() {
  document.querySelectorAll('[data-testid="reserve-button"]').forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedFlightId = btn.getAttribute("data-flight-id");
      document.getElementById("selected-flight-id").textContent = selectedFlightId;
      const flight = btn.closest('[data-testid="flight-row"]');
      document.getElementById("reservation-summary").textContent =
        `Reserva seleccionada: ${flight.querySelector(".flight-route").textContent} · ${flight.querySelector(".flight-meta").textContent}`;
      document.getElementById("reserve-panel").hidden = false;
      document.getElementById("confirmation").hidden = true;
      document.getElementById("reserve-error").textContent = "";
      document.querySelector('[data-testid="passenger-name"]').focus();
    });
  });
}

function renderFlightCards(flights, target, emptyMessage) {
  target.innerHTML = "";
  if (flights.length === 0) {
    target.innerHTML = `<p class="empty-state">${emptyMessage}</p>`;
    return;
  }
  flights.forEach((f) => {
    const row = document.createElement("div");
    row.setAttribute("data-testid", "flight-row");
    row.className = "flight-row";
    row.innerHTML = `
      <span class="flight-details">
        <strong class="flight-id">${f.flight_id}</strong>
        <span class="flight-route">${f.route}</span>
        <span class="flight-meta">${f.flight_date} · ${f.seats_available} asientos libres · $${(f.price_cents / 100).toFixed(2)}</span>
        <span class="fare-list">${(f.available_fare_classes || ["ECONOMY", "BUSINESS", "FIRST"]).map((fare) => `<span class="fare-chip">${fare === "ECONOMY" ? "Económica" : fare === "BUSINESS" ? "Ejecutiva" : "Primera"}</span>`).join("")}</span>
      </span>
      <button class="button button-primary" data-testid="reserve-button" data-flight-id="${f.flight_id}">Reservar</button>
    `;
    target.appendChild(row);
    row.addEventListener("click", (event) => {
      if (!event.target.closest('[data-testid="reserve-button"]')) {
        row.querySelector('[data-testid="reserve-button"]').click();
      }
    });
  });
  addReserveListeners();
}

async function loadCatalog() {
  const catalog = document.getElementById("catalog");
  catalog.innerHTML = '<p class="loading-state">Cargando vuelos disponibles...</p>';
  try {
    const response = await fetch(`${API}/flights/available`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderFlightCards(await response.json(), catalog, "No hay vuelos con asientos disponibles.");
  } catch (error) {
    catalog.innerHTML = `<p class="message message-error">No se pudo cargar el catálogo: ${error.message}</p>`;
  }
}

document.getElementById("search-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const origin = document.querySelector('[data-testid="search-origin"]').value.trim().toUpperCase();
  const destination = document.querySelector('[data-testid="search-destination"]').value.trim().toUpperCase();
  const date = document.querySelector('[data-testid="search-date"]').value;

  const url = `${API}/flights/search?origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)}&date=${encodeURIComponent(date)}`;
  const results = document.getElementById("results");
  try {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const flights = await r.json();

    if (flights.length === 0) {
      results.innerHTML = "<p>No hay vuelos disponibles.</p>";
      return;
    }

    renderFlightCards(flights, results, "No hay vuelos disponibles para esa búsqueda.");
  } catch (err) {
    results.innerHTML = `<p style="color:red;">Error: ${err.message}</p>`;
  }
});

document.getElementById("refresh-catalog").addEventListener("click", loadCatalog);
loadCatalog();

const dateInput = document.querySelector('[data-testid="search-date"]');
if (dateInput) {
  dateInput.title = "Los vuelos operacionales disponibles están cargados en el catálogo.";
}

document.querySelector('[data-testid="confirm-submit"]').addEventListener("click", async () => {
  const passengerName = document.querySelector('[data-testid="passenger-name"]').value.trim();
  const fareClass = document.getElementById("fare-class").value;
  const errEl = document.getElementById("reserve-error");
  errEl.textContent = "";

  if (!passengerName) { errEl.textContent = "Falta el nombre"; return; }
  if (!selectedFlightId) { errEl.textContent = "Selecciona un vuelo primero"; return; }

  try {
    const r = await fetch(`${API}/reservations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        flight_id: selectedFlightId,
        passenger_name: passengerName,
        fare_class: fareClass,
      }),
    });

    if (r.status === 201) {
      const data = await r.json();
      document.querySelector('[data-testid="confirmation-id"]').textContent = data.reservation_id;
      document.getElementById("confirmation").hidden = false;
      document.getElementById("reserve-panel").hidden = true;
    } else if (r.status === 409) {
      errEl.textContent = "Sin asientos disponibles.";
    } else if (r.status === 404) {
      errEl.textContent = "El vuelo no existe.";
    } else {
      errEl.textContent = `Error inesperado (${r.status}).`;
    }
  } catch (err) {
    errEl.textContent = `Error de red: ${err.message}`;
  }
});
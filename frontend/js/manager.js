const API = window.AIRLINE_API_URL || `${window.location.protocol}//${window.location.hostname}:8000`;

function loadFields(route, month) {
  document.querySelector('[data-testid="manager-route"]').value = route;
  document.querySelector('[data-testid="manager-month"]').value = month;
  document.querySelector('[data-testid="manager-load"]').click();
}

document.querySelectorAll(".sample-chip").forEach((button) => {
  button.addEventListener("click", () => loadFields(button.dataset.route, button.dataset.month));
});

document.querySelector('[data-testid="manager-load"]').addEventListener("click", async () => {
  const route = document.querySelector('[data-testid="manager-route"]').value.trim().toUpperCase();
  const month = document.querySelector('[data-testid="manager-month"]').value.trim();
  const valueEl = document.querySelector('[data-testid="occupancy-value"]');
  const errEl = document.getElementById("manager-error");
  const summaryEl = document.getElementById("manager-summary");
  const soldEl = document.getElementById("sold-value");
  const capacityEl = document.getElementById("capacity-value");
  errEl.textContent = "";
  valueEl.textContent = "—";
  soldEl.textContent = "—";
  capacityEl.textContent = "—";
  summaryEl.textContent = "Cargando datos...";

  if (!route || !month) { errEl.textContent = "Faltan ruta o mes"; return; }

  try {
    const r = await fetch(`${API}/analytics/occupancy?route=${encodeURIComponent(route)}&month=${encodeURIComponent(month)}`);
    if (r.status === 404) {
      errEl.textContent = "Sin datos para esa ruta y mes.";
      summaryEl.textContent = "No hay vuelos registrados para los filtros seleccionados.";
      return;
    }
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    // porcentaje con 3 decimales → "78.400%"
    valueEl.textContent = `${(data.occupancy * 100).toFixed(3)}%`;
    soldEl.textContent = data.seats_sold.toLocaleString("es-CO");
    capacityEl.textContent = data.seats_capacity.toLocaleString("es-CO");
    summaryEl.textContent = `Ocupación de ${route} durante ${month}. Las cancelaciones no cuentan como vendidos.`;
  } catch (err) {
    errEl.textContent = `Error: ${err.message}`;
    summaryEl.textContent = "No fue posible cargar el indicador.";
  }
});
const API = window.AIRLINE_API_URL || "http://localhost:8000";

document.querySelector('[data-testid="manager-load"]').addEventListener("click", async () => {
  const route = document.querySelector('[data-testid="manager-route"]').value.trim().toUpperCase();
  const month = document.querySelector('[data-testid="manager-month"]').value.trim();
  const valueEl = document.querySelector('[data-testid="occupancy-value"]');
  const errEl = document.getElementById("manager-error");
  const summaryEl = document.getElementById("manager-summary");
  errEl.textContent = "";
  valueEl.textContent = "—";
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
    summaryEl.textContent = `${data.seats_sold} asientos vendidos de ${data.seats_capacity} disponibles.`;
  } catch (err) {
    errEl.textContent = `Error: ${err.message}`;
    summaryEl.textContent = "No fue posible cargar el indicador.";
  }
});
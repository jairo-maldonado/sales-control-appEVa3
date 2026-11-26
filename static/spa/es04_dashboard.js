(() => {
  "use strict";

  const ANALYTICS_URL = "/api/analytics/resumen/";
  const AI_URL = "/api/ia/analisis/";

  let salesChart = null;
  let stockChart = null;
  let selectedDays = 30;
  let selectedFocus = "general";
  let historyItems = [];
  let activeAnalysis = null;

  function destroyCharts() {
    if (salesChart) {
      salesChart.destroy();
      salesChart = null;
    }
    if (stockChart) {
      stockChart.destroy();
      stockChart = null;
    }
  }

  function formatDateTime(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString("es-CL", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function renderSkeleton() {
    return `
      <div class="d-flex flex-wrap justify-content-between align-items-center gap-3 mb-4">
        <div>
          <span class="placeholder col-6 rounded" style="width: 220px; height: 28px;"></span>
          <div class="mt-2"><span class="placeholder col-8 rounded" style="width: 320px; height: 16px;"></span></div>
        </div>
      </div>
      <div class="row g-3 mb-4 placeholder-glow">
        ${[1, 2, 3, 4]
          .map(
            () => `
          <div class="col-12 col-sm-6 col-xl-3">
            <div class="kpi-card">
              <span class="placeholder col-5 mb-3 rounded"></span>
              <span class="placeholder col-8 d-block mb-2 rounded" style="height: 28px;"></span>
              <span class="placeholder col-6 rounded"></span>
            </div>
          </div>`
          )
          .join("")}
      </div>
      <div class="row g-4 placeholder-glow">
        <div class="col-12 col-lg-6"><div class="chart-card"><span class="placeholder w-100 rounded" style="height: 290px;"></span></div></div>
        <div class="col-12 col-lg-6"><div class="chart-card"><span class="placeholder w-100 rounded" style="height: 290px;"></span></div></div>
      </div>
    `;
  }

  function renderLayout(container) {
    container.innerHTML = `
      <div class="d-flex flex-wrap justify-content-between align-items-center gap-3 mb-4">
        <div>
          <h1 class="h4 fw-bold mb-1">Dashboard de Inteligencia Comercial</h1>
          <p class="text-muted small mb-0" id="dash-period-label">Indicadores en tiempo real desde PostgreSQL y diagnóstico asistido por IA</p>
        </div>
        <div class="d-flex flex-wrap align-items-center gap-2">
          <select id="dash-days" class="form-select form-select-sm" style="width: auto;" aria-label="Período de análisis">
            <option value="7" ${selectedDays === 7 ? "selected" : ""}>Últimos 7 días</option>
            <option value="30" ${selectedDays === 30 ? "selected" : ""}>Últimos 30 días</option>
            <option value="90" ${selectedDays === 90 ? "selected" : ""}>Últimos 90 días</option>
            <option value="365" ${selectedDays === 365 ? "selected" : ""}>Último año</option>
          </select>
          <button type="button" id="dash-refresh" class="btn btn-outline-secondary btn-sm">
            <i class="bi bi-arrow-clockwise me-1"></i>Actualizar
          </button>
        </div>
      </div>

      <div id="dash-kpis" class="row g-3 mb-4"></div>

      <div class="row g-4 mb-4">
        <div class="col-12 col-lg-7">
          <div class="chart-card">
            <div class="d-flex justify-content-between align-items-center mb-3">
              <div>
                <h2 class="h6 fw-bold mb-0">Evolución de Ingresos</h2>
                <span class="text-muted small">Montos diarios facturados en el período</span>
              </div>
              <span class="badge text-bg-light border">Chart.js</span>
            </div>
            <div class="chart-container">
              <canvas id="chart-sales"></canvas>
            </div>
            <div id="chart-sales-empty" class="text-center text-muted small py-5 d-none">
              No hay ventas registradas en el período seleccionado.
            </div>
          </div>
        </div>

        <div class="col-12 col-lg-5">
          <div class="chart-card">
            <div class="d-flex justify-content-between align-items-center mb-3">
              <div>
                <h2 class="h6 fw-bold mb-0">Estado de Inventario</h2>
                <span class="text-muted small">Productos con menor stock disponible</span>
              </div>
              <span class="badge text-bg-light border">Alerta &le; 5</span>
            </div>
            <div class="chart-container">
              <canvas id="chart-stock"></canvas>
            </div>
            <div id="chart-stock-empty" class="text-center text-muted small py-5 d-none">
              No hay productos registrados en el catálogo.
            </div>
          </div>
        </div>
      </div>

      <div class="row g-4">
        <div class="col-12 col-lg-8">
          <div class="ai-panel p-4 h-100">
            <div class="d-flex flex-wrap justify-content-between align-items-center gap-3 mb-3">
              <div>
                <span class="ai-badge d-inline-flex align-items-center gap-1 mb-2">
                  <i class="bi bi-stars"></i> GroqCloud IA
                </span>
                <h2 class="h5 fw-bold mb-0">Diagnóstico Inteligente de Negocio</h2>
              </div>
              <div class="d-flex flex-wrap align-items-center gap-2">
                <select id="ai-focus" class="form-select form-select-sm" style="width: auto;" aria-label="Enfoque del análisis">
                  <option value="general" ${selectedFocus === "general" ? "selected" : ""}>Enfoque General</option>
                  <option value="reposicion" ${selectedFocus === "reposicion" ? "selected" : ""}>Reposición de Stock</option>
                  <option value="ventas" ${selectedFocus === "ventas" ? "selected" : ""}>Rendimiento de Ventas</option>
                </select>
                <button type="button" id="ai-generate-btn" class="btn btn-brand btn-sm px-3 fw-semibold">
                  <span id="ai-spinner" class="spinner-border spinner-border-sm me-1 d-none" aria-hidden="true"></span>
                  <i id="ai-icon" class="bi bi-cpu me-1"></i>
                  <span id="ai-btn-label">Generar Análisis IA</span>
                </button>
              </div>
            </div>

            <div id="ai-error-box" class="alert alert-danger d-none py-2 small" role="alert"></div>
            <div id="ai-result-body"></div>
          </div>
        </div>

        <div class="col-12 col-lg-4">
          <div class="card p-4 h-100">
            <div class="d-flex justify-content-between align-items-center mb-3">
              <h2 class="h6 fw-bold mb-0"><i class="bi bi-clock-history me-1 text-primary"></i>Historial de Análisis</h2>
              <span class="badge text-bg-light border" id="ai-history-count">0</span>
            </div>
            <div id="ai-history-list" class="d-flex flex-column gap-2"></div>
          </div>
        </div>
      </div>
    `;
  }

  function renderKpis(data, ctx) {
    const kpis = data.kpis;
    const top = data.top_productos && data.top_productos.length > 0 ? data.top_productos[0] : null;
    const el = document.querySelector("#dash-kpis");
    if (!el) return;

    const periodLabel = document.querySelector("#dash-period-label");
    if (periodLabel) {
      periodLabel.textContent = `Período analizado: ${ctx.formatDate(data.fecha_inicio)} al ${ctx.formatDate(data.fecha_fin)} (${data.periodo_dias} días)`;
    }

    el.innerHTML = `
      <div class="col-12 col-sm-6 col-xl-3">
        <div class="kpi-card">
          <div class="d-flex justify-content-between align-items-start mb-2">
            <span class="text-muted small fw-medium">Ingresos del período</span>
            <span class="kpi-icon" style="background:#eef2ff;color:#4f46e5;"><i class="bi bi-cash-coin"></i></span>
          </div>
          <div class="kpi-value">${ctx.escapeHtml(ctx.formatMoney(kpis.ingresos_periodo))}</div>
          <div class="text-muted small mt-1">${kpis.total_ventas_periodo} venta(s) registradas</div>
        </div>
      </div>

      <div class="col-12 col-sm-6 col-xl-3">
        <div class="kpi-card">
          <div class="d-flex justify-content-between align-items-start mb-2">
            <span class="text-muted small fw-medium">Valor en inventario</span>
            <span class="kpi-icon" style="background:#ecfdf5;color:#059669;"><i class="bi bi-box-seam"></i></span>
          </div>
          <div class="kpi-value">${ctx.escapeHtml(ctx.formatMoney(kpis.valor_inventario))}</div>
          <div class="text-muted small mt-1">${kpis.total_productos} productos activos</div>
        </div>
      </div>

      <div class="col-12 col-sm-6 col-xl-3">
        <div class="kpi-card">
          <div class="d-flex justify-content-between align-items-start mb-2">
            <span class="text-muted small fw-medium">Alertas de stock</span>
            <span class="kpi-icon" style="background:#fef3c7;color:#d97706;"><i class="bi bi-exclamation-triangle"></i></span>
          </div>
          <div class="kpi-value">${kpis.stock_bajo + kpis.sin_stock}</div>
          <div class="text-muted small mt-1">${kpis.sin_stock} sin stock &middot; ${kpis.stock_bajo} stock bajo</div>
        </div>
      </div>

      <div class="col-12 col-sm-6 col-xl-3">
        <div class="kpi-card">
          <div class="d-flex justify-content-between align-items-start mb-2">
            <span class="text-muted small fw-medium">Producto más vendido</span>
            <span class="kpi-icon" style="background:#f3e8ff;color:#7c3aed;"><i class="bi bi-trophy"></i></span>
          </div>
          <div class="kpi-value text-truncate" style="font-size:1.15rem;" title="${top ? ctx.escapeHtml(top.nombre) : "Sin datos"}">
            ${top ? ctx.escapeHtml(top.nombre) : "Sin ventas"}
          </div>
          <div class="text-muted small mt-1">
            ${top ? `${top.unidades} uds &middot; ${ctx.escapeHtml(ctx.formatMoney(top.ingresos))}` : "Registra una venta para ver métricas"}
          </div>
        </div>
      </div>
    `;
  }

  function renderCharts(data, ctx) {
    destroyCharts();

    const salesCanvas = document.querySelector("#chart-sales");
    const salesEmpty = document.querySelector("#chart-sales-empty");
    const salesSeries = data.ventas_por_fecha || [];

    if (!salesSeries.length) {
      salesCanvas.classList.add("d-none");
      salesEmpty.classList.remove("d-none");
    } else {
      salesCanvas.classList.remove("d-none");
      salesEmpty.classList.add("d-none");
      salesChart = new Chart(salesCanvas, {
        type: "line",
        data: {
          labels: salesSeries.map((r) => ctx.formatDate(r.fecha)),
          datasets: [
            {
              label: "Ingresos (CLP)",
              data: salesSeries.map((r) => r.ingresos),
              borderColor: "#4f46e5",
              backgroundColor: "rgba(79, 70, 229, 0.14)",
              borderWidth: 2.5,
              fill: true,
              tension: 0.3,
              pointRadius: 4,
              pointHoverRadius: 6,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (item) => {
                  const row = salesSeries[item.dataIndex];
                  return ` ${ctx.formatMoney(row.ingresos)} (${row.cantidad_ventas} venta/s)`;
                },
              },
            },
          },
          scales: {
            y: {
              beginAtZero: true,
              ticks: {
                callback: (val) => ctx.formatMoney(val),
              },
            },
          },
        },
      });
    }

    const stockCanvas = document.querySelector("#chart-stock");
    const stockEmpty = document.querySelector("#chart-stock-empty");
    const stockSeries = (data.stock_por_producto || []).slice(0, 10);

    if (!stockSeries.length) {
      stockCanvas.classList.add("d-none");
      stockEmpty.classList.remove("d-none");
    } else {
      stockCanvas.classList.remove("d-none");
      stockEmpty.classList.add("d-none");
      const colors = stockSeries.map((p) =>
        p.estado === "sin_stock"
          ? "#ef4444"
          : p.estado === "bajo"
          ? "#f59e0b"
          : "#10b981"
      );

      stockChart = new Chart(stockCanvas, {
        type: "bar",
        data: {
          labels: stockSeries.map((p) =>
            p.nombre.length > 18 ? `${p.nombre.slice(0, 18)}…` : p.nombre
          ),
          datasets: [
            {
              label: "Unidades en stock",
              data: stockSeries.map((p) => p.stock),
              backgroundColor: colors,
              borderRadius: 6,
            },
          ],
        },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                title: (items) => stockSeries[items[0].dataIndex].nombre,
                label: (item) => {
                  const p = stockSeries[item.dataIndex];
                  return ` Stock: ${p.stock} uds · Precio: ${ctx.formatMoney(p.precio)}`;
                },
              },
            },
          },
          scales: {
            x: { beginAtZero: true },
          },
        },
      });
    }
  }

  function renderAnalysisDetail(record, ctx) {
    const body = document.querySelector("#ai-result-body");
    if (!body) return;

    if (!record) {
      body.innerHTML = `
        <div class="text-center py-4 px-3 border rounded-4 bg-white">
          <i class="bi bi-robot fs-1 text-primary opacity-75"></i>
          <p class="fw-semibold mt-2 mb-1">Aún no has generado un diagnóstico</p>
          <p class="text-muted small mb-0">
            Presiona <strong>Generar Análisis IA</strong> para que GroqCloud analice tus ventas e inventario reales y entregue recomendaciones priorizadas.
          </p>
        </div>
      `;
      return;
    }

    if (record.estado !== "OK") {
      body.innerHTML = `
        <div class="alert alert-warning mb-0">
          <strong>Análisis #${record.id} registrado con error:</strong> ${ctx.escapeHtml(record.mensaje_error || "Error no especificado.")}
        </div>
      `;
      return;
    }

    const res = record.resultado || {};
    const risk = res.nivel_riesgo || "MEDIO";
    const acciones = Array.isArray(res.acciones_prioritarias) ? res.acciones_prioritarias : [];
    const criticos = Array.isArray(res.productos_criticos) ? res.productos_criticos : [];

    body.innerHTML = `
      <div class="bg-white border rounded-4 p-3 p-md-4">
        <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
          <div class="d-flex align-items-center gap-2">
            <span class="badge rounded-pill risk-badge-${ctx.escapeHtml(risk)} px-3 py-2">
              Riesgo ${ctx.escapeHtml(risk)}
            </span>
            <span class="badge text-bg-light border text-capitalize">${ctx.escapeHtml(record.enfoque)}</span>
          </div>
          <span class="text-muted small">
            <i class="bi bi-calendar3 me-1"></i>${ctx.escapeHtml(formatDateTime(record.fecha_creacion))}
            ${record.modelo ? ` &middot; ${ctx.escapeHtml(record.modelo)}` : ""}
          </span>
        </div>

        <p class="mb-3" style="line-height: 1.6;">${ctx.escapeHtml(res.resumen_ejecutivo || "")}</p>

        <div class="row g-3">
          <div class="col-12 col-md-7">
            <h3 class="h6 fw-bold mb-2"><i class="bi bi-check2-circle text-success me-1"></i>Acciones prioritarias</h3>
            <ul class="list-group list-group-flush small">
              ${
                acciones.length
                  ? acciones
                      .map(
                        (a) =>
                          `<li class="list-group-item px-0 py-1 border-0"><i class="bi bi-arrow-right-short text-primary"></i>${ctx.escapeHtml(a)}</li>`
                      )
                      .join("")
                  : '<li class="list-group-item px-0 text-muted border-0">Sin acciones sugeridas.</li>'
              }
            </ul>
          </div>
          <div class="col-12 col-md-5">
            <h3 class="h6 fw-bold mb-2"><i class="bi bi-exclamation-octagon text-danger me-1"></i>Productos críticos</h3>
            <div class="d-flex flex-wrap gap-2">
              ${
                criticos.length
                  ? criticos
                      .map(
                        (p) =>
                          `<span class="badge text-bg-danger bg-opacity-10 text-danger border border-danger-subtle px-2 py-1">${ctx.escapeHtml(p)}</span>`
                      )
                      .join("")
                  : '<span class="text-muted small">Sin productos críticos detectados.</span>'
              }
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function renderHistory(ctx) {
    const list = document.querySelector("#ai-history-list");
    const count = document.querySelector("#ai-history-count");
    if (!list || !count) return;

    count.textContent = String(historyItems.length);
    if (!historyItems.length) {
      list.innerHTML = `<p class="text-muted small mb-0">Sin registros guardados en la base de datos.</p>`;
      return;
    }

    list.innerHTML = historyItems
      .map((item) => {
        const isActive = activeAnalysis && activeAnalysis.id === item.id;
        const ok = item.estado === "OK";
        return `
          <button type="button" data-ai-id="${item.id}" class="btn text-start p-2 rounded-3 border ${
            isActive ? "border-primary bg-primary bg-opacity-10" : "bg-light"
          }">
            <div class="d-flex justify-content-between align-items-center mb-1">
              <span class="fw-semibold small text-capitalize">#${item.id} &middot; ${ctx.escapeHtml(item.enfoque)}</span>
              <span class="badge ${ok ? "text-bg-success" : "text-bg-danger"}" style="font-size: 0.7rem;">${ctx.escapeHtml(item.estado)}</span>
            </div>
            <div class="text-muted" style="font-size: 0.75rem;">
              ${ctx.escapeHtml(formatDateTime(item.fecha_creacion))}
            </div>
          </button>
        `;
      })
      .join("");
  }

  async function loadAll(container, ctx) {
    container.innerHTML = renderSkeleton();
    try {
      const [analytics, aiHistory] = await Promise.all([
        ctx.apiFetch(`${ANALYTICS_URL}?dias=${selectedDays}`),
        ctx.apiFetch(AI_URL),
      ]);

      renderLayout(container);
      renderKpis(analytics, ctx);
      renderCharts(analytics, ctx);

      historyItems = Array.isArray(aiHistory.results) ? aiHistory.results : [];
      activeAnalysis = historyItems.find((item) => item.estado === "OK") || historyItems[0] || null;
      renderAnalysisDetail(activeAnalysis, ctx);
      renderHistory(ctx);
      bindEvents(container, ctx);
    } catch (error) {
      if (error.status === 401) return;
      container.innerHTML = `
        <div class="alert alert-danger d-flex justify-content-between align-items-center">
          <span>No se pudo cargar el dashboard: ${ctx.escapeHtml(error.message)}</span>
          <button type="button" id="dash-retry" class="btn btn-sm btn-outline-danger">Reintentar</button>
        </div>
      `;
      const retry = document.querySelector("#dash-retry");
      if (retry) retry.addEventListener("click", () => loadAll(container, ctx));
    }
  }

  function bindEvents(container, ctx) {
    const daysSelect = document.querySelector("#dash-days");
    const refreshBtn = document.querySelector("#dash-refresh");
    const focusSelect = document.querySelector("#ai-focus");
    const aiBtn = document.querySelector("#ai-generate-btn");
    const historyList = document.querySelector("#ai-history-list");

    if (daysSelect) {
      daysSelect.addEventListener("change", () => {
        selectedDays = Number(daysSelect.value) || 30;
        loadAll(container, ctx);
      });
    }

    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => loadAll(container, ctx));
    }

    if (focusSelect) {
      focusSelect.addEventListener("change", () => {
        selectedFocus = focusSelect.value;
      });
    }

    if (historyList) {
      historyList.addEventListener("click", (event) => {
        const btn = event.target.closest("[data-ai-id]");
        if (!btn) return;
        const id = Number(btn.dataset.aiId);
        activeAnalysis = historyItems.find((x) => x.id === id) || null;
        renderAnalysisDetail(activeAnalysis, ctx);
        renderHistory(ctx);
      });
    }

    if (aiBtn) {
      aiBtn.addEventListener("click", async () => {
        const spinner = document.querySelector("#ai-spinner");
        const icon = document.querySelector("#ai-icon");
        const label = document.querySelector("#ai-btn-label");
        const errorBox = document.querySelector("#ai-error-box");

        aiBtn.disabled = true;
        spinner.classList.remove("d-none");
        icon.classList.add("d-none");
        label.textContent = "Analizando con GroqCloud...";
        errorBox.classList.add("d-none");

        try {
          const created = await ctx.apiFetch(AI_URL, {
            method: "POST",
            body: { enfoque: selectedFocus, dias: selectedDays },
          });
          historyItems = [created, ...historyItems].slice(0, 10);
          activeAnalysis = created;
          renderAnalysisDetail(activeAnalysis, ctx);
          renderHistory(ctx);

          if (created && created.estado === "OK") {
            ctx.showAlert("Diagnóstico IA generado y guardado en base de datos.", "success");
          } else {
            const msg = (created && created.mensaje_error) || "El análisis quedó registrado con observaciones.";
            errorBox.textContent = msg;
            errorBox.classList.remove("d-none");
            ctx.showAlert(msg, "warning");
          }
        } catch (error) {
          if (error.status !== 401) {
            errorBox.textContent = error.message || "Error al consultar el servicio de IA.";
            errorBox.classList.remove("d-none");
            ctx.showAlert(error.message || "Error al generar análisis IA.");
          }
        } finally {
          aiBtn.disabled = false;
          spinner.classList.add("d-none");
          icon.classList.remove("d-none");
          label.textContent = "Generar Análisis IA";
        }
      });
    }
  }

  window.ES04Dashboard = {
    render: loadAll,
    destroy: destroyCharts,
  };
})();
(() => {
  "use strict";

  const API = {
    token: "/api/token/",
    refresh: "/api/token/refresh/",
    products: "/api/productos/",
    sales: "/api/ventas/",
  };
  const STORAGE_KEY = "sales_spa_session";
  const PAGE_SIZE = 10;
  const ROUTES = ["products", "sales", "new-sale"];
  const currency = new Intl.NumberFormat("es-CL", {
    style: "currency",
    currency: "CLP",
    maximumFractionDigits: 0,
  });

  const state = {
    access: null,
    refresh: null,
    username: "",
    products: null,
    salesById: new Map(),
  };
  const productsView = { page: 1, search: "" };
  const salesView = { page: 1, dateFrom: "", dateTo: "" };
  let currentRoute = "products";
  let refreshPromise = null;

  const $ = (selector) => document.querySelector(selector);

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatMoney(value) {
    return currency.format(Number(value));
  }

  function formatDate(iso) {
    const [year, month, day] = String(iso).split("-");
    return year && month && day ? `${day}-${month}-${year}` : iso;
  }

  function todayLocal() {
    const now = new Date();
    const offsetMs = now.getTimezoneOffset() * 60000;
    return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10);
  }

  function loadSession() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const data = JSON.parse(raw);
      state.access = data.access || null;
      state.refresh = data.refresh || null;
      state.username = data.username || "";
    } catch (error) {
      state.access = null;
      state.refresh = null;
    }
  }

  function saveSession() {
    try {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          access: state.access,
          refresh: state.refresh,
          username: state.username,
        })
      );
    } catch (error) {
      /* storage unavailable: session lives in memory only */
    }
  }

  function clearSession() {
    state.access = null;
    state.refresh = null;
    state.username = "";
    state.products = null;
    state.salesById.clear();
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch (error) {
      /* nothing to clear */
    }
  }

  function showAlert(message, type = "danger", timeoutMs = 6000) {
    const wrapper = document.createElement("div");
    wrapper.className = `alert alert-${type} alert-dismissible fade show shadow-sm`;
    wrapper.setAttribute("role", "alert");

    const text = document.createElement("span");
    text.textContent = message;

    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "btn-close";
    closeButton.setAttribute("aria-label", "Cerrar");
    closeButton.addEventListener("click", () => wrapper.remove());

    wrapper.append(text, closeButton);
    $("#alert-container").appendChild(wrapper);
    if (timeoutMs) setTimeout(() => wrapper.remove(), timeoutMs);
  }

  const PLAIN_ERROR_KEYS = new Set(["detail", "non_field_errors", "detalles"]);

  function flattenErrors(data) {
    if (data === null || data === undefined) return [];
    if (typeof data === "string") return [data];
    if (Array.isArray(data)) return data.flatMap(flattenErrors);
    if (typeof data === "object") {
      return Object.entries(data).flatMap(([key, value]) => {
        const messages = flattenErrors(value);
        return PLAIN_ERROR_KEYS.has(key) ? messages : messages.map((m) => `${key}: ${m}`);
      });
    }
    return [String(data)];
  }

  class ApiError extends Error {
    constructor(status, data) {
      const messages = flattenErrors(data);
      super(messages.length ? messages.join(" ") : `Error inesperado (HTTP ${status}).`);
      this.status = status;
      this.data = data;
    }
  }

  async function safeJson(response) {
    try {
      return await response.json();
    } catch (error) {
      return null;
    }
  }

  async function refreshAccessToken() {
    if (!state.refresh) throw new Error("Missing refresh token");
    if (!refreshPromise) {
      refreshPromise = fetch(API.refresh, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh: state.refresh }),
      })
        .then(async (response) => {
          const data = await safeJson(response);
          if (!response.ok) throw new ApiError(response.status, data);
          state.access = data.access;
          if (data.refresh) state.refresh = data.refresh;
          saveSession();
        })
        .finally(() => {
          refreshPromise = null;
        });
    }
    return refreshPromise;
  }

  async function apiFetch(url, options = {}, canRetry = true) {
    const headers = { Accept: "application/json", ...(options.headers || {}) };
    if (state.access) headers.Authorization = `Bearer ${state.access}`;
    const hasBody = options.body !== undefined;
    if (hasBody) headers["Content-Type"] = "application/json";

    const response = await fetch(url, {
      ...options,
      headers,
      body: hasBody ? JSON.stringify(options.body) : undefined,
    });

    if (response.status === 401 && canRetry && state.refresh) {
      try {
        await refreshAccessToken();
      } catch (error) {
        logout("Tu sesión expiró. Inicia sesión nuevamente.", "warning");
        throw new ApiError(401, null);
      }
      return apiFetch(url, options, false);
    }

    const data = response.status === 204 ? null : await safeJson(response);
    if (!response.ok) {
      if (response.status === 401) {
        logout("Tu sesión no es válida. Inicia sesión nuevamente.", "warning");
      }
      throw new ApiError(response.status, data);
    }
    return data;
  }

  async function fetchAllProducts() {
    const all = [];
    let url = `${API.products}?ordering=nombre`;
    while (url) {
      const data = await apiFetch(url);
      all.push(...data.results);
      if (data.next) {
        const next = new URL(data.next);
        url = next.pathname + next.search;
      } else {
        url = null;
      }
    }
    return all;
  }

  function skeletonRows(rows, cols) {
    const cell = '<td><span class="placeholder col-8"></span></td>';
    return Array.from(
      { length: rows },
      () => `<tr class="placeholder-glow">${cell.repeat(cols)}</tr>`
    ).join("");
  }

  function emptyRow(cols, message) {
    return `<tr><td colspan="${cols}" class="text-center text-muted py-4">${escapeHtml(message)}</td></tr>`;
  }

  function paginationHtml(page, count) {
    const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
    return `
      <div class="d-flex justify-content-between align-items-center mt-3">
        <small class="text-muted">${count} registro(s) · página ${page} de ${totalPages}</small>
        <div class="btn-group">
          <button type="button" class="btn btn-outline-secondary btn-sm" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>Anterior</button>
          <button type="button" class="btn btn-outline-secondary btn-sm" data-page="${page + 1}" ${page >= totalPages ? "disabled" : ""}>Siguiente</button>
        </div>
      </div>`;
  }

  function showLogin() {
    $("#app-section").classList.add("d-none");
    $("#login-section").classList.remove("d-none");
    $("#login-form").reset();
    $("#login-username").focus();
  }

  function showApp() {
    $("#login-section").classList.add("d-none");
    $("#app-section").classList.remove("d-none");
    $("#nav-username").textContent = state.username;
    route();
  }

  function logout(message, type = "info") {
    clearSession();
    showLogin();
    if (message) showAlert(message, type);
  }

  async function login(username, password) {
    const response = await fetch(API.token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await safeJson(response);
    if (!response.ok) {
      if (response.status === 401) {
        throw new Error("Usuario o contraseña incorrectos.");
      }
      throw new ApiError(response.status, data);
    }
    state.access = data.access;
    state.refresh = data.refresh;
    state.username = username;
    saveSession();
  }

  function route() {
    if (!state.access) return;
    const requested = location.hash.replace("#", "");
    currentRoute = ROUTES.includes(requested) ? requested : "products";

    document.querySelectorAll("[data-route]").forEach((link) => {
      link.classList.toggle("active", link.dataset.route === currentRoute);
    });

    if (currentRoute === "products") renderProducts();
    else if (currentRoute === "sales") renderSales();
    else renderNewSale();
  }

  /* ---------- Products ---------- */

  function renderProducts() {
    $("#view").innerHTML = `
      <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
        <h2 class="h4 mb-0">Catálogo de productos</h2>
        <form id="product-search-form" class="d-flex gap-2" role="search">
          <input type="search" id="product-search" class="form-control" placeholder="Buscar por código o nombre" value="${escapeHtml(productsView.search)}">
          <button type="submit" class="btn btn-primary">Buscar</button>
        </form>
      </div>
      <div class="card">
        <div class="table-responsive">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr><th>Código</th><th>Nombre</th><th class="text-end">Precio</th><th class="text-end">Stock</th></tr>
            </thead>
            <tbody id="products-body">${skeletonRows(5, 4)}</tbody>
          </table>
        </div>
      </div>
      <div id="products-pagination"></div>`;

    $("#product-search-form").addEventListener("submit", (event) => {
      event.preventDefault();
      productsView.search = $("#product-search").value.trim();
      productsView.page = 1;
      loadProducts();
    });

    loadProducts();
  }

  async function loadProducts() {
    const body = $("#products-body");
    if (!body) return;
    body.innerHTML = skeletonRows(5, 4);

    const params = new URLSearchParams({ page: productsView.page });
    if (productsView.search) params.set("search", productsView.search);

    try {
      const data = await apiFetch(`${API.products}?${params}`);
      if (!$("#products-body")) return;

      $("#products-body").innerHTML = data.results.length
        ? data.results
            .map(
              (product) => `
              <tr>
                <td>${escapeHtml(product.codigo)}</td>
                <td>${escapeHtml(product.nombre)}</td>
                <td class="text-end">${formatMoney(product.precio)}</td>
                <td class="text-end">
                  <span class="badge text-bg-${product.is_low_stock ? "danger" : "success"}">${product.stock}</span>
                  ${product.stock === 0 ? '<small class="text-danger ms-1">Sin stock</small>' : ""}
                </td>
              </tr>`
            )
            .join("")
        : emptyRow(4, "No se encontraron productos.");
      $("#products-pagination").innerHTML = paginationHtml(productsView.page, data.count);
    } catch (error) {
      if (error.status === 401) return;
      if (error.status === 404 && productsView.page > 1) {
        productsView.page = 1;
        return loadProducts();
      }
      if ($("#products-body")) $("#products-body").innerHTML = emptyRow(4, "No se pudo cargar el catálogo.");
      showAlert(error.message);
    }
  }

  /* ---------- Sales list ---------- */

  function renderSales() {
    $("#view").innerHTML = `
      <div class="d-flex flex-wrap justify-content-between align-items-end gap-2 mb-3">
        <h2 class="h4 mb-0">Ventas</h2>
        <form id="sales-filter-form" class="d-flex flex-wrap align-items-end gap-2">
          <div>
            <label for="filter-from" class="form-label mb-0 small">Desde</label>
            <input type="date" id="filter-from" class="form-control form-control-sm" value="${escapeHtml(salesView.dateFrom)}">
          </div>
          <div>
            <label for="filter-to" class="form-label mb-0 small">Hasta</label>
            <input type="date" id="filter-to" class="form-control form-control-sm" value="${escapeHtml(salesView.dateTo)}">
          </div>
          <button type="submit" class="btn btn-primary btn-sm">Filtrar</button>
          <button type="button" id="filter-clear" class="btn btn-outline-secondary btn-sm">Limpiar</button>
        </form>
      </div>
      <div class="card">
        <div class="table-responsive">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr><th>Folio</th><th>Cliente</th><th>Fecha</th><th class="text-end">Ítems</th><th class="text-end">Total</th><th></th></tr>
            </thead>
            <tbody id="sales-body">${skeletonRows(5, 6)}</tbody>
          </table>
        </div>
      </div>
      <div id="sales-pagination"></div>`;

    $("#sales-filter-form").addEventListener("submit", (event) => {
      event.preventDefault();
      const dateFrom = $("#filter-from").value;
      const dateTo = $("#filter-to").value;
      if (dateFrom && dateTo && dateFrom > dateTo) {
        showAlert("La fecha 'Desde' no puede ser posterior a 'Hasta'.", "warning");
        return;
      }
      salesView.dateFrom = dateFrom;
      salesView.dateTo = dateTo;
      salesView.page = 1;
      loadSales();
    });

    $("#filter-clear").addEventListener("click", () => {
      salesView.dateFrom = "";
      salesView.dateTo = "";
      salesView.page = 1;
      $("#filter-from").value = "";
      $("#filter-to").value = "";
      loadSales();
    });

    loadSales();
  }

  async function loadSales() {
    const body = $("#sales-body");
    if (!body) return;
    body.innerHTML = skeletonRows(5, 6);

    const params = new URLSearchParams({ page: salesView.page });
    if (salesView.dateFrom) params.set("fecha_desde", salesView.dateFrom);
    if (salesView.dateTo) params.set("fecha_hasta", salesView.dateTo);

    try {
      const data = await apiFetch(`${API.sales}?${params}`);
      if (!$("#sales-body")) return;

      state.salesById.clear();
      data.results.forEach((sale) => state.salesById.set(sale.id, sale));

      $("#sales-body").innerHTML = data.results.length
        ? data.results
            .map(
              (sale) => `
              <tr>
                <td>${escapeHtml(sale.folio)}</td>
                <td>${escapeHtml(sale.cliente)}</td>
                <td>${formatDate(sale.fecha)}</td>
                <td class="text-end">${sale.detalles.length}</td>
                <td class="text-end">${formatMoney(sale.total)}</td>
                <td class="text-end"><button type="button" class="btn btn-outline-primary btn-sm" data-sale-id="${sale.id}">Ver detalle</button></td>
              </tr>`
            )
            .join("")
        : emptyRow(6, "No hay ventas para mostrar.");
      $("#sales-pagination").innerHTML = paginationHtml(salesView.page, data.count);
    } catch (error) {
      if (error.status === 401) return;
      if (error.status === 404 && salesView.page > 1) {
        salesView.page = 1;
        return loadSales();
      }
      if ($("#sales-body")) $("#sales-body").innerHTML = emptyRow(6, "No se pudieron cargar las ventas.");
      showAlert(error.message);
    }
  }

  function openSaleModal(saleId) {
    const sale = state.salesById.get(saleId);
    if (!sale) return;

    $("#sale-modal-title").textContent = `Venta ${sale.folio}`;
    const rows = sale.detalles
      .map(
        (item) => `
        <tr>
          <td>${escapeHtml(item.producto_nombre)}</td>
          <td class="text-end">${item.cantidad}</td>
          <td class="text-end">${formatMoney(item.precio_unitario)}</td>
          <td class="text-end">${formatMoney(item.subtotal)}</td>
        </tr>`
      )
      .join("");

    $("#sale-modal-body").innerHTML = `
      <p class="mb-3">
        <strong>Cliente:</strong> ${escapeHtml(sale.cliente)}<br>
        <strong>Fecha:</strong> ${formatDate(sale.fecha)}
      </p>
      <div class="table-responsive">
        <table class="table table-sm align-middle mb-0">
          <thead>
            <tr><th>Producto</th><th class="text-end">Cant.</th><th class="text-end">Precio</th><th class="text-end">Subtotal</th></tr>
          </thead>
          <tbody>${rows}</tbody>
          <tfoot>
            <tr><th colspan="3" class="text-end">Total</th><th class="text-end">${formatMoney(sale.total)}</th></tr>
          </tfoot>
        </table>
      </div>`;

    bootstrap.Modal.getOrCreateInstance($("#sale-modal")).show();
  }

  /* ---------- New sale ---------- */

  function saleLineHtml(products) {
    const options = products
      .map(
        (product) => `
        <option value="${product.id}" data-price="${escapeHtml(product.precio)}" ${product.stock <= 0 ? "disabled" : ""}>
          ${escapeHtml(product.nombre)} · ${formatMoney(product.precio)} (stock: ${product.stock})
        </option>`
      )
      .join("");

    return `
      <div class="row g-2 align-items-center sale-line">
        <div class="col-sm-8">
          <select class="form-select line-product" aria-label="Producto" required>
            <option value="">Selecciona un producto</option>
            ${options}
          </select>
        </div>
        <div class="col-8 col-sm-2">
          <input type="number" class="form-control line-quantity" aria-label="Cantidad" min="1" step="1" value="1" required>
        </div>
        <div class="col-4 col-sm-2 text-end">
          <button type="button" class="btn btn-outline-danger btn-sm remove-line">Quitar</button>
        </div>
      </div>`;
  }

  function recalculateSaleTotal() {
    let total = 0;
    document.querySelectorAll(".sale-line").forEach((row) => {
      const select = row.querySelector(".line-product");
      const quantity = Number(row.querySelector(".line-quantity").value);
      const option = select.options[select.selectedIndex];
      const price = option && option.dataset.price ? Number(option.dataset.price) : 0;
      if (Number.isFinite(quantity) && quantity > 0) total += price * quantity;
    });
    const totalElement = $("#sale-total");
    if (totalElement) totalElement.textContent = formatMoney(total);
  }

  function updateRemoveButtons() {
    const rows = document.querySelectorAll(".sale-line");
    rows.forEach((row) => {
      row.querySelector(".remove-line").disabled = rows.length === 1;
    });
  }

  function collectSaleLines() {
    const lines = [];
    const requested = new Map();

    document.querySelectorAll(".sale-line").forEach((row) => {
      const select = row.querySelector(".line-product");
      const quantity = Number(row.querySelector(".line-quantity").value);
      if (!select.value) throw new Error("Selecciona un producto en cada línea.");
      if (!Number.isInteger(quantity) || quantity < 1) {
        throw new Error("La cantidad debe ser un número entero mayor a 0.");
      }
      const productId = Number(select.value);
      lines.push({ producto: productId, cantidad: quantity });
      requested.set(productId, (requested.get(productId) || 0) + quantity);
    });

    if (lines.length === 0) throw new Error("Agrega al menos un producto.");

    requested.forEach((quantity, productId) => {
      const product = state.products.find((item) => item.id === productId);
      if (product && quantity > product.stock) {
        throw new Error(`Stock insuficiente para "${product.nombre}" (disponible: ${product.stock}).`);
      }
    });

    return lines;
  }

  async function renderNewSale() {
    $("#view").innerHTML = `
      <h2 class="h4 mb-3">Registrar venta</h2>
      <div id="sale-form-host">
        <div class="card card-body placeholder-glow">
          <span class="placeholder col-12 mb-3"></span>
          <span class="placeholder col-8 mb-3"></span>
          <span class="placeholder col-10 mb-3"></span>
          <span class="placeholder col-6"></span>
        </div>
      </div>`;

    try {
      state.products = await fetchAllProducts();
    } catch (error) {
      if (error.status === 401) return;
      if ($("#sale-form-host")) {
        $("#sale-form-host").innerHTML = '<div class="alert alert-danger">No se pudo cargar el catálogo de productos.</div>';
      }
      showAlert(error.message);
      return;
    }

    const host = $("#sale-form-host");
    if (!host || currentRoute !== "new-sale") return;

    host.innerHTML = `
      <form id="sale-form" class="card card-body" novalidate>
        <div class="row g-3 mb-3">
          <div class="col-md-8">
            <label for="sale-client" class="form-label">Cliente</label>
            <input type="text" id="sale-client" class="form-control" maxlength="120" required>
          </div>
          <div class="col-md-4">
            <label for="sale-date" class="form-label">Fecha</label>
            <input type="date" id="sale-date" class="form-control" value="${todayLocal()}" required>
          </div>
        </div>
        <h3 class="h6">Productos</h3>
        <div id="sale-lines" class="d-grid gap-2 mb-2">${saleLineHtml(state.products)}</div>
        <button type="button" id="add-line" class="btn btn-outline-primary btn-sm align-self-start mb-3">+ Agregar producto</button>
        <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 border-top pt-3">
          <div class="fs-5">Total estimado: <strong id="sale-total">${formatMoney(0)}</strong></div>
          <button type="submit" id="sale-submit" class="btn btn-success">
            <span id="sale-spinner" class="spinner-border spinner-border-sm d-none" aria-hidden="true"></span>
            Registrar venta
          </button>
        </div>
      </form>`;

    updateRemoveButtons();

    const form = $("#sale-form");

    $("#add-line").addEventListener("click", () => {
      $("#sale-lines").insertAdjacentHTML("beforeend", saleLineHtml(state.products));
      updateRemoveButtons();
      recalculateSaleTotal();
    });

    form.addEventListener("click", (event) => {
      const removeButton = event.target.closest(".remove-line");
      if (!removeButton) return;
      removeButton.closest(".sale-line").remove();
      updateRemoveButtons();
      recalculateSaleTotal();
    });

    form.addEventListener("input", recalculateSaleTotal);
    form.addEventListener("change", recalculateSaleTotal);

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submitButton = $("#sale-submit");
      const spinner = $("#sale-spinner");

      try {
        const client = $("#sale-client").value.trim();
        const date = $("#sale-date").value;
        if (!client) throw new Error("El cliente es obligatorio.");
        if (!date) throw new Error("La fecha es obligatoria.");
        const items = collectSaleLines();

        submitButton.disabled = true;
        spinner.classList.remove("d-none");

        const sale = await apiFetch(API.sales, {
          method: "POST",
          body: { cliente: client, fecha: date, detalles: items },
        });

        showAlert(`Venta ${sale.folio} registrada por ${formatMoney(sale.total)}.`, "success");
        state.products = null;
        salesView.page = 1;
        location.hash = "#sales";
      } catch (error) {
        if (error.status !== 401) showAlert(error.message);
        submitButton.disabled = false;
        spinner.classList.add("d-none");
      }
    });
  }

  /* ---------- Init ---------- */

  function init() {
    loadSession();

    $("#login-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const username = $("#login-username").value.trim();
      const password = $("#login-password").value;
      if (!username || !password) {
        showAlert("Ingresa usuario y contraseña.", "warning");
        return;
      }

      const button = $("#login-submit");
      button.disabled = true;
      $("#login-spinner").classList.remove("d-none");
      $("#login-label").textContent = "Ingresando...";

      try {
        await login(username, password);
        showApp();
      } catch (error) {
        showAlert(error.message);
      } finally {
        button.disabled = false;
        $("#login-spinner").classList.add("d-none");
        $("#login-label").textContent = "Ingresar";
      }
    });

    $("#logout-button").addEventListener("click", () => logout("Sesión cerrada.", "info"));

    $("#view").addEventListener("click", (event) => {
      const pageButton = event.target.closest("[data-page]");
      if (pageButton) {
        const page = Number(pageButton.dataset.page);
        if (currentRoute === "products") {
          productsView.page = page;
          loadProducts();
        } else if (currentRoute === "sales") {
          salesView.page = page;
          loadSales();
        }
        return;
      }
      const detailButton = event.target.closest("[data-sale-id]");
      if (detailButton) openSaleModal(Number(detailButton.dataset.saleId));
    });

    window.addEventListener("hashchange", route);

    if (state.access) showApp();
    else showLogin();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
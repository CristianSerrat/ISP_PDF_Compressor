// Lógica del Panel de Administración con Autenticación por Clave Maestra

document.addEventListener("DOMContentLoaded", () => {
  let currentDays = 30;

  // Elementos de autenticación
  const loginSection = document.getElementById("loginSection");
  const dashboardSection = document.getElementById("dashboardSection");
  const loginForm = document.getElementById("loginForm");
  const adminPasswordInput = document.getElementById("adminPasswordInput");
  const loginAlert = document.getElementById("loginAlert");
  const btnLoginSubmit = document.getElementById("btnLoginSubmit");
  const btnLogout = document.getElementById("btnLogout");

  // Elementos del dashboard
  const valTotalOps = document.getElementById("valTotalOps");
  const valOkOps = document.getElementById("valOkOps");
  const valErrorRate = document.getElementById("valErrorRate");
  const valErrorOps = document.getElementById("valErrorOps");
  const valSavedPct = document.getElementById("valSavedPct");
  const valSavedBytes = document.getElementById("valSavedBytes");
  const valOriginalBytes = document.getElementById("valOriginalBytes");
  const valFinalBytes = document.getElementById("valFinalBytes");
  const valTotalPages = document.getElementById("valTotalPages");
  const valAvgDuration = document.getElementById("valAvgDuration");

  const chartDays = document.getElementById("chartDays");
  const chartHours = document.getElementById("chartHours");
  const chartTypes = document.getElementById("chartTypes");
  const chartPresets = document.getElementById("chartPresets");
  const tableClients = document.getElementById("tableClients");
  const tableErrors = document.getElementById("tableErrors");

  const periodButtons = document.querySelectorAll(".period-btn");
  const btnExportCsv = document.getElementById("btnExportCsv");
  const exportStart = document.getElementById("exportStart");
  const exportEnd = document.getElementById("exportEnd");

  function formatBytes(bytes) {
    if (!bytes || bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  }

  function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // Comprobar autenticación cargando estadísticas
  async function loadStats(days) {
    currentDays = days;
    try {
      const response = await fetch(`/admin/api/stats?days=${days}`);

      if (response.status === 401 || response.status === 403) {
        // No autenticado: mostrar pantalla de login
        dashboardSection.style.display = "none";
        btnLogout.style.display = "none";
        loginSection.style.display = "block";
        adminPasswordInput.value = "";
        adminPasswordInput.focus();
        return;
      }

      if (!response.ok) {
        throw new Error("No se pudieron cargar las estadísticas.");
      }

      // Autenticado: mostrar dashboard
      loginSection.style.display = "none";
      dashboardSection.style.display = "block";
      btnLogout.style.display = "inline-flex";

      const data = await response.json();
      renderDashboard(data);
    } catch (err) {
      console.error(err);
      chartDays.innerHTML = `<div style="margin: auto; color: var(--danger); font-size: 0.85rem;">Error al conectar con el servidor.</div>`;
    }
  }

  // Manejo del formulario de login
  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    loginAlert.innerHTML = "";
    btnLoginSubmit.disabled = true;
    btnLoginSubmit.textContent = "Verificando...";

    const formData = new FormData();
    formData.append("password", adminPasswordInput.value);

    try {
      const resp = await fetch("/admin/api/login", {
        method: "POST",
        body: formData,
      });

      const resData = await resp.json().catch(() => ({}));

      if (!resp.ok) {
        throw new Error(resData.detail || "Error de autenticación.");
      }

      // Login exitoso: cargar estadísticas
      await loadStats(currentDays);
    } catch (err) {
      loginAlert.innerHTML = `
        <div class="alert alert-danger" style="padding: 0.5rem; font-size: 0.85rem; margin-top: 0.5rem;">
          ${escapeHtml(err.message)}
        </div>
      `;
      adminPasswordInput.focus();
    } finally {
      btnLoginSubmit.disabled = false;
      btnLoginSubmit.textContent = "🔓 Entrar al Panel";
    }
  });

  // Manejo de Logout
  btnLogout.addEventListener("click", async () => {
    try {
      await fetch("/admin/api/logout", { method: "POST" });
    } catch (err) {
      console.error(err);
    }
    dashboardSection.style.display = "none";
    btnLogout.style.display = "none";
    loginSection.style.display = "block";
    loginAlert.innerHTML = "";
    adminPasswordInput.value = "";
    adminPasswordInput.focus();
  });

  function renderDashboard(data) {
    // 1. Tarjetas de métricas
    valTotalOps.textContent = data.total_operations.toLocaleString();
    valOkOps.textContent = `${data.successful_operations} exitosas (${data.total_operations > 0 ? ((data.successful_operations / data.total_operations) * 100).toFixed(1) : 0}%)`;

    valErrorRate.textContent = `${data.error_rate_pct}%`;
    valErrorOps.textContent = `${data.error_operations} fallidas`;

    valSavedPct.textContent = `-${data.saved_pct}%`;
    valSavedBytes.textContent = `${formatBytes(data.saved_bytes)} ahorrados`;

    valOriginalBytes.textContent = formatBytes(data.total_original_bytes);
    valFinalBytes.textContent = `Final: ${formatBytes(data.total_final_bytes)}`;

    valTotalPages.textContent = (data.total_pages || 0).toLocaleString();
    valAvgDuration.textContent = `${(data.avg_duration_ms / 1000).toFixed(2)}s`;

    // 2. Gráficos
    renderDaysChart(data.by_day || []);
    renderHourlyChart(data.hourly || []);
    renderTypesBars(data.by_type || [], data.total_operations);
    renderPresetsBars(data.by_preset || [], data.total_operations);
    renderTopClients(data.top_clients || []);
    renderTopErrors(data.top_errors || []);
  }

  function renderDaysChart(daysList) {
    chartDays.innerHTML = "";
    if (daysList.length === 0) {
      chartDays.innerHTML = `<div style="margin: auto; color: var(--text-muted); font-size: 0.85rem;">Sin actividad en este período.</div>`;
      return;
    }
    const maxCount = Math.max(...daysList.map((d) => d.count), 1);
    daysList.forEach((d) => {
      const pct = Math.max((d.count / maxCount) * 100, 3);
      const col = document.createElement("div");
      col.className = "bar-col";
      col.title = `Fecha: ${d.date}\nTotal: ${d.count}\nExitosas: ${d.ok}\nErrores: ${d.errors}`;
      const shortDate = d.date.length >= 10 ? d.date.substring(5) : d.date;
      col.innerHTML = `
        <div class="bar-fill" style="height: ${pct}%;"></div>
        <div class="bar-label">${escapeHtml(shortDate)}</div>
      `;
      chartDays.appendChild(col);
    });
  }

  function renderHourlyChart(hourlyList) {
    chartHours.innerHTML = "";
    const hourMap = {};
    for (let i = 0; i < 24; i++) {
      hourMap[i.toString().padStart(2, "0")] = 0;
    }
    hourlyList.forEach((h) => {
      if (h.hour !== null && h.hour !== undefined) {
        hourMap[h.hour] = h.count;
      }
    });

    const counts = Object.values(hourMap);
    const maxCount = Math.max(...counts, 1);

    for (let i = 0; i < 24; i++) {
      const hStr = i.toString().padStart(2, "0");
      const count = hourMap[hStr] || 0;
      const pct = count > 0 ? Math.max((count / maxCount) * 100, 3) : 0;

      const col = document.createElement("div");
      col.className = "bar-col";
      col.title = `${hStr}:00 UTC - ${count} operaciones`;
      const labelText = i % 3 === 0 ? `${hStr}h` : "";
      col.innerHTML = `
        <div class="bar-fill" style="height: ${pct}%; background: ${count > 0 ? "var(--primary)" : "#cbd5e1"};"></div>
        <div class="bar-label">${labelText}</div>
      `;
      chartHours.appendChild(col);
    }
  }

  function renderTypesBars(typesList, totalOps) {
    chartTypes.innerHTML = "";
    if (typesList.length === 0) {
      chartTypes.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem;">Sin registros.</div>`;
      return;
    }

    const typeNames = {
      compress: "Compresión",
      watermark: "Marca de Agua",
      merge: "Unir PDFs",
      split: "Dividir PDFs",
      rotate: "Rotar Páginas",
      protect: "Proteger con Contraseña",
      strip_metadata: "Eliminar Metadatos",
      img2pdf: "Imágenes a PDF",
    };

    typesList.forEach((item) => {
      const label = typeNames[item.operation] || item.operation;
      const pct = totalOps > 0 ? ((item.count / totalOps) * 100).toFixed(1) : 0;
      const row = document.createElement("div");
      row.className = "h-bar-item";
      row.innerHTML = `
        <div class="h-bar-header">
          <span>${escapeHtml(label)}</span>
          <span style="color: var(--text-muted);">${item.count} (${pct}%)</span>
        </div>
        <div class="h-bar-track">
          <div class="h-bar-fill" style="width: ${pct}%;"></div>
        </div>
      `;
      chartTypes.appendChild(row);
    });
  }

  function renderPresetsBars(presetsList, totalOps) {
    chartPresets.innerHTML = "";
    if (presetsList.length === 0) {
      chartPresets.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem;">Sin datos de compresión.</div>`;
      return;
    }

    const presetNames = {
      screen: "Máxima Compresión (~72 DPI)",
      ebook: "Equilibrada (~150 DPI)",
      printer: "Alta Calidad (~300 DPI)",
      custom: "Personalizada (manual)",
    };

    const compOps = presetsList.reduce((acc, p) => acc + p.count, 0);

    presetsList.forEach((p) => {
      const key = p.preset || "ebook";
      const label = presetNames[key] || key;
      const pct = compOps > 0 ? ((p.count / compOps) * 100).toFixed(1) : 0;
      const row = document.createElement("div");
      row.className = "h-bar-item";
      row.innerHTML = `
        <div class="h-bar-header">
          <span>${escapeHtml(label)}</span>
          <span style="color: var(--text-muted);">${p.count} (${pct}%)</span>
        </div>
        <div class="h-bar-track">
          <div class="h-bar-fill" style="width: ${pct}%; background: #0284c7;"></div>
        </div>
      `;
      chartPresets.appendChild(row);
    });
  }

  function renderTopClients(clientsList) {
    tableClients.innerHTML = "";
    if (clientsList.length === 0) {
      tableClients.innerHTML = `<tr><td colspan="3" style="text-align:center; color: var(--text-muted);">Sin registros.</td></tr>`;
      return;
    }

    clientsList.forEach((c) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><code style="background:#f1f5f9; padding: 0.1rem 0.4rem; border-radius: 4px;">${escapeHtml(c.client_id)}</code></td>
        <td><strong>${c.count}</strong></td>
        <td>${c.ok_count}</td>
      `;
      tableClients.appendChild(tr);
    });
  }

  function renderTopErrors(errorsList) {
    tableErrors.innerHTML = "";
    if (errorsList.length === 0) {
      tableErrors.innerHTML = `<tr><td colspan="2" style="text-align:center; color: var(--success);">¡Cero errores registrados en este período!</td></tr>`;
      return;
    }

    const errorNames = {
      ENCRYPTED_PDF: "PDF protegido con contraseña",
      CORRUPT_PDF: "PDF corrupto o formato no válido",
      FILE_TOO_LARGE: "Archivo supera tamaño máximo",
      INVALID_PDF_HEADER: "Cabecera no corresponde a PDF",
      TIMEOUT: "Tiempo de espera agotado",
      GS_NOT_INSTALLED: "Ghostscript no disponible",
      GS_EXECUTION_ERROR: "Fallo de ejecución en Ghostscript",
      WATERMARK_ERROR: "Error en marca de agua",
    };

    errorsList.forEach((e) => {
      const tr = document.createElement("tr");
      const desc = errorNames[e.error_code] || e.error_code || "Error no categorizado";
      tr.innerHTML = `
        <td>
          <div><strong>${escapeHtml(desc)}</strong></div>
          <small style="color: var(--text-muted); font-family: monospace;">${escapeHtml(e.error_code || "UNKNOWN")}</small>
        </td>
        <td><span style="color: var(--danger); font-weight: 600;">${e.count}</span></td>
      `;
      tableErrors.appendChild(tr);
    });
  }

  // Filtros de período
  periodButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      periodButtons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const days = parseInt(btn.dataset.days, 10);
      loadStats(days);
    });
  });

  // Exportar CSV
  btnExportCsv.addEventListener("click", () => {
    let url = "/admin/export.csv";
    const params = [];
    if (exportStart.value) {
      params.push(`start_date=${encodeURIComponent(exportStart.value)}`);
    }
    if (exportEnd.value) {
      params.push(`end_date=${encodeURIComponent(exportEnd.value)}`);
    }
    if (params.length > 0) {
      url += `?${params.join("&")}`;
    }
    window.location.href = url;
  });

  // Carga inicial
  loadStats(currentDays);
});

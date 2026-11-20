// JavaScript Vanilla - 100% Local y sin dependencias externas

document.addEventListener("DOMContentLoaded", () => {
  // === UTILIDADES GLOBALES ===
  function formatBytes(bytes) {
    if (!bytes || bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  }

  function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // === PESTAÑAS PRINCIPALES ===
  const tabCompress = document.getElementById("tabCompress");
  const tabWatermark = document.getElementById("tabWatermark");
  const tabExtras = document.getElementById("tabExtras");

  const compressSection = document.getElementById("compressSection");
  const watermarkSection = document.getElementById("watermarkSection");
  const extrasSection = document.getElementById("extrasSection");

  function switchMainTab(activeTab, activeSec) {
    [tabCompress, tabWatermark, tabExtras].forEach((t) => t.classList.remove("active"));
    [compressSection, watermarkSection, extrasSection].forEach((s) => (s.style.display = "none"));
    activeTab.classList.add("active");
    activeSec.style.display = "block";
  }

  tabCompress.addEventListener("click", () => switchMainTab(tabCompress, compressSection));
  tabWatermark.addEventListener("click", () => switchMainTab(tabWatermark, watermarkSection));
  tabExtras.addEventListener("click", () => switchMainTab(tabExtras, extrasSection));

  // ==========================================
  // 1. MÓDULO DE COMPRESIÓN
  // ==========================================
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("fileInput");
  const fileListContainer = document.getElementById("fileList");
  const presets = document.querySelectorAll(".preset-card");
  const customSliders = document.getElementById("customSliders");
  const dpiRange = document.getElementById("dpiRange");
  const dpiVal = document.getElementById("dpiVal");
  const qRange = document.getElementById("qRange");
  const qVal = document.getElementById("qVal");
  const compressBtn = document.getElementById("compressBtn");
  const resetBtn = document.getElementById("resetBtn");
  const progressContainer = document.getElementById("progressContainer");
  const progressBar = document.getElementById("progressBar");
  const progressStatus = document.getElementById("progressStatus");
  const alertContainer = document.getElementById("alertContainer");
  const resultsContainer = document.getElementById("resultsContainer");

  let selectedFiles = [];
  let currentPreset = "ebook";

  presets.forEach((card) => {
    card.addEventListener("click", () => {
      presets.forEach((c) => c.classList.remove("selected"));
      card.classList.add("selected");
      currentPreset = card.dataset.preset;
      customSliders.style.display = currentPreset === "custom" ? "grid" : "none";
    });
  });

  dpiRange.addEventListener("input", (e) => (dpiVal.textContent = e.target.value));
  qRange.addEventListener("input", (e) => (qVal.textContent = e.target.value));

  function handleFiles(files) {
    alertContainer.innerHTML = "";
    resultsContainer.style.display = "none";
    const validFiles = Array.from(files).filter(
      (f) => f.name.toLowerCase().endsWith(".pdf") || f.type === "application/pdf"
    );

    if (validFiles.length === 0) {
      showCompressAlert("Por favor, selecciona archivos con formato .pdf válidos.", "warning");
      return;
    }

    selectedFiles = validFiles;
    renderFileList();
    compressBtn.disabled = selectedFiles.length === 0;
  }

  function renderFileList() {
    fileListContainer.innerHTML = "";
    if (selectedFiles.length === 0) return;

    selectedFiles.forEach((file) => {
      const item = document.createElement("div");
      item.className = "file-item";
      item.innerHTML = `
        <span class="file-name">${escapeHtml(file.name)}</span>
        <span class="file-size">${formatBytes(file.size)}</span>
      `;
      fileListContainer.appendChild(item);
    });
  }

  dropzone.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (e) => handleFiles(e.target.files));

  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove("dragover");
    });
  });

  dropzone.addEventListener("drop", (e) => {
    if (e.dataTransfer && e.dataTransfer.files) {
      handleFiles(e.dataTransfer.files);
    }
  });

  function showCompressAlert(message, type = "danger") {
    alertContainer.innerHTML = `<div class="alert alert-${type}">${escapeHtml(message)}</div>`;
  }

  resetBtn.addEventListener("click", () => {
    selectedFiles = [];
    fileInput.value = "";
    renderFileList();
    compressBtn.disabled = true;
    progressContainer.style.display = "none";
    alertContainer.innerHTML = "";
    resultsContainer.style.display = "none";
  });

  compressBtn.addEventListener("click", async () => {
    if (selectedFiles.length === 0) return;

    compressBtn.disabled = true;
    resetBtn.disabled = true;
    alertContainer.innerHTML = "";
    resultsContainer.style.display = "none";
    progressContainer.style.display = "block";
    progressBar.style.width = "40%";
    progressStatus.textContent = "Procesando documento(s) con Ghostscript...";

    const formData = new FormData();
    formData.append("preset", currentPreset);
    if (currentPreset === "custom") {
      formData.append("custom_dpi", dpiRange.value);
      formData.append("custom_jpeg_quality", qRange.value);
    }

    const isBatch = selectedFiles.length > 1;
    const endpoint = isBatch ? "/api/compress/batch" : "/api/compress";

    if (isBatch) {
      selectedFiles.forEach((file) => formData.append("files", file));
    } else {
      formData.append("file", selectedFiles[0]);
    }

    try {
      const response = await fetch(endpoint, { method: "POST", body: formData });
      progressBar.style.width = "90%";
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Error en el procesamiento del PDF.");
      }

      progressBar.style.width = "100%";
      progressStatus.textContent = "¡Procesado completado!";

      setTimeout(() => {
        progressContainer.style.display = "none";
        renderCompressResults(data, isBatch);
      }, 400);
    } catch (err) {
      progressContainer.style.display = "none";
      showCompressAlert(err.message || "Error al procesar el archivo.", "danger");
    } finally {
      compressBtn.disabled = false;
      resetBtn.disabled = false;
    }
  });

  function renderCompressResults(data, isBatch) {
    resultsContainer.style.display = "block";
    if (!isBatch) {
      let warningHtml = "";
      if (data.returned_original) {
        warningHtml = `
          <div class="alert alert-warning" style="margin-bottom: 1rem;">
            ℹ️ El archivo comprimido resultaba más pesado que el original. Se ha conservado el archivo original intacto.
          </div>
        `;
      }
      resultsContainer.innerHTML = `
        ${warningHtml}
        <div class="stats-row">
          <div class="stat-box">
            <div class="stat-label">Tamaño Original</div>
            <div class="stat-val">${formatBytes(data.original_size)}</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Tamaño Final</div>
            <div class="stat-val">${formatBytes(data.final_size)}</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Espacio Ahorrado</div>
            <div class="stat-val">
              <span class="badge-savings">-${data.saved_pct}%</span>
              <span style="font-size: 0.85rem; color: var(--text-muted); margin-left: 0.3rem;">
                (${formatBytes(data.saved_bytes)})
              </span>
            </div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Páginas / Tiempo</div>
            <div class="stat-val" style="font-size: 1rem;">
              ${data.pages} págs. · ${(data.duration_ms / 1000).toFixed(1)}s
            </div>
          </div>
        </div>
        <div class="actions">
          <a href="${data.download_url}" class="btn btn-success" download="${escapeHtml(data.filename)}">
            ⬇️ Descargar PDF Comprimido
          </a>
          <button class="btn btn-secondary" onclick="document.getElementById('resetBtn').click()">
            Procesar otro archivo
          </button>
        </div>
      `;
    } else {
      let itemsHtml = "";
      data.items.forEach((item) => {
        if (item.success) {
          itemsHtml += `
            <div class="file-item" style="margin-bottom: 0.5rem;">
              <span class="file-name">${escapeHtml(item.filename)}</span>
              <div style="display: flex; gap: 0.5rem; align-items: center;">
                <span class="badge-savings">-${item.saved_pct}%</span>
                <span class="file-size">${formatBytes(item.final_size)}</span>
                <a href="${item.download_url}" class="btn btn-secondary" style="padding: 0.2rem 0.5rem; font-size: 0.8rem;">⬇️</a>
              </div>
            </div>
          `;
        } else {
          itemsHtml += `
            <div class="file-item" style="margin-bottom: 0.5rem; border-left: 3px solid var(--danger);">
              <span class="file-name">${escapeHtml(item.filename)}</span>
              <span style="color: var(--danger); font-size: 0.8rem;">${escapeHtml(item.error)}</span>
            </div>
          `;
        }
      });
      let zipAction = data.zip_url ? `<a href="${data.zip_url}" class="btn btn-success">📦 Descargar Todo en ZIP</a>` : "";
      resultsContainer.innerHTML = `
        <h4 style="margin-bottom: 1rem;">Resultados del Lote:</h4>
        <div style="margin-bottom: 1.5rem;">${itemsHtml}</div>
        <div class="actions">
          ${zipAction}
          <button class="btn btn-secondary" onclick="document.getElementById('resetBtn').click()">Procesar más archivos</button>
        </div>
      `;
    }
  }

  // ==========================================
  // 2. MÓDULO DE MARCA DE AGUA
  // ==========================================
  const wmDropzone = document.getElementById("wmDropzone");
  const wmTargetFileInput = document.getElementById("wmTargetFileInput");
  const wmFileList = document.getElementById("wmFileList");
  const wmTypeButtons = document.querySelectorAll(".type-btn[data-wmtype]");
  const wmTextOptions = document.getElementById("wmTextOptions");
  const wmFileOptions = document.getElementById("wmFileOptions");
  const wmFileLabel = document.getElementById("wmFileLabel");
  const wmTextInput = document.getElementById("wmTextInput");
  const wmAssetFileInput = document.getElementById("wmAssetFileInput");

  const wmPosButtons = document.querySelectorAll(".pos-btn");
  const wmOpacityRange = document.getElementById("wmOpacityRange");
  const wmOpacityVal = document.getElementById("wmOpacityVal");
  const wmRotationRange = document.getElementById("wmRotationRange");
  const wmRotationVal = document.getElementById("wmRotationVal");
  const wmScaleRange = document.getElementById("wmScaleRange");
  const wmScaleVal = document.getElementById("wmScaleVal");
  const wmPagesInput = document.getElementById("wmPagesInput");

  const wmBtnPreview = document.getElementById("wmBtnPreview");
  const wmPreviewContainer = document.getElementById("wmPreviewContainer");
  const wmPreviewFrame = document.getElementById("wmPreviewFrame");

  const wmAlertContainer = document.getElementById("wmAlertContainer");
  const wmProgressContainer = document.getElementById("wmProgressContainer");
  const wmProgressBar = document.getElementById("wmProgressBar");
  const wmProgressStatus = document.getElementById("wmProgressStatus");
  const wmApplyBtn = document.getElementById("wmApplyBtn");
  const wmResetBtn = document.getElementById("wmResetBtn");
  const wmResultsContainer = document.getElementById("wmResultsContainer");

  let wmSelectedFiles = [];
  let currentWmType = "text";
  let currentPosition = "center";
  let currentPreviewUrl = null;

  wmTypeButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      wmTypeButtons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentWmType = btn.dataset.wmtype;

      if (currentWmType === "text") {
        wmTextOptions.style.display = "block";
        wmFileOptions.style.display = "none";
      } else if (currentWmType === "image") {
        wmTextOptions.style.display = "none";
        wmFileOptions.style.display = "block";
        wmFileLabel.textContent = "Selecciona la imagen (PNG, JPG, WebP):";
        wmAssetFileInput.accept = ".png,.jpg,.jpeg,.webp";
      } else if (currentWmType === "pdf") {
        wmTextOptions.style.display = "none";
        wmFileOptions.style.display = "block";
        wmFileLabel.textContent = "Selecciona el archivo PDF de marca de agua:";
        wmAssetFileInput.accept = ".pdf,application/pdf";
      }
      checkWmReady();
    });
  });

  wmPosButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      wmPosButtons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentPosition = btn.dataset.pos;
    });
  });

  wmOpacityRange.addEventListener("input", (e) => (wmOpacityVal.textContent = e.target.value));
  wmRotationRange.addEventListener("input", (e) => (wmRotationVal.textContent = e.target.value));
  wmScaleRange.addEventListener("input", (e) => (wmScaleVal.textContent = parseFloat(e.target.value).toFixed(1)));

  function showWmAlert(msg, type = "danger") {
    wmAlertContainer.innerHTML = `<div class="alert alert-${type}">${escapeHtml(msg)}</div>`;
  }

  function handleWmFiles(files) {
    wmAlertContainer.innerHTML = "";
    wmResultsContainer.style.display = "none";
    const valids = Array.from(files).filter(
      (f) => f.name.toLowerCase().endsWith(".pdf") || f.type === "application/pdf"
    );
    if (valids.length === 0) {
      showWmAlert("Por favor, selecciona archivos con formato .pdf válidos.", "warning");
      return;
    }
    wmSelectedFiles = valids;
    renderWmFileList();
    checkWmReady();
  }

  function renderWmFileList() {
    wmFileList.innerHTML = "";
    if (wmSelectedFiles.length === 0) return;
    wmSelectedFiles.forEach((file) => {
      const item = document.createElement("div");
      item.className = "file-item";
      item.innerHTML = `
        <span class="file-name">${escapeHtml(file.name)}</span>
        <span class="file-size">${formatBytes(file.size)}</span>
      `;
      wmFileList.appendChild(item);
    });
  }

  function checkWmReady() {
    const hasFiles = wmSelectedFiles.length > 0;
    wmApplyBtn.disabled = !hasFiles;
    wmBtnPreview.disabled = !hasFiles;
  }

  wmDropzone.addEventListener("click", () => wmTargetFileInput.click());
  wmTargetFileInput.addEventListener("change", (e) => handleWmFiles(e.target.files));

  ["dragenter", "dragover"].forEach((eventName) => {
    wmDropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      wmDropzone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    wmDropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      wmDropzone.classList.remove("dragover");
    });
  });

  wmDropzone.addEventListener("drop", (e) => {
    if (e.dataTransfer && e.dataTransfer.files) {
      handleWmFiles(e.dataTransfer.files);
    }
  });

  wmResetBtn.addEventListener("click", () => {
    wmSelectedFiles = [];
    wmTargetFileInput.value = "";
    wmAssetFileInput.value = "";
    renderWmFileList();
    checkWmReady();
    wmProgressContainer.style.display = "none";
    wmAlertContainer.innerHTML = "";
    wmResultsContainer.style.display = "none";
    wmPreviewContainer.style.display = "none";
    if (currentPreviewUrl) {
      URL.revokeObjectURL(currentPreviewUrl);
      currentPreviewUrl = null;
    }
  });

  wmBtnPreview.addEventListener("click", async () => {
    if (wmSelectedFiles.length === 0) return;

    wmAlertContainer.innerHTML = "";
    wmBtnPreview.disabled = true;
    wmBtnPreview.textContent = "Generando vista previa...";

    const fd = new FormData();
    fd.append("file", wmSelectedFiles[0]);
    fd.append("wm_type", currentWmType);
    fd.append("position", currentPosition);
    fd.append("opacity", (parseInt(wmOpacityRange.value, 10) / 100).toFixed(2));
    fd.append("rotation", wmRotationRange.value);
    fd.append("scale", wmScaleRange.value);

    if (currentWmType === "text") {
      fd.append("wm_text", wmTextInput.value || "CONFIDENCIAL");
    } else if (wmAssetFileInput.files && wmAssetFileInput.files[0]) {
      fd.append("wm_file", wmAssetFileInput.files[0]);
    } else {
      showWmAlert("Por favor, selecciona primero el archivo de imagen o PDF para la marca de agua.", "warning");
      wmBtnPreview.disabled = false;
      wmBtnPreview.textContent = "👁️ Actualizar Vista Previa";
      return;
    }

    try {
      const resp = await fetch("/api/watermark/preview", { method: "POST", body: fd });
      if (!resp.ok) {
        const errJson = await resp.json().catch(() => ({}));
        throw new Error(errJson.detail || "Error al generar la previsualización.");
      }
      const blob = await resp.blob();
      if (currentPreviewUrl) {
        URL.revokeObjectURL(currentPreviewUrl);
      }
      currentPreviewUrl = URL.createObjectURL(blob);
      wmPreviewFrame.src = currentPreviewUrl;
      wmPreviewContainer.style.display = "block";
    } catch (err) {
      showWmAlert(err.message, "danger");
    } finally {
      wmBtnPreview.disabled = false;
      wmBtnPreview.textContent = "👁️ Actualizar Vista Previa";
    }
  });

  wmApplyBtn.addEventListener("click", async () => {
    if (wmSelectedFiles.length === 0) return;

    wmApplyBtn.disabled = true;
    wmResetBtn.disabled = true;
    wmAlertContainer.innerHTML = "";
    wmResultsContainer.style.display = "none";
    wmProgressContainer.style.display = "block";
    wmProgressBar.style.width = "40%";
    wmProgressStatus.textContent = "Estampando marca de agua en los documentos...";

    const fd = new FormData();
    fd.append("wm_type", currentWmType);
    fd.append("position", currentPosition);
    fd.append("opacity", (parseInt(wmOpacityRange.value, 10) / 100).toFixed(2));
    fd.append("rotation", wmRotationRange.value);
    fd.append("scale", wmScaleRange.value);
    fd.append("pages_range", wmPagesInput.value.trim() || "all");

    if (currentWmType === "text") {
      fd.append("wm_text", wmTextInput.value || "CONFIDENCIAL");
    } else if (wmAssetFileInput.files && wmAssetFileInput.files[0]) {
      fd.append("wm_file", wmAssetFileInput.files[0]);
    } else {
      wmProgressContainer.style.display = "none";
      showWmAlert("Debes seleccionar un archivo para la marca de agua.", "warning");
      wmApplyBtn.disabled = false;
      wmResetBtn.disabled = false;
      return;
    }

    const isBatch = wmSelectedFiles.length > 1;
    const endpoint = isBatch ? "/api/watermark/batch" : "/api/watermark";

    if (isBatch) {
      wmSelectedFiles.forEach((f) => fd.append("files", f));
    } else {
      fd.append("file", wmSelectedFiles[0]);
    }

    try {
      const resp = await fetch(endpoint, { method: "POST", body: fd });
      wmProgressBar.style.width = "90%";
      const data = await resp.json();

      if (!resp.ok) {
        throw new Error(data.detail || "Error al estampar marca de agua.");
      }

      wmProgressBar.style.width = "100%";
      wmProgressStatus.textContent = "¡Marca de agua estampada con éxito!";

      setTimeout(() => {
        wmProgressContainer.style.display = "none";
        renderWmResults(data, isBatch);
      }, 400);
    } catch (err) {
      wmProgressContainer.style.display = "none";
      showWmAlert(err.message, "danger");
    } finally {
      wmApplyBtn.disabled = false;
      wmResetBtn.disabled = false;
    }
  });

  function renderWmResults(data, isBatch) {
    wmResultsContainer.style.display = "block";
    if (!isBatch) {
      wmResultsContainer.innerHTML = `
        <div class="stats-row">
          <div class="stat-box">
            <div class="stat-label">Tamaño Original</div>
            <div class="stat-val">${formatBytes(data.original_size)}</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Tamaño Final</div>
            <div class="stat-val">${formatBytes(data.final_size)}</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Páginas / Tiempo</div>
            <div class="stat-val" style="font-size: 1rem;">
              ${data.pages} págs. · ${(data.duration_ms / 1000).toFixed(1)}s
            </div>
          </div>
        </div>
        <div class="actions">
          <a href="${data.download_url}" class="btn btn-success" download="${escapeHtml(data.filename)}">
            ⬇️ Descargar PDF con Marca de Agua
          </a>
          <button class="btn btn-secondary" onclick="document.getElementById('wmResetBtn').click()">
            Procesar otro documento
          </button>
        </div>
      `;
    } else {
      let itemsHtml = "";
      data.items.forEach((item) => {
        if (item.success) {
          itemsHtml += `
            <div class="file-item" style="margin-bottom: 0.5rem;">
              <span class="file-name">${escapeHtml(item.filename)}</span>
              <div style="display: flex; gap: 0.5rem; align-items: center;">
                <span class="file-size">${formatBytes(item.final_size)}</span>
                <a href="${item.download_url}" class="btn btn-secondary" style="padding: 0.2rem 0.5rem; font-size: 0.8rem;">⬇️</a>
              </div>
            </div>
          `;
        } else {
          itemsHtml += `
            <div class="file-item" style="margin-bottom: 0.5rem; border-left: 3px solid var(--danger);">
              <span class="file-name">${escapeHtml(item.filename)}</span>
              <span style="color: var(--danger); font-size: 0.8rem;">${escapeHtml(item.error)}</span>
            </div>
          `;
        }
      });
      let zipAction = data.zip_url ? `<a href="${data.zip_url}" class="btn btn-success">📦 Descargar Todo en ZIP</a>` : "";
      wmResultsContainer.innerHTML = `
        <h4 style="margin-bottom: 1rem;">Resultados del Lote:</h4>
        <div style="margin-bottom: 1.5rem;">${itemsHtml}</div>
        <div class="actions">
          ${zipAction}
          <button class="btn btn-secondary" onclick="document.getElementById('wmResetBtn').click()">Procesar más documentos</button>
        </div>
      `;
    }
  }

  // ==========================================
  // 3. MÓDULO DE OTRAS HERRAMIENTAS (EXTRAS)
  // ==========================================
  const extraTypeButtons = document.querySelectorAll(".type-btn[data-extra]");
  const extraDropzone = document.getElementById("extraDropzone");
  const extraFileInput = document.getElementById("extraFileInput");
  const extraDropText = document.getElementById("extraDropText");
  const extraDropHint = document.getElementById("extraDropHint");
  const extraFileList = document.getElementById("extraFileList");

  const extraPanelSplit = document.getElementById("extraPanelSplit");
  const extraPanelRotate = document.getElementById("extraPanelRotate");
  const extraPanelProtect = document.getElementById("extraPanelProtect");
  const extraPanelStrip = document.getElementById("extraPanelStrip");

  const splitPagesInput = document.getElementById("splitPagesInput");
  const rotateAngleSelect = document.getElementById("rotateAngleSelect");
  const rotatePagesInput = document.getElementById("rotatePagesInput");
  const protectPasswordInput = document.getElementById("protectPasswordInput");

  const extraAlertContainer = document.getElementById("extraAlertContainer");
  const extraProgressContainer = document.getElementById("extraProgressContainer");
  const extraProgressBar = document.getElementById("extraProgressBar");
  const extraProgressStatus = document.getElementById("extraProgressStatus");
  const extraApplyBtn = document.getElementById("extraApplyBtn");
  const extraResetBtn = document.getElementById("extraResetBtn");
  const extraResultsContainer = document.getElementById("extraResultsContainer");

  let currentExtraTool = "merge";
  let extraFiles = [];

  const extraToolConfig = {
    merge: {
      btnLabel: "🔗 Unir PDFs",
      dropText: "Arrastra los PDFs a unir (puedes reordenarlos abajo)",
      accept: ".pdf,application/pdf",
      multiple: true,
      minFiles: 2,
    },
    split: {
      btnLabel: "✂️ Dividir PDF",
      dropText: "Arrastra el PDF que deseas dividir",
      accept: ".pdf,application/pdf",
      multiple: false,
      minFiles: 1,
    },
    rotate: {
      btnLabel: "🔄 Rotar Páginas",
      dropText: "Arrastra el PDF cuyas páginas deseas rotar",
      accept: ".pdf,application/pdf",
      multiple: false,
      minFiles: 1,
    },
    protect: {
      btnLabel: "🔒 Proteger PDF",
      dropText: "Arrastra el PDF que deseas cifrar con contraseña",
      accept: ".pdf,application/pdf",
      multiple: false,
      minFiles: 1,
    },
    strip: {
      btnLabel: "🧹 Eliminar Metadatos",
      dropText: "Arrastra el PDF para limpiar datos de autor y software",
      accept: ".pdf,application/pdf",
      multiple: false,
      minFiles: 1,
    },
    img2pdf: {
      btnLabel: "🖼️ Convertir a PDF",
      dropText: "Arrastra las imágenes a convertir (PNG, JPG, WebP)",
      accept: ".png,.jpg,.jpeg,.webp",
      multiple: true,
      minFiles: 1,
    },
  };

  extraTypeButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      extraTypeButtons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentExtraTool = btn.dataset.extra;
      switchExtraTool(currentExtraTool);
    });
  });

  function switchExtraTool(toolKey) {
    const cfg = extraToolConfig[toolKey] || extraToolConfig.merge;
    extraApplyBtn.textContent = cfg.btnLabel;
    extraDropText.textContent = cfg.dropText;
    extraFileInput.accept = cfg.accept;
    extraFileInput.multiple = cfg.multiple;

    // Paneles de opciones
    extraPanelSplit.style.display = toolKey === "split" ? "block" : "none";
    extraPanelRotate.style.display = toolKey === "rotate" ? "block" : "none";
    extraPanelProtect.style.display = toolKey === "protect" ? "block" : "none";
    extraPanelStrip.style.display = toolKey === "strip" ? "block" : "none";

    // Reiniciar archivos
    extraFiles = [];
    extraFileInput.value = "";
    renderExtraFileList();
    checkExtraReady();
    extraAlertContainer.innerHTML = "";
    extraResultsContainer.style.display = "none";
  }

  function handleExtraFiles(fileList) {
    extraAlertContainer.innerHTML = "";
    extraResultsContainer.style.display = "none";
    const cfg = extraToolConfig[currentExtraTool];

    let valids = Array.from(fileList);
    if (currentExtraTool === "img2pdf") {
      valids = valids.filter((f) => /\.(png|jpe?g|webp)$/i.test(f.name) || f.type.startsWith("image/"));
    } else {
      valids = valids.filter((f) => f.name.toLowerCase().endsWith(".pdf") || f.type === "application/pdf");
    }

    if (valids.length === 0) {
      showExtraAlert("Formato de archivo no compatible con la herramienta seleccionada.", "warning");
      return;
    }

    if (!cfg.multiple) {
      extraFiles = [valids[0]];
    } else {
      extraFiles = extraFiles.concat(valids);
    }

    renderExtraFileList();
    checkExtraReady();
  }

  function renderExtraFileList() {
    extraFileList.innerHTML = "";
    if (extraFiles.length === 0) return;

    extraFiles.forEach((file, idx) => {
      const item = document.createElement("div");
      item.className = "file-item";

      let orderButtons = "";
      if (currentExtraTool === "merge" && extraFiles.length > 1) {
        orderButtons = `
          <div style="display: flex; gap: 0.25rem;">
            <button class="btn btn-secondary" style="padding: 0.1rem 0.4rem; font-size: 0.75rem;" ${idx === 0 ? "disabled" : ""} onclick="window.moveExtraFile(${idx}, -1)">▲</button>
            <button class="btn btn-secondary" style="padding: 0.1rem 0.4rem; font-size: 0.75rem;" ${idx === extraFiles.length - 1 ? "disabled" : ""} onclick="window.moveExtraFile(${idx}, 1)">▼</button>
          </div>
        `;
      }

      item.innerHTML = `
        <div style="display: flex; align-items: center; gap: 0.5rem; max-width: 75%;">
          <span style="color: var(--text-muted); font-size: 0.8rem; font-weight: 600;">#${idx + 1}</span>
          <span class="file-name">${escapeHtml(file.name)}</span>
        </div>
        <div style="display: flex; align-items: center; gap: 0.5rem;">
          <span class="file-size">${formatBytes(file.size)}</span>
          ${orderButtons}
          <button class="btn btn-secondary" style="padding: 0.1rem 0.4rem; font-size: 0.75rem; color: var(--danger);" onclick="window.removeExtraFile(${idx})">✕</button>
        </div>
      `;
      extraFileList.appendChild(item);
    });
  }

  // Métodos expuestos globalmente para botones en línea
  window.moveExtraFile = (index, delta) => {
    const target = index + delta;
    if (target < 0 || target >= extraFiles.length) return;
    const temp = extraFiles[index];
    extraFiles[index] = extraFiles[target];
    extraFiles[target] = temp;
    renderExtraFileList();
    checkExtraReady();
  };

  window.removeExtraFile = (index) => {
    extraFiles.splice(index, 1);
    renderExtraFileList();
    checkExtraReady();
  };

  function checkExtraReady() {
    const cfg = extraToolConfig[currentExtraTool];
    extraApplyBtn.disabled = extraFiles.length < cfg.minFiles;
  }

  extraDropzone.addEventListener("click", () => extraFileInput.click());
  extraFileInput.addEventListener("change", (e) => handleExtraFiles(e.target.files));

  ["dragenter", "dragover"].forEach((eventName) => {
    extraDropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      extraDropzone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    extraDropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      extraDropzone.classList.remove("dragover");
    });
  });

  extraDropzone.addEventListener("drop", (e) => {
    if (e.dataTransfer && e.dataTransfer.files) {
      handleExtraFiles(e.dataTransfer.files);
    }
  });

  function showExtraAlert(msg, type = "danger") {
    extraAlertContainer.innerHTML = `<div class="alert alert-${type}">${escapeHtml(msg)}</div>`;
  }

  extraResetBtn.addEventListener("click", () => {
    extraFiles = [];
    extraFileInput.value = "";
    renderExtraFileList();
    checkExtraReady();
    extraProgressContainer.style.display = "none";
    extraAlertContainer.innerHTML = "";
    extraResultsContainer.style.display = "none";
  });

  // Ejecutar Acción Extra
  extraApplyBtn.addEventListener("click", async () => {
    const cfg = extraToolConfig[currentExtraTool];
    if (extraFiles.length < cfg.minFiles) return;

    extraAlertContainer.innerHTML = "";
    extraResultsContainer.style.display = "none";
    extraApplyBtn.disabled = true;
    extraResetBtn.disabled = true;
    extraProgressContainer.style.display = "block";
    extraProgressBar.style.width = "40%";
    extraProgressStatus.textContent = "Procesando documentos en local...";

    const fd = new FormData();
    let endpoint = "";

    if (currentExtraTool === "merge") {
      endpoint = "/api/extras/merge";
      extraFiles.forEach((f) => fd.append("files", f));
    } else if (currentExtraTool === "split") {
      endpoint = "/api/extras/split";
      fd.append("file", extraFiles[0]);
      fd.append("pages_range", splitPagesInput.value.trim() || "1");
    } else if (currentExtraTool === "rotate") {
      endpoint = "/api/extras/rotate";
      fd.append("file", extraFiles[0]);
      fd.append("angle", rotateAngleSelect.value);
      fd.append("pages_range", rotatePagesInput.value.trim() || "all");
    } else if (currentExtraTool === "protect") {
      endpoint = "/api/extras/protect";
      fd.append("file", extraFiles[0]);
      if (!protectPasswordInput.value) {
        extraProgressContainer.style.display = "none";
        showExtraAlert("Debes introducir una contraseña para proteger el archivo.", "warning");
        extraApplyBtn.disabled = false;
        extraResetBtn.disabled = false;
        return;
      }
      fd.append("password", protectPasswordInput.value);
    } else if (currentExtraTool === "strip") {
      endpoint = "/api/extras/strip-metadata";
      fd.append("file", extraFiles[0]);
    } else if (currentExtraTool === "img2pdf") {
      endpoint = "/api/extras/img2pdf";
      extraFiles.forEach((f) => fd.append("files", f));
    }

    try {
      const resp = await fetch(endpoint, { method: "POST", body: fd });
      extraProgressBar.style.width = "90%";
      const data = await resp.json();

      if (!resp.ok) {
        throw new Error(data.detail || "Error en el procesamiento del archivo.");
      }

      extraProgressBar.style.width = "100%";
      extraProgressStatus.textContent = "¡Operación completada con éxito!";

      setTimeout(() => {
        extraProgressContainer.style.display = "none";
        renderExtraResults(data);
      }, 400);
    } catch (err) {
      extraProgressContainer.style.display = "none";
      showExtraAlert(err.message, "danger");
    } finally {
      extraApplyBtn.disabled = false;
      extraResetBtn.disabled = false;
    }
  });

  function renderExtraResults(data) {
    extraResultsContainer.style.display = "block";
    extraResultsContainer.innerHTML = `
      <div class="stats-row">
        <div class="stat-box">
          <div class="stat-label">Tamaño Original</div>
          <div class="stat-val">${formatBytes(data.original_size)}</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Tamaño Resultante</div>
          <div class="stat-val">${formatBytes(data.final_size)}</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Páginas / Tiempo</div>
          <div class="stat-val" style="font-size: 1rem;">
            ${data.pages} págs. · ${(data.duration_ms / 1000).toFixed(1)}s
          </div>
        </div>
      </div>
      <div class="actions">
        <a href="${data.download_url}" class="btn btn-success" download="${escapeHtml(data.filename)}">
          ⬇️ Descargar ${escapeHtml(data.filename)}
        </a>
        <button class="btn btn-secondary" onclick="document.getElementById('extraResetBtn').click()">
          Realizar otra operación
        </button>
      </div>
    `;
  }
});

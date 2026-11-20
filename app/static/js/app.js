// JavaScript Vanilla - 100% Local y sin dependencias externas

document.addEventListener("DOMContentLoaded", () => {
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

  // Formatear bytes a formato legible
  function formatBytes(bytes) {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  }

  // Presets de compresión
  presets.forEach((card) => {
    card.addEventListener("click", () => {
      presets.forEach((c) => c.classList.remove("selected"));
      card.classList.add("selected");
      currentPreset = card.dataset.preset;

      if (currentPreset === "custom") {
        customSliders.style.display = "grid";
      } else {
        customSliders.style.display = "none";
      }
    });
  });

  // Actualizar valores de sliders
  dpiRange.addEventListener("input", (e) => (dpiVal.textContent = e.target.value));
  qRange.addEventListener("input", (e) => (qVal.textContent = e.target.value));

  // Manejo de archivos seleccionados
  function handleFiles(files) {
    alertContainer.innerHTML = "";
    resultsContainer.style.display = "none";

    const validFiles = Array.from(files).filter((f) =>
      f.name.toLowerCase().endsWith(".pdf") || f.type === "application/pdf"
    );

    if (validFiles.length === 0) {
      showAlert("Por favor, selecciona archivos con formato .pdf válidos.", "warning");
      return;
    }

    selectedFiles = validFiles;
    renderFileList();
    compressBtn.disabled = selectedFiles.length === 0;
  }

  function renderFileList() {
    fileListContainer.innerHTML = "";
    if (selectedFiles.length === 0) return;

    selectedFiles.forEach((file, index) => {
      const item = document.createElement("div");
      item.className = "file-item";
      item.innerHTML = `
        <span class="file-name">${escapeHtml(file.name)}</span>
        <span class="file-size">${formatBytes(file.size)}</span>
      `;
      fileListContainer.appendChild(item);
    });
  }

  // Drag and Drop
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
    const dt = e.dataTransfer;
    if (dt && dt.files) {
      handleFiles(dt.files);
    }
  });

  // Mostrar alertas
  function showAlert(message, type = "danger") {
    alertContainer.innerHTML = `
      <div class="alert alert-${type}">
        ${escapeHtml(message)}
      </div>
    `;
  }

  // Escape HTML para seguridad en interfaz
  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // Reiniciar estado
  resetBtn.addEventListener("click", () => {
    selectedFiles = [];
    fileInput.value = "";
    renderFileList();
    compressBtn.disabled = true;
    progressContainer.style.display = "none";
    alertContainer.innerHTML = "";
    resultsContainer.style.display = "none";
  });

  // Enviar a compresión
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
      const response = await fetch(endpoint, {
        method: "POST",
        body: formData,
      });

      progressBar.style.width = "90%";

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Error en el procesamiento del PDF.");
      }

      progressBar.style.width = "100%";
      progressStatus.textContent = "¡Procesado completado!";

      setTimeout(() => {
        progressContainer.style.display = "none";
        renderResults(data, isBatch);
      }, 400);

    } catch (err) {
      progressContainer.style.display = "none";
      showAlert(err.message || "Error al procesar el archivo.", "danger");
    } finally {
      compressBtn.disabled = false;
      resetBtn.disabled = false;
    }
  });

  // Renderizar resultados
  function renderResults(data, isBatch) {
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
      // Resultados por lotes
      let itemsHtml = "";
      data.items.forEach((item) => {
        if (item.success) {
          itemsHtml += `
            <div class="file-item" style="margin-bottom: 0.5rem;">
              <span class="file-name">${escapeHtml(item.filename)}</span>
              <div style="display: flex; gap: 0.5rem; align-items: center;">
                <span class="badge-savings">-${item.saved_pct}%</span>
                <span class="file-size">${formatBytes(item.final_size)}</span>
                <a href="${item.download_url}" class="btn btn-secondary" style="padding: 0.2rem 0.5rem; font-size: 0.8rem;">
                  ⬇️
                </a>
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

      let zipAction = "";
      if (data.zip_url) {
        zipAction = `
          <a href="${data.zip_url}" class="btn btn-success">
            📦 Descargar Todo en ZIP
          </a>
        `;
      }

      resultsContainer.innerHTML = `
        <h4 style="margin-bottom: 1rem;">Resultados del Lote:</h4>
        <div style="margin-bottom: 1.5rem;">
          ${itemsHtml}
        </div>
        <div class="actions">
          ${zipAction}
          <button class="btn btn-secondary" onclick="document.getElementById('resetBtn').click()">
            Procesar más archivos
          </button>
        </div>
      `;
    }
  }
});

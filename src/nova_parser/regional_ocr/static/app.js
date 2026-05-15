"use strict";

const api = {
  async getImages() {
    const r = await fetch("/api/images");
    if (!r.ok) throw new Error(`GET /api/images failed: ${r.status}`);
    return r.json();
  },
  async getImageMeta(name) {
    const r = await fetch(`/api/image/${encodeURIComponent(name)}`);
    if (!r.ok) throw new Error(`GET /api/image/${name} failed: ${r.status}`);
    return r.json();
  },
  async getSession(name) {
    const r = await fetch(`/api/session/${encodeURIComponent(name)}`);
    if (!r.ok) throw new Error(`GET /api/session/${name} failed: ${r.status}`);
    return r.json();
  },
  async putSession(name, session) {
    const r = await fetch(`/api/session/${encodeURIComponent(name)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(session),
    });
    if (!r.ok) throw new Error(`PUT /api/session/${name} failed: ${r.status}`);
    return r.json();
  },
  async ocrSingle(name, rectId) {
    const r = await fetch(
      `/api/ocr/${encodeURIComponent(name)}/${encodeURIComponent(rectId)}`,
      { method: "POST" },
    );
    if (!r.ok) throw new Error(`POST /api/ocr/${name}/${rectId} failed: ${r.status}`);
    return r.json();
  },
  ocrBatchStream(signal) {
    return fetch("/api/ocr/batch/stream", { method: "POST", signal });
  },
};

const SAVE_DEBOUNCE_MS = 500;
const MIN_DRAG_PX = 5;

function clampInt(v, min, max) {
  return Math.max(min, Math.min(max, Math.round(v)));
}

function displayToNatural(rect, scaleX, scaleY, naturalW, naturalH) {
  const x = clampInt(rect.x / scaleX, 0, Math.max(0, naturalW - 1));
  const y = clampInt(rect.y / scaleY, 0, Math.max(0, naturalH - 1));
  const width = clampInt(rect.width / scaleX, 1, naturalW - x);
  const height = clampInt(rect.height / scaleY, 1, naturalH - y);
  return { x, y, width, height };
}

function generateRectId() {
  const u = (crypto.randomUUID && crypto.randomUUID()) || `${Date.now()}-${Math.random()}`;
  return `${u.slice(0, 8)}-${Date.now().toString(36)}`;
}

function nextDrawOrder(regions) {
  if (!regions.length) return 0;
  return Math.max(...regions.map((r) => r.rectangle.draw_order)) + 1;
}

function regionalOcrApp() {
  return {
    images: [],
    warnings: [],
    currentImage: null,
    session: null,
    imgLoaded: false,
    selectedRectId: null,
    scaleX: 1,
    scaleY: 1,
    draftRect: null,
    dragMode: null,
    dragStart: null,
    saveTimer: null,
    savingState: "idle",
    sseController: null,
    batchRunning: false,
    ocrLog: [],

    async init() {
      try {
        const data = await api.getImages();
        this.images = data.images;
        this.warnings = data.warnings;
      } catch (err) {
        console.error(err);
        this.warnings = [`画像一覧の取得に失敗: ${err.message}`];
      }
      window.addEventListener("resize", () => this.recomputeScale());
      window.addEventListener("beforeunload", () => this.cancelBatch());
    },

    async selectImage(name) {
      this.cancelBatch();
      this.selectedRectId = null;
      this.imgLoaded = false;
      this.draftRect = null;
      try {
        const meta = await api.getImageMeta(name);
        this.currentImage = {
          name,
          width: meta.image_width,
          height: meta.image_height,
          mime: meta.mime_type,
        };
        this.session = await api.getSession(name);
      } catch (err) {
        console.error(err);
        this.currentImage = null;
        this.session = null;
        this.warnings = [`画像のロードに失敗: ${err.message}`];
      }
    },

    onImageLoad(event) {
      const img = event.target;
      this.imgLoaded = true;
      this.recomputeScale(img);
    },

    recomputeScale(imgEl) {
      const img = imgEl || document.querySelector(".canvas-wrap img");
      if (!img || !this.currentImage) return;
      const rect = img.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      this.scaleX = rect.width / this.currentImage.width;
      this.scaleY = rect.height / this.currentImage.height;
    },

    regionStyle(rect) {
      return {
        left: `${rect.x * this.scaleX}px`,
        top: `${rect.y * this.scaleY}px`,
        width: `${rect.width * this.scaleX}px`,
        height: `${rect.height * this.scaleY}px`,
      };
    },

    draftStyle() {
      const d = this.draftRect;
      return {
        left: `${d.x}px`,
        top: `${d.y}px`,
        width: `${d.width}px`,
        height: `${d.height}px`,
      };
    },

    _displayCoord(event) {
      const wrap = document.querySelector(".canvas-wrap");
      if (!wrap) return { x: 0, y: 0 };
      const img = wrap.querySelector("img");
      if (!img) return { x: 0, y: 0 };
      const rect = img.getBoundingClientRect();
      return { x: event.clientX - rect.left, y: event.clientY - rect.top };
    },

    onMouseDown(event) {
      if (!this.session || !this.imgLoaded) return;
      if (event.target.classList.contains("handle") || event.target.classList.contains("region")) return;
      if (event.target.classList.contains("region-delete")) return;
      const { x, y } = this._displayCoord(event);
      this.dragMode = "create";
      this.dragStart = { x, y };
      this.draftRect = { x, y, width: 0, height: 0 };
      this.selectedRectId = null;
    },

    onMouseMove(event) {
      if (!this.dragMode) return;
      if (this.dragMode === "create") {
        const { x, y } = this._displayCoord(event);
        const startX = Math.min(this.dragStart.x, x);
        const startY = Math.min(this.dragStart.y, y);
        this.draftRect = {
          x: startX,
          y: startY,
          width: Math.abs(x - this.dragStart.x),
          height: Math.abs(y - this.dragStart.y),
        };
      } else if (this.dragMode === "resize") {
        this._applyResize(event);
      } else if (this.dragMode === "move") {
        this._applyMove(event);
      }
    },

    onMouseUp() {
      if (this.dragMode === "create" && this.draftRect) {
        if (this.draftRect.width >= MIN_DRAG_PX && this.draftRect.height >= MIN_DRAG_PX) {
          this._addRegionFromDraft();
        }
      }
      this.draftRect = null;
      this.dragMode = null;
      this.dragStart = null;
    },

    _addRegionFromDraft() {
      const natural = displayToNatural(
        this.draftRect,
        this.scaleX,
        this.scaleY,
        this.currentImage.width,
        this.currentImage.height,
      );
      const rect = {
        rect_id: generateRectId(),
        draw_order: nextDrawOrder(this.session.regions),
        ...natural,
      };
      this.session.regions.push({
        rectangle: rect,
        text: null,
        ocr_status: "pending",
        ocr_error: null,
        ocr_completed_at: null,
      });
      this.selectedRectId = rect.rect_id;
      this.scheduleSave();
    },

    selectRect(rectId) {
      this.selectedRectId = rectId;
    },

    deleteRect(rectId) {
      if (!this.session) return;
      this.session.regions = this.session.regions.filter((r) => r.rectangle.rect_id !== rectId);
      if (this.selectedRectId === rectId) this.selectedRectId = null;
      this.scheduleSave();
    },

    startResize(event, rectId, edge) {
      if (!this.session) return;
      this.selectedRectId = rectId;
      this.dragMode = "resize";
      const region = this.session.regions.find((r) => r.rectangle.rect_id === rectId);
      if (!region) return;
      this.dragStart = {
        clientX: event.clientX,
        clientY: event.clientY,
        edge,
        original: { ...region.rectangle },
      };
    },

    _applyResize(event) {
      if (!this.dragStart) return;
      const { clientX, clientY, edge, original } = this.dragStart;
      const dxDisp = event.clientX - clientX;
      const dyDisp = event.clientY - clientY;
      const dxNat = dxDisp / this.scaleX;
      const dyNat = dyDisp / this.scaleY;
      const region = this.session.regions.find((r) => r.rectangle.rect_id === this.selectedRectId);
      if (!region) return;
      let x = original.x;
      let y = original.y;
      let width = original.width;
      let height = original.height;
      if (edge.includes("e")) width = Math.max(1, original.width + dxNat);
      if (edge.includes("s")) height = Math.max(1, original.height + dyNat);
      if (edge.includes("w")) {
        x = original.x + dxNat;
        width = original.width - dxNat;
        if (width < 1) {
          x = original.x + original.width - 1;
          width = 1;
        }
      }
      if (edge.includes("n")) {
        y = original.y + dyNat;
        height = original.height - dyNat;
        if (height < 1) {
          y = original.y + original.height - 1;
          height = 1;
        }
      }
      const maxW = this.currentImage.width;
      const maxH = this.currentImage.height;
      x = clampInt(x, 0, Math.max(0, maxW - 1));
      y = clampInt(y, 0, Math.max(0, maxH - 1));
      width = clampInt(width, 1, maxW - x);
      height = clampInt(height, 1, maxH - y);
      region.rectangle = { ...region.rectangle, x, y, width, height };
      this.scheduleSave();
    },

    _applyMove() {
      // 現状未使用（リサイズと作成のみ）。将来の移動操作のためのフック。
    },

    scheduleSave() {
      if (!this.session || !this.currentImage) return;
      this.savingState = "saving";
      if (this.saveTimer) clearTimeout(this.saveTimer);
      const snapshot = JSON.parse(JSON.stringify(this.session));
      this.saveTimer = setTimeout(async () => {
        try {
          const saved = await api.putSession(this.currentImage.name, snapshot);
          // サーバ側で done レコードがマージされる可能性があるため反映
          this.session = saved;
          this.savingState = "idle";
        } catch (err) {
          console.error(err);
          this.savingState = "error";
        }
      }, SAVE_DEBOUNCE_MS);
    },

    async runSingleOcr(rectId) {
      if (!this.currentImage) return;
      try {
        const updated = await api.ocrSingle(this.currentImage.name, rectId);
        const idx = this.session.regions.findIndex((r) => r.rectangle.rect_id === rectId);
        if (idx >= 0) this.session.regions[idx] = updated;
      } catch (err) {
        console.error(err);
      }
    },

    async runBatchOcr() {
      if (this.batchRunning) return;
      this.batchRunning = true;
      this.ocrLog = [];
      const controller = new AbortController();
      this.sseController = controller;
      try {
        const resp = await api.ocrBatchStream(controller.signal);
        if (!resp.ok || !resp.body) {
          throw new Error(`batch stream failed: ${resp.status}`);
        }
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        try {
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let idx;
            while ((idx = buffer.indexOf("\n\n")) !== -1) {
              const chunk = buffer.slice(0, idx);
              buffer = buffer.slice(idx + 2);
              for (const line of chunk.split("\n")) {
                if (line.startsWith("data: ")) {
                  try {
                    const item = JSON.parse(line.slice("data: ".length));
                    this.applyOcrItem(item);
                  } catch (e) {
                    console.warn("SSE parse error", e);
                  }
                }
              }
            }
          }
        } finally {
          try {
            reader.releaseLock();
          } catch (_) {
            // already released
          }
        }
      } catch (err) {
        if (err.name !== "AbortError") {
          console.error(err);
        }
      } finally {
        this.batchRunning = false;
        this.sseController = null;
      }
    },

    cancelBatch() {
      if (this.sseController) {
        this.sseController.abort();
        this.sseController = null;
      }
    },

    applyOcrItem(item) {
      this.ocrLog.push(item);
      if (this.ocrLog.length > 50) this.ocrLog.shift();
      if (!this.session || !this.currentImage) return;
      if (item.image_name !== this.currentImage.name) return;
      const idx = this.session.regions.findIndex((r) => r.rectangle.rect_id === item.rect_id);
      if (idx < 0) return;
      const region = this.session.regions[idx];
      this.session.regions[idx] = {
        ...region,
        text: item.text ?? region.text,
        ocr_status: item.status,
        ocr_error: item.error ?? null,
        ocr_completed_at: new Date().toISOString(),
      };
    },
  };
}

window.regionalOcrApp = regionalOcrApp;

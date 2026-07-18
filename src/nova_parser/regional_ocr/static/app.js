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
  async getBlocks(name) {
    const r = await fetch(`/api/blocks/${encodeURIComponent(name)}`);
    if (!r.ok) throw new Error(`GET /api/blocks/${name} failed: ${r.status}`);
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
const ZOOM_MIN = 0.25;
const ZOOM_MAX = 8.0;
const ZOOM_STEP = 1.25;

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

function hitTestBlock(blocks, x, y) {
  let best = null;
  for (const b of blocks) {
    if (x < b.x || y < b.y || x >= b.x + b.width || y >= b.y + b.height) continue;
    if (!best || b.width * b.height < best.width * best.height) best = b;
  }
  return best;
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
    inFlightSave: null,
    saveVersion: 0,
    savingState: "idle",
    sseController: null,
    batchRunning: false,
    ocrLog: [],
    zoom: 1.0,
    zoomFit: true,
    blockMode: false,
    blockGranularity: "vertical",
    paragraphBlocks: null,
    verticalBlocks: null,
    blocksLoading: false,
    hoverBlock: null,
    _blocksRequestFor: null,
    _blocksRequestEpoch: null,
    _blocksEpoch: 0,

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
      // バッチ OCR は save の await を待たず即時停止（SSE 接続を切断）
      this.cancelBatch();

      // 旧画像の保存を完全に drain してから image switch に進む。
      //
      // ループにする理由:
      //   - await 中はマイクロタスク境界が挟まり、user の edit や既存 saveTimer の
      //     fire が走り得る。これらは新たな saveTimer / inFlightSave を発生させる。
      //   - 1 回だけ flush + await で済ませると、await 直後に発生した新 save が drain
      //     されず、selectImage がそのまま image switch を始めてしまう（"old-image
      //     debounce dropped" 状態）。
      //   - while で saveTimer と inFlightSave が両方 null になるまで drain することで、
      //     image switch 直前の時点で旧画像の autosave が完全に backend に反映される。
      //
      // pending snapshot capture を await 前に行う点も維持:
      //   - 後続の await 中に古い PUT response が _performSave 内で
      //     this.session = saved を実行しても、capture 済み snapshot は影響を受けない。
      //   - saveVersion を進めることで、自分が "最新世代の save" として扱われる。
      while (this.saveTimer || this.inFlightSave) {
        let pendingFlush = null;
        if (this.saveTimer && this.session && this.currentImage) {
          clearTimeout(this.saveTimer);
          this.saveTimer = null;
          this.saveVersion += 1;
          pendingFlush = {
            imageName: this.currentImage.name,
            snapshot: JSON.parse(JSON.stringify(this.session)),
            version: this.saveVersion,
          };
        } else if (this.saveTimer) {
          // session / currentImage が null なのに timer が残っている異常状態。
          // データを送れないので timer だけ破棄してループ継続。
          clearTimeout(this.saveTimer);
          this.saveTimer = null;
        }

        // pending flush は _launchSave 経由で発行する。これで:
        //   1. 既存 in-flight chain の完了後に flush PUT が送られる（古い PUT が
        //      後着で flush を上書きする race を防ぐ）。
        //   2. flush 自身も this.inFlightSave に登録されるので、この PUT 中に
        //      新たな scheduleSave が走っても、その save は flush を await して
        //      同じ chain に組み込まれる（serialization の連鎖が切れない）。
        //   3. 失敗は _launchSave 内の IIFE で _reportSaveFailure に転送される。
        const waitFor = pendingFlush
          ? this._launchSave(pendingFlush.imageName, pendingFlush.snapshot, pendingFlush.version)
          : this.inFlightSave;

        if (waitFor) {
          await waitFor;
        }
      }
      this.savingState = "idle";

      this.selectedRectId = null;
      this.imgLoaded = false;
      this.draftRect = null;
      this.paragraphBlocks = null;
      this.verticalBlocks = null;
      this.hoverBlock = null;
      this._blocksEpoch += 1;
      try {
        const meta = await api.getImageMeta(name);
        this.currentImage = {
          name,
          width: meta.image_width,
          height: meta.image_height,
          mime: meta.mime_type,
        };
        this.session = await api.getSession(name);
        if (this.blockMode) this._ensureBlocks();
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

    imgStyle() {
      if (this.zoomFit || !this.currentImage) return {};
      return {
        width: `${this.currentImage.width * this.zoom}px`,
        maxWidth: "none",
      };
    },

    _applyZoomTick() {
      const tick = this.$nextTick ? this.$nextTick.bind(this) : (fn) => Promise.resolve().then(fn);
      tick(() => this.recomputeScale());
    },

    _currentEffectiveScale() {
      const s = this.zoomFit ? this.scaleX : this.zoom;
      if (!Number.isFinite(s) || s <= 0) return 1.0;
      return s;
    },

    zoomIn() {
      if (this.dragMode) return;
      const base = this._currentEffectiveScale();
      const next = Math.min(base * ZOOM_STEP, ZOOM_MAX);
      if (next <= base) return;
      this.zoomFit = false;
      this.zoom = next;
      this._applyZoomTick();
    },

    zoomOut() {
      if (this.dragMode) return;
      const base = this._currentEffectiveScale();
      const next = Math.max(base / ZOOM_STEP, ZOOM_MIN);
      if (next >= base) return;
      this.zoomFit = false;
      this.zoom = next;
      this._applyZoomTick();
    },

    zoomFitToggle() {
      if (this.dragMode) return;
      this.zoomFit = true;
      this.zoom = 1.0;
      this._applyZoomTick();
    },

    zoomReset() {
      if (this.dragMode) return;
      this.zoomFit = false;
      this.zoom = 1.0;
      this._applyZoomTick();
    },

    zoomPercent() {
      const v = this.zoomFit ? this.scaleX : this.zoom;
      return Math.round(v * 100);
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
      if (this.blockMode) {
        this._addRegionFromBlockClick(event);
        return;
      }
      const { x, y } = this._displayCoord(event);
      this.dragMode = "create";
      this.dragStart = { x, y };
      this.draftRect = { x, y, width: 0, height: 0 };
      this.selectedRectId = null;
    },

    onMouseMove(event) {
      if (this.blockMode && !this.dragMode) {
        this._updateHoverBlock(event);
        return;
      }
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

    async toggleBlockMode() {
      if (this.blockMode) {
        this.blockMode = false;
        this.hoverBlock = null;
        // 検出中に OFF された場合、in-flight 応答を破棄しローディング表示を即消しする。
        // epoch を進めることで、到着した応答は _ensureBlocks の epoch ガードで弾かれる。
        this._blocksEpoch += 1;
        this.blocksLoading = false;
        return;
      }
      if (!this.currentImage) return;
      this.blockMode = true;
      await this._ensureBlocks();
    },

    activeBlocks() {
      const paragraphs = this.paragraphBlocks || [];
      if (this.blockGranularity === "paragraph") return paragraphs;
      const vertical = this.verticalBlocks || [];
      // 縦ブロックが 0 件でも段落があれば段落矩形へフォールバックする
      return vertical.length ? vertical : paragraphs;
    },

    setGranularity(value) {
      if (value !== "vertical" && value !== "paragraph") return;
      this.blockGranularity = value;
      // 粒度変更でホバーをクリアし、次の mousemove から新しい当たり判定を使う
      this.hoverBlock = null;
    },

    async _ensureBlocks() {
      if (!this.currentImage || this.paragraphBlocks !== null) return;
      const imageName = this.currentImage.name;
      // await 前に epoch を捕捉する。selectImage が画像を切り替える（同名再選択を含む）
      // たびに epoch を進めるので、応答が届いた時点で epoch が食い違っていれば
      // 「画像名は一致するが実は別世代」の stale 応答だと判定できる。
      const epoch = this._blocksEpoch;
      // 同一画像 かつ 同一世代 の取得が既に走っている場合のみ抑止する。
      // 世代も見ることで、同名再選択（epoch が進む）のときに新世代の取得が
      // 「画像名一致」だけで飢餓させられるのを防ぐ。
      if (this._blocksRequestFor === imageName && this._blocksRequestEpoch === epoch) return;
      this._blocksRequestFor = imageName;
      this._blocksRequestEpoch = epoch;
      this.blocksLoading = true;
      try {
        const result = await api.getBlocks(imageName);
        // 取得中に画像が切り替わった場合、古い画像の blocks を反映しない
        // （画像名一致だけでは selectImage の meta/session await 中に届いた
        //  stale 応答をすり抜けさせてしまうため、epoch も併せて確認する）
        if (!this.currentImage || this.currentImage.name !== imageName || epoch !== this._blocksEpoch) return;
        this.paragraphBlocks = result.blocks || [];
        this.verticalBlocks = result.vertical_blocks || [];
        if (this.paragraphBlocks.length === 0 && this.verticalBlocks.length === 0) {
          const msg = `「${imageName}」からテキストブロックが検出されませんでした`;
          // 同一画像を行き来した際に同文言の警告が重複蓄積しないようにする
          if (!this.warnings.includes(msg)) this.warnings = [...this.warnings, msg];
        }
      } catch (err) {
        console.error(err);
        if (this.currentImage && this.currentImage.name === imageName && epoch === this._blocksEpoch) {
          const msg = `「${imageName}」のテキストブロック検出に失敗しました: ${err.message}`;
          // 0 件警告と同様に、同一画像での連続失敗で同文言が重複蓄積しないよう抑止する
          if (!this.warnings.includes(msg)) this.warnings = [...this.warnings, msg];
          this.blockMode = false;
        }
      } finally {
        // 自分（同一画像・同一世代）が最新のリクエストである場合だけ解除する。
        // 古い世代の finally が新しい世代の loading 所有権を奪わないようにする。
        if (this._blocksRequestFor === imageName && this._blocksRequestEpoch === epoch) {
          this._blocksRequestFor = null;
          this._blocksRequestEpoch = null;
          this.blocksLoading = false;
        }
      }
    },

    _addRegionFromBlockClick(event) {
      const blocks = this.activeBlocks();
      if (!blocks.length) return;
      const { x, y } = this._displayCoord(event);
      const block = hitTestBlock(blocks, x / this.scaleX, y / this.scaleY);
      if (!block) return;
      const rect = {
        rect_id: generateRectId(),
        draw_order: nextDrawOrder(this.session.regions),
        x: block.x,
        y: block.y,
        width: block.width,
        height: block.height,
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

    _updateHoverBlock(event) {
      const blocks = this.activeBlocks();
      if (!blocks.length || !this.imgLoaded) {
        this.hoverBlock = null;
        return;
      }
      const { x, y } = this._displayCoord(event);
      this.hoverBlock = hitTestBlock(blocks, x / this.scaleX, y / this.scaleY);
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
      this.saveVersion += 1;
      const version = this.saveVersion;
      const snapshot = JSON.parse(JSON.stringify(this.session));
      const imageName = this.currentImage.name;
      this.saveTimer = setTimeout(() => {
        this.saveTimer = null;
        this._launchSave(imageName, snapshot, version);
      }, SAVE_DEBOUNCE_MS);
    },

    _launchSave(imageName, snapshot, version) {
      // autosave 群を厳密に直列化するため、直前 in-flight save が完了してから
      // 自分の PUT を実行する。これで「saveTimer fire 時点で前の PUT がまだ
      // network 上にあり、古い PUT が新しい PUT の後で server へ届いて上書き
      // する」race を防ぐ。さらに自分自身を this.inFlightSave に登録するので、
      // この PUT 中に新たに scheduled された save も同じ chain に連結される。
      // 失敗報告は自分の IIFE 内で行う（chain の中間 save の失敗を
      // selectImage が拾えないと warnings に残らない問題を解消）。
      // _performSave は throw せず {ok, error} を返すので、await previous は安全。
      const previous = this.inFlightSave;
      const promise = (async () => {
        if (previous) await previous;
        const result = await this._performSave(imageName, snapshot, version);
        if (!result.ok) {
          this._reportSaveFailure(imageName, result.error);
        }
        return { ...result, imageName };
      })();
      this.inFlightSave = promise;
      promise.finally(() => {
        if (this.inFlightSave === promise) {
          this.inFlightSave = null;
        }
      });
      return promise;
    },

    async _performSave(imageName, snapshot, version) {
      try {
        const saved = await api.putSession(imageName, snapshot);
        // session を反映するのは「同じ画像 + 自分が最新世代の save」の場合のみ。
        // version が新しい save に追い越されている時は、queued autosave の古い response
        // で this.session を上書きすると、その間にユーザーが行った編集が live state から
        // 消えてしまう（roll back）。version が一致する時だけ反映することで roll back を防ぐ。
        if (
          this.currentImage &&
          this.currentImage.name === imageName &&
          this.saveVersion === version
        ) {
          this.session = saved;
          this.savingState = "idle";
        }
        return { ok: true };
      } catch (err) {
        console.error(err);
        // savingState='error' も最新世代の失敗時だけ表示する。
        // 古い queued save の失敗で error をフラッシュすると、後続成功で隠れて UX が悪い。
        if (
          this.currentImage &&
          this.currentImage.name === imageName &&
          this.saveVersion === version
        ) {
          this.savingState = "error";
        }
        return { ok: false, error: err };
      }
    },

    _reportSaveFailure(imageName, error) {
      const message = error?.message ?? String(error);
      this.warnings = [
        ...this.warnings,
        `「${imageName}」の保存に失敗しました: ${message}`,
      ];
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

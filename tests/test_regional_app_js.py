"""regional_ocr/static/app.js の client-side autosave 回帰テスト。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_JS = "src/nova_parser/regional_ocr/static/app.js"


def _run_node(script: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node executable is required for app.js regression tests")

    result = subprocess.run(
        [node, "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_select_image_serializes_in_flight_save_before_pending_flush() -> None:
    """画像切替時、未完了 PUT の後に pending debounce の最新 snapshot を保存してから切り替える。"""
    _run_node(
        r"""
const assert = require("node:assert/strict");

global.window = {};

const putResolvers = [];
const calls = [];

function sessionPayload(imageName, rectIds) {
  return {
    image_name: imageName,
    image_width: 100,
    image_height: 100,
    schema_version: 1,
    regions: rectIds.map((rectId, idx) => ({
      rectangle: {
        rect_id: rectId,
        draw_order: idx,
        x: idx * 10,
        y: idx * 10,
        width: 30,
        height: 30,
      },
      text: null,
      ocr_status: "pending",
      ocr_error: null,
      ocr_completed_at: null,
    })),
  };
}

function fetchResponse(payload) {
  return { ok: true, json: async () => payload };
}

global.fetch = (url, options = {}) => {
  if (options.method === "PUT") {
    const body = JSON.parse(options.body);
    calls.push({ type: "PUT", url, body });
    return new Promise((resolve) => {
      putResolvers.push(() => resolve(fetchResponse(body)));
    });
  }
  if (url === "/api/image/new.png") {
    calls.push({ type: "GET_META", url });
    return Promise.resolve(fetchResponse({ image_width: 200, image_height: 200, mime_type: "image/png" }));
  }
  if (url === "/api/session/new.png") {
    calls.push({ type: "GET_SESSION", url });
    return Promise.resolve(fetchResponse(sessionPayload("new.png", ["new-r0"])));
  }
  throw new Error(`unexpected fetch: ${url}`);
};

require("./src/nova_parser/regional_ocr/static/app.js");

const tick = () => new Promise((resolve) => setImmediate(resolve));

(async () => {
  const app = window.regionalOcrApp();
  app.currentImage = { name: "old.png", width: 100, height: 100, mime: "image/png" };
  app.session = sessionPayload("old.png", ["old-v2-r0", "old-v2-r1"]);
  app.saveVersion = 1;

  app._launchSave("old.png", sessionPayload("old.png", ["old-v1-r0"]), 1);
  app.saveTimer = setTimeout(() => {}, 60_000);

  const selecting = app.selectImage("new.png");
  await tick();

  assert.deepEqual(
    calls.map((call) => call.type),
    ["PUT"],
    "pending flush must wait until the already in-flight PUT has resolved",
  );
  assert.deepEqual(
    calls[0].body.regions.map((region) => region.rectangle.rect_id),
    ["old-v1-r0"],
  );

  putResolvers.shift()();
  await tick();

  assert.deepEqual(
    calls.map((call) => call.type),
    ["PUT", "PUT"],
    "selectImage should enqueue the pending flush before loading the next image",
  );
  assert.deepEqual(
    calls[1].body.regions.map((region) => region.rectangle.rect_id),
    ["old-v2-r0", "old-v2-r1"],
  );

  putResolvers.shift()();
  await selecting;

  assert.deepEqual(
    calls.map((call) => call.type),
    ["PUT", "PUT", "GET_META", "GET_SESSION"],
  );
  assert.equal(app.currentImage.name, "new.png");
  assert.equal(app.session.image_name, "new.png");
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
""",
    )


def test_select_image_drains_save_scheduled_while_flush_is_in_flight() -> None:
    """pending flush の await 中に発生した編集も、画像切替前に drain される。"""
    _run_node(
        r"""
const assert = require("node:assert/strict");

global.window = {};

const putResolvers = [];
const calls = [];

function sessionPayload(imageName, rectIds) {
  return {
    image_name: imageName,
    image_width: 100,
    image_height: 100,
    schema_version: 1,
    regions: rectIds.map((rectId, idx) => ({
      rectangle: {
        rect_id: rectId,
        draw_order: idx,
        x: idx * 10,
        y: idx * 10,
        width: 30,
        height: 30,
      },
      text: null,
      ocr_status: "pending",
      ocr_error: null,
      ocr_completed_at: null,
    })),
  };
}

function fetchResponse(payload) {
  return { ok: true, json: async () => payload };
}

global.fetch = (url, options = {}) => {
  if (options.method === "PUT") {
    const body = JSON.parse(options.body);
    calls.push({ type: "PUT", url, body });
    return new Promise((resolve) => {
      putResolvers.push(() => resolve(fetchResponse(body)));
    });
  }
  if (url === "/api/image/new.png") {
    calls.push({ type: "GET_META", url });
    return Promise.resolve(fetchResponse({ image_width: 200, image_height: 200, mime_type: "image/png" }));
  }
  if (url === "/api/session/new.png") {
    calls.push({ type: "GET_SESSION", url });
    return Promise.resolve(fetchResponse(sessionPayload("new.png", ["new-r0"])));
  }
  throw new Error(`unexpected fetch: ${url}`);
};

require("./src/nova_parser/regional_ocr/static/app.js");

const tick = () => new Promise((resolve) => setImmediate(resolve));

(async () => {
  const app = window.regionalOcrApp();
  app.currentImage = { name: "old.png", width: 100, height: 100, mime: "image/png" };
  app.session = sessionPayload("old.png", ["old-v2-r0"]);
  app.saveVersion = 1;
  app.saveTimer = setTimeout(() => {}, 60_000);

  const selecting = app.selectImage("new.png");
  await tick();

  assert.deepEqual(
    calls.map((call) => call.type),
    ["PUT"],
    "initial pending debounce should be flushed before image switch",
  );
  assert.deepEqual(
    calls[0].body.regions.map((region) => region.rectangle.rect_id),
    ["old-v2-r0"],
  );

  app.session = sessionPayload("old.png", ["old-v3-r0", "old-v3-r1", "old-v3-r2"]);
  app.scheduleSave();
  assert.equal(app.saveTimer !== null, true, "scheduleSave should leave a pending debounce while v2 PUT is in-flight");

  putResolvers.shift()();
  await tick();

  assert.deepEqual(
    app.session.regions.map((region) => region.rectangle.rect_id),
    ["old-v3-r0", "old-v3-r1", "old-v3-r2"],
    "stale v2 response must not roll back live v3 edits",
  );
  assert.deepEqual(
    calls.map((call) => call.type),
    ["PUT", "PUT"],
    "selectImage should drain the save scheduled while the previous flush was in-flight",
  );
  assert.deepEqual(
    calls[1].body.regions.map((region) => region.rectangle.rect_id),
    ["old-v3-r0", "old-v3-r1", "old-v3-r2"],
  );

  putResolvers.shift()();
  await selecting;

  assert.deepEqual(
    calls.map((call) => call.type),
    ["PUT", "PUT", "GET_META", "GET_SESSION"],
  );
  assert.equal(app.currentImage.name, "new.png");
  assert.equal(app.session.image_name, "new.png");
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
""",
    )


# ---------------------------------------------------------------------------
# 共通ヘルパ（以下、純粋関数 / 状態遷移 / SSE / autosave 追加カバレッジ）
# ---------------------------------------------------------------------------

_PRELUDE = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

global.window = {};
const queryStubs = Object.create(null);
global.document = {
  querySelector(selector) {
    const stub = queryStubs[selector];
    if (typeof stub === "function") return stub();
    return stub === undefined ? null : stub;
  },
};
function setQueryStub(selector, value) {
  queryStubs[selector] = value;
}
function setupCanvas({ wrapRect = null, imgRect = null } = {}) {
  const fakeImg = imgRect ? { getBoundingClientRect: () => imgRect } : null;
  const fakeWrap = wrapRect
    ? {
        getBoundingClientRect: () => wrapRect,
        querySelector: (sel) => (sel === "img" ? fakeImg : null),
      }
    : null;
  setQueryStub(".canvas-wrap", fakeWrap);
  setQueryStub(".canvas-wrap img", fakeImg);
}

function sessionPayload(imageName, rectIds) {
  return {
    image_name: imageName,
    image_width: 100,
    image_height: 100,
    schema_version: 1,
    regions: rectIds.map((rectId, idx) => ({
      rectangle: {
        rect_id: rectId,
        draw_order: idx,
        x: idx * 10,
        y: idx * 10,
        width: 30,
        height: 30,
      },
      text: null,
      ocr_status: "pending",
      ocr_error: null,
      ocr_completed_at: null,
    })),
  };
}

function fetchResponse(payload, { ok = true, status = 200 } = {}) {
  return { ok, status, json: async () => payload };
}

const tick = () => new Promise((resolve) => setImmediate(resolve));

// app.js を CommonJS の require ではなく Function constructor 経由で評価する。
// production の app.js にテスト専用のエクスポートを残さないために、
// 内部関数（clampInt 等）は body 末尾に注入する return 文で取り出す。
const __APP_SOURCE = fs.readFileSync(
  path.resolve("./src/nova_parser/regional_ocr/static/app.js"),
  "utf-8",
);
const __APP_FACTORY = new Function(
  "window",
  __APP_SOURCE +
    "\n;return { clampInt, displayToNatural, generateRectId, nextDrawOrder, regionalOcrApp };",
);
const { clampInt, displayToNatural, generateRectId, nextDrawOrder, regionalOcrApp } =
  __APP_FACTORY(global.window);
const internals = { clampInt, displayToNatural, generateRectId, nextDrawOrder };

function newApp(overrides = {}) {
  const app = regionalOcrApp();
  Object.assign(app, overrides);
  return app;
}

function dropAutosaveTimer(app) {
  if (app.saveTimer) {
    clearTimeout(app.saveTimer);
    app.saveTimer = null;
  }
}
"""


def _run_node_inline(body: str) -> None:
    """共通 prelude を差し込んでテスト本体 JS を実行する。"""
    _run_node(_PRELUDE + "\n" + body)


# ---------------------------------------------------------------------------
# 3.1 純粋関数（__regionalInternals）
# ---------------------------------------------------------------------------


def test_clamp_int_rounds_and_bounds_within_min_max() -> None:
    _run_node_inline(
        r"""
assert.equal(internals.clampInt(3.4, 0, 10), 3);
assert.equal(internals.clampInt(3.6, 0, 10), 4);
assert.equal(internals.clampInt(-5, 0, 10), 0);
assert.equal(internals.clampInt(99, 0, 10), 10);
assert.equal(internals.clampInt(0, 0, 10), 0);
assert.equal(internals.clampInt(10, 0, 10), 10);
"""
    )


def test_display_to_natural_floors_x_y_at_zero_and_clamps_to_natural_minus_one() -> None:
    _run_node_inline(
        r"""
const r = internals.displayToNatural({ x: -10, y: -10, width: 20, height: 20 }, 1, 1, 100, 100);
assert.equal(r.x, 0);
assert.equal(r.y, 0);
assert.equal(r.width, 20);
assert.equal(r.height, 20);

const tiny = internals.displayToNatural({ x: 0, y: 0, width: 0.2, height: 0.2 }, 1, 1, 100, 100);
assert.equal(tiny.width, 1, "width must be at least 1");
assert.equal(tiny.height, 1, "height must be at least 1");
"""
    )


def test_display_to_natural_clamps_width_height_to_remaining_canvas() -> None:
    _run_node_inline(
        r"""
const r = internals.displayToNatural({ x: 95, y: 95, width: 50, height: 50 }, 1, 1, 100, 100);
assert.equal(r.x, 95);
assert.equal(r.y, 95);
assert.equal(r.width, 5, "width must clamp to naturalW - x");
assert.equal(r.height, 5, "height must clamp to naturalH - y");
"""
    )


def test_display_to_natural_applies_scale_before_clamp() -> None:
    _run_node_inline(
        r"""
const r = internals.displayToNatural({ x: 20, y: 40, width: 40, height: 80 }, 2, 4, 100, 100);
assert.deepEqual(r, { x: 10, y: 10, width: 20, height: 20 });
"""
    )


def test_generate_rect_id_returns_two_segment_string_and_does_not_collide() -> None:
    _run_node_inline(
        r"""
const a = internals.generateRectId();
const b = internals.generateRectId();
assert.match(a, /^[A-Za-z0-9]+-[a-z0-9]+$/, `unexpected shape: ${a}`);
assert.notEqual(a, b, "consecutive ids should not collide");
"""
    )


def test_next_draw_order_is_zero_for_empty_and_max_plus_one_otherwise() -> None:
    _run_node_inline(
        r"""
assert.equal(internals.nextDrawOrder([]), 0);
assert.equal(
  internals.nextDrawOrder([
    { rectangle: { draw_order: 0 } },
    { rectangle: { draw_order: 3 } },
    { rectangle: { draw_order: 1 } },
  ]),
  4,
);
"""
    )


# ---------------------------------------------------------------------------
# 3.2 ズーム
# ---------------------------------------------------------------------------


def test_zoom_in_grows_zoom_by_step_disables_fit_and_clamps_at_max() -> None:
    _run_node_inline(
        r"""
const app = newApp({
  currentImage: { name: "x.png", width: 100, height: 100, mime: "image/png" },
  scaleX: 1,
  scaleY: 1,
  zoomFit: true,
  zoom: 1.0,
});
app.zoomIn();
assert.equal(app.zoomFit, false);
assert.ok(Math.abs(app.zoom - 1.25) < 1e-9, `zoom should be 1.25 but was ${app.zoom}`);

app.zoom = 8.0;
app.zoomIn();
assert.equal(app.zoom, 8.0, "zoom must clamp at ZOOM_MAX=8.0");
"""
    )


def test_zoom_out_shrinks_by_step_and_clamps_at_min() -> None:
    _run_node_inline(
        r"""
const app = newApp({
  currentImage: { name: "x.png", width: 100, height: 100, mime: "image/png" },
  scaleX: 1,
  scaleY: 1,
  zoomFit: false,
  zoom: 1.0,
});
app.zoomOut();
assert.ok(Math.abs(app.zoom - 0.8) < 1e-9, `zoom should be 0.8 but was ${app.zoom}`);

app.zoom = 0.25;
app.zoomOut();
assert.equal(app.zoom, 0.25, "zoom must clamp at ZOOM_MIN=0.25");
"""
    )


def test_zoom_fit_toggle_resets_zoom_to_one_and_sets_zoom_fit_true() -> None:
    _run_node_inline(
        r"""
const app = newApp({ zoomFit: false, zoom: 2.5, scaleX: 1, scaleY: 1 });
app.zoomFitToggle();
assert.equal(app.zoomFit, true);
assert.equal(app.zoom, 1.0);
"""
    )


def test_zoom_reset_sets_explicit_zoom_to_one_and_disables_fit() -> None:
    _run_node_inline(
        r"""
const app = newApp({ zoomFit: true, zoom: 2.5, scaleX: 1, scaleY: 1 });
app.zoomReset();
assert.equal(app.zoomFit, false);
assert.equal(app.zoom, 1.0);
"""
    )


def test_zoom_percent_returns_rounded_percent_of_active_scale() -> None:
    _run_node_inline(
        r"""
const app = newApp({ zoomFit: true, scaleX: 0.487, zoom: 1.0 });
assert.equal(app.zoomPercent(), 49, "fit mode reports scaleX-based percent");

app.zoomFit = false;
app.zoom = 1.25;
assert.equal(app.zoomPercent(), 125, "explicit mode reports zoom percent");
"""
    )


def test_zoom_methods_are_no_op_while_drag_mode_active() -> None:
    _run_node_inline(
        r"""
const app = newApp({
  currentImage: { name: "x.png", width: 100, height: 100, mime: "image/png" },
  scaleX: 1,
  scaleY: 1,
  zoomFit: false,
  zoom: 1.0,
  dragMode: "create",
});
app.zoomIn();
app.zoomOut();
app.zoomFitToggle();
app.zoomReset();
assert.equal(app.zoom, 1.0, "zoom must stay put during drag");
assert.equal(app.zoomFit, false, "zoomFit must stay put during drag");
"""
    )


def test_img_style_returns_empty_when_fit_and_explicit_width_otherwise() -> None:
    _run_node_inline(
        r"""
const app = newApp({
  currentImage: { name: "x.png", width: 800, height: 600, mime: "image/png" },
  zoomFit: true,
  zoom: 1.0,
});
assert.deepEqual(app.imgStyle(), {}, "fit mode yields no inline style");

app.zoomFit = false;
app.zoom = 1.5;
assert.deepEqual(app.imgStyle(), { width: "1200px", maxWidth: "none" });
"""
    )


# ---------------------------------------------------------------------------
# 3.3 マウス・ドラフト作成
# ---------------------------------------------------------------------------


def test_on_mouse_down_starts_create_when_target_is_canvas_not_handle() -> None:
    _run_node_inline(
        r"""
setupCanvas({
  imgRect: { left: 10, top: 20, width: 200, height: 200 },
  wrapRect: { left: 10, top: 20, width: 200, height: 200 },
});
const app = newApp({
  session: sessionPayload("a.png", ["r0"]),
  currentImage: { name: "a.png", width: 100, height: 100 },
  imgLoaded: true,
  selectedRectId: "r0",
});
app.onMouseDown({
  target: { classList: { contains: () => false } },
  clientX: 50,
  clientY: 60,
});
assert.equal(app.dragMode, "create");
assert.deepEqual(app.dragStart, { x: 40, y: 40 });
assert.deepEqual(app.draftRect, { x: 40, y: 40, width: 0, height: 0 });
assert.equal(app.selectedRectId, null, "starting a new draft clears selection");
"""
    )


def test_on_mouse_down_is_no_op_on_handle_region_or_region_delete() -> None:
    _run_node_inline(
        r"""
setupCanvas({
  imgRect: { left: 0, top: 0, width: 200, height: 200 },
  wrapRect: { left: 0, top: 0, width: 200, height: 200 },
});
for (const cls of ["handle", "region", "region-delete"]) {
  const app = newApp({
    session: sessionPayload("a.png", ["r0"]),
    currentImage: { name: "a.png", width: 100, height: 100 },
    imgLoaded: true,
  });
  app.onMouseDown({
    target: { classList: { contains: (c) => c === cls } },
    clientX: 50,
    clientY: 60,
  });
  assert.equal(app.dragMode, null, `${cls} click must not start drag`);
  assert.equal(app.draftRect, null);
}
"""
    )


def test_on_mouse_down_is_no_op_until_session_and_img_loaded() -> None:
    _run_node_inline(
        r"""
const noTarget = { target: { classList: { contains: () => false } }, clientX: 0, clientY: 0 };

const noSession = newApp({ session: null, imgLoaded: true });
noSession.onMouseDown(noTarget);
assert.equal(noSession.dragMode, null);

const notLoaded = newApp({ session: sessionPayload("a.png", []), imgLoaded: false });
notLoaded.onMouseDown(noTarget);
assert.equal(notLoaded.dragMode, null);
"""
    )


def test_on_mouse_move_grows_draft_rect_to_absolute_size_in_both_directions() -> None:
    _run_node_inline(
        r"""
setupCanvas({
  imgRect: { left: 0, top: 0, width: 200, height: 200 },
  wrapRect: { left: 0, top: 0, width: 200, height: 200 },
});
const app = newApp({
  session: sessionPayload("a.png", []),
  currentImage: { name: "a.png", width: 100, height: 100 },
  imgLoaded: true,
  dragMode: "create",
  dragStart: { x: 50, y: 50 },
  draftRect: { x: 50, y: 50, width: 0, height: 0 },
});
app.onMouseMove({ clientX: 80, clientY: 90 });
assert.deepEqual(app.draftRect, { x: 50, y: 50, width: 30, height: 40 });

app.onMouseMove({ clientX: 20, clientY: 10 });
assert.deepEqual(app.draftRect, { x: 20, y: 10, width: 30, height: 40 }, "negative direction normalizes");
"""
    )


def test_on_mouse_up_adds_region_when_draft_passes_min_drag_px() -> None:
    _run_node_inline(
        r"""
const app = newApp({
  session: sessionPayload("a.png", []),
  currentImage: { name: "a.png", width: 100, height: 100 },
  imgLoaded: true,
  dragMode: "create",
  draftRect: { x: 10, y: 10, width: 20, height: 30 },
  scaleX: 1,
  scaleY: 1,
});
app.onMouseUp();
assert.equal(app.session.regions.length, 1);
const rect = app.session.regions[0].rectangle;
assert.equal(rect.x, 10);
assert.equal(rect.width, 20);
assert.equal(rect.draw_order, 0);
assert.equal(app.selectedRectId, rect.rect_id);
assert.equal(app.dragMode, null);
assert.equal(app.draftRect, null);
dropAutosaveTimer(app);
"""
    )


def test_on_mouse_up_discards_draft_below_min_drag_px() -> None:
    _run_node_inline(
        r"""
const app = newApp({
  session: sessionPayload("a.png", []),
  currentImage: { name: "a.png", width: 100, height: 100 },
  imgLoaded: true,
  dragMode: "create",
  draftRect: { x: 10, y: 10, width: 4, height: 4 },
  scaleX: 1,
  scaleY: 1,
});
app.onMouseUp();
assert.equal(app.session.regions.length, 0, "tiny draft must be discarded");
assert.equal(app.draftRect, null);
assert.equal(app.dragMode, null);
"""
    )


def test_add_region_from_draft_uses_display_to_natural_and_assigns_next_draw_order() -> None:
    _run_node_inline(
        r"""
const app = newApp({
  session: sessionPayload("a.png", ["existing"]),
  currentImage: { name: "a.png", width: 100, height: 100 },
  imgLoaded: true,
  draftRect: { x: 20, y: 40, width: 40, height: 80 },
  scaleX: 2,
  scaleY: 4,
});
app._addRegionFromDraft();
const rect = app.session.regions[1].rectangle;
assert.deepEqual(
  { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
  { x: 10, y: 10, width: 20, height: 20 },
  "scale must be applied",
);
assert.equal(rect.draw_order, 1, "draw_order increments");
assert.equal(app.session.regions[1].ocr_status, "pending");
assert.equal(app.savingState, "saving", "scheduleSave must mark saving");
dropAutosaveTimer(app);
"""
    )


# ---------------------------------------------------------------------------
# 3.4 select / delete
# ---------------------------------------------------------------------------


def test_select_rect_updates_selected_id() -> None:
    _run_node_inline(
        r"""
const app = newApp({ selectedRectId: null });
app.selectRect("abc");
assert.equal(app.selectedRectId, "abc");
"""
    )


def test_delete_rect_removes_from_regions_and_clears_selection_when_selected() -> None:
    _run_node_inline(
        r"""
const app = newApp({
  session: sessionPayload("a.png", ["r0", "r1"]),
  currentImage: { name: "a.png", width: 100, height: 100 },
  selectedRectId: "r0",
});
app.deleteRect("r0");
assert.deepEqual(
  app.session.regions.map((r) => r.rectangle.rect_id),
  ["r1"],
);
assert.equal(app.selectedRectId, null);
dropAutosaveTimer(app);
"""
    )


def test_delete_rect_keeps_selection_when_different_rect_id() -> None:
    _run_node_inline(
        r"""
const app = newApp({
  session: sessionPayload("a.png", ["r0", "r1"]),
  currentImage: { name: "a.png", width: 100, height: 100 },
  selectedRectId: "r1",
});
app.deleteRect("r0");
assert.deepEqual(
  app.session.regions.map((r) => r.rectangle.rect_id),
  ["r1"],
);
assert.equal(app.selectedRectId, "r1");
dropAutosaveTimer(app);
"""
    )


# ---------------------------------------------------------------------------
# 3.5 リサイズ
# ---------------------------------------------------------------------------


def test_start_resize_records_edge_and_snapshots_original_rectangle() -> None:
    _run_node_inline(
        r"""
const session = sessionPayload("a.png", ["r0"]);
session.regions[0].rectangle = { rect_id: "r0", draw_order: 0, x: 10, y: 20, width: 30, height: 40 };
const app = newApp({ session, currentImage: { name: "a.png", width: 100, height: 100 } });
app.startResize({ clientX: 100, clientY: 200 }, "r0", "se");
assert.equal(app.dragMode, "resize");
assert.equal(app.selectedRectId, "r0");
assert.equal(app.dragStart.edge, "se");
assert.deepEqual(app.dragStart.original, { rect_id: "r0", draw_order: 0, x: 10, y: 20, width: 30, height: 40 });
assert.equal(app.dragStart.clientX, 100);
assert.equal(app.dragStart.clientY, 200);
"""
    )


def test_apply_resize_grows_east_and_clamps_to_image_width() -> None:
    _run_node_inline(
        r"""
const session = sessionPayload("a.png", ["r0"]);
session.regions[0].rectangle = { rect_id: "r0", draw_order: 0, x: 80, y: 10, width: 10, height: 10 };
const app = newApp({
  session,
  currentImage: { name: "a.png", width: 100, height: 100 },
  scaleX: 1,
  scaleY: 1,
  selectedRectId: "r0",
  dragMode: "resize",
  dragStart: { clientX: 0, clientY: 0, edge: "e", original: { ...session.regions[0].rectangle } },
});
app._applyResize({ clientX: 200, clientY: 0 });
const rect = app.session.regions[0].rectangle;
assert.equal(rect.x, 80);
assert.equal(rect.width, 20, "width must clamp to image right edge (maxW - x = 20)");
dropAutosaveTimer(app);
"""
    )


def test_apply_resize_grows_south_and_clamps_to_image_height() -> None:
    _run_node_inline(
        r"""
const session = sessionPayload("a.png", ["r0"]);
session.regions[0].rectangle = { rect_id: "r0", draw_order: 0, x: 10, y: 80, width: 10, height: 10 };
const app = newApp({
  session,
  currentImage: { name: "a.png", width: 100, height: 100 },
  scaleX: 1,
  scaleY: 1,
  selectedRectId: "r0",
  dragMode: "resize",
  dragStart: { clientX: 0, clientY: 0, edge: "s", original: { ...session.regions[0].rectangle } },
});
app._applyResize({ clientX: 0, clientY: 200 });
const rect = app.session.regions[0].rectangle;
assert.equal(rect.height, 20, "height must clamp to image bottom edge");
dropAutosaveTimer(app);
"""
    )


def test_apply_resize_shrinks_west_anchors_left_edge_at_minimum_1px_width() -> None:
    _run_node_inline(
        r"""
const session = sessionPayload("a.png", ["r0"]);
session.regions[0].rectangle = { rect_id: "r0", draw_order: 0, x: 10, y: 10, width: 30, height: 30 };
const app = newApp({
  session,
  currentImage: { name: "a.png", width: 100, height: 100 },
  scaleX: 1,
  scaleY: 1,
  selectedRectId: "r0",
  dragMode: "resize",
  dragStart: { clientX: 0, clientY: 0, edge: "w", original: { ...session.regions[0].rectangle } },
});
app._applyResize({ clientX: 1000, clientY: 0 });
const rect = app.session.regions[0].rectangle;
assert.equal(rect.width, 1, "width must clamp to minimum 1px");
assert.equal(rect.x, 39, "left edge must anchor at original.x + original.width - 1");
dropAutosaveTimer(app);
"""
    )


def test_apply_resize_shrinks_north_anchors_top_edge_at_minimum_1px_height() -> None:
    _run_node_inline(
        r"""
const session = sessionPayload("a.png", ["r0"]);
session.regions[0].rectangle = { rect_id: "r0", draw_order: 0, x: 10, y: 10, width: 30, height: 30 };
const app = newApp({
  session,
  currentImage: { name: "a.png", width: 100, height: 100 },
  scaleX: 1,
  scaleY: 1,
  selectedRectId: "r0",
  dragMode: "resize",
  dragStart: { clientX: 0, clientY: 0, edge: "n", original: { ...session.regions[0].rectangle } },
});
app._applyResize({ clientX: 0, clientY: 1000 });
const rect = app.session.regions[0].rectangle;
assert.equal(rect.height, 1, "height must clamp to minimum 1px");
assert.equal(rect.y, 39, "top edge must anchor at original.y + original.height - 1");
dropAutosaveTimer(app);
"""
    )


def test_apply_resize_diagonal_se_updates_width_and_height() -> None:
    _run_node_inline(
        r"""
const session = sessionPayload("a.png", ["r0"]);
session.regions[0].rectangle = { rect_id: "r0", draw_order: 0, x: 10, y: 10, width: 20, height: 20 };
const app = newApp({
  session,
  currentImage: { name: "a.png", width: 100, height: 100 },
  scaleX: 2,
  scaleY: 4,
  selectedRectId: "r0",
  dragMode: "resize",
  dragStart: { clientX: 0, clientY: 0, edge: "se", original: { ...session.regions[0].rectangle } },
});
app._applyResize({ clientX: 20, clientY: 40 });
const rect = app.session.regions[0].rectangle;
assert.equal(rect.width, 30, "width = 20 + 20/scaleX(2) = 30");
assert.equal(rect.height, 30, "height = 20 + 40/scaleY(4) = 30");
dropAutosaveTimer(app);
"""
    )


def test_apply_resize_schedules_save_after_step() -> None:
    _run_node_inline(
        r"""
const session = sessionPayload("a.png", ["r0"]);
session.regions[0].rectangle = { rect_id: "r0", draw_order: 0, x: 10, y: 10, width: 20, height: 20 };
const app = newApp({
  session,
  currentImage: { name: "a.png", width: 100, height: 100 },
  scaleX: 1,
  scaleY: 1,
  selectedRectId: "r0",
  dragMode: "resize",
  dragStart: { clientX: 0, clientY: 0, edge: "e", original: { ...session.regions[0].rectangle } },
});
assert.equal(app.savingState, "idle");
app._applyResize({ clientX: 5, clientY: 0 });
assert.equal(app.savingState, "saving");
assert.notEqual(app.saveTimer, null);
dropAutosaveTimer(app);
"""
    )


# ---------------------------------------------------------------------------
# 3.6 scale / style
# ---------------------------------------------------------------------------


def test_recompute_scale_is_no_op_without_current_image_or_image_element() -> None:
    _run_node_inline(
        r"""
setupCanvas({ imgRect: { width: 0, height: 0 } });
const app = newApp({ currentImage: null, scaleX: 5, scaleY: 5 });
app.recomputeScale();
assert.equal(app.scaleX, 5, "without currentImage scale must not change");

setupCanvas({});
const app2 = newApp({
  currentImage: { name: "a.png", width: 100, height: 100 },
  scaleX: 5,
  scaleY: 5,
});
app2.recomputeScale();
assert.equal(app2.scaleX, 5, "without image element scale must not change");
"""
    )


def test_recompute_scale_divides_display_rect_by_natural_size() -> None:
    _run_node_inline(
        r"""
const fakeImg = { getBoundingClientRect: () => ({ width: 400, height: 300 }) };
const app = newApp({
  currentImage: { name: "a.png", width: 200, height: 100 },
  scaleX: 0,
  scaleY: 0,
});
app.recomputeScale(fakeImg);
assert.equal(app.scaleX, 2);
assert.equal(app.scaleY, 3);
"""
    )


def test_region_style_uses_scale_for_left_top_width_height_px() -> None:
    _run_node_inline(
        r"""
const app = newApp({ scaleX: 2, scaleY: 3 });
const style = app.regionStyle({ x: 10, y: 20, width: 30, height: 40 });
assert.deepEqual(style, { left: "20px", top: "60px", width: "60px", height: "120px" });
"""
    )


# ---------------------------------------------------------------------------
# 3.7 autosave 補強
# ---------------------------------------------------------------------------


def test_perform_save_skips_state_update_when_current_image_changed_mid_flight() -> None:
    _run_node_inline(
        r"""
global.fetch = () => Promise.resolve(fetchResponse(sessionPayload("a.png", ["server-r0"])));
const app = newApp({
  currentImage: { name: "b.png", width: 100, height: 100 },
  session: sessionPayload("b.png", ["b-r0"]),
  saveVersion: 1,
});
(async () => {
  const result = await app._performSave("a.png", sessionPayload("a.png", ["client-r0"]), 1);
  assert.equal(result.ok, true);
  assert.equal(app.session.image_name, "b.png", "live state must not be overwritten by stale image response");
  assert.deepEqual(app.session.regions.map((r) => r.rectangle.rect_id), ["b-r0"]);
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_perform_save_skips_state_update_when_save_version_is_outdated() -> None:
    _run_node_inline(
        r"""
global.fetch = () => Promise.resolve(fetchResponse(sessionPayload("a.png", ["server-r0"])));
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100 },
  session: sessionPayload("a.png", ["v2-r0"]),
  saveVersion: 2,
  savingState: "saving",
});
(async () => {
  await app._performSave("a.png", sessionPayload("a.png", ["v1-r0"]), 1);
  assert.deepEqual(
    app.session.regions.map((r) => r.rectangle.rect_id),
    ["v2-r0"],
    "outdated version must not roll back live state",
  );
  assert.equal(app.savingState, "saving", "outdated save success must not flip savingState to idle");
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_saving_state_transitions_idle_saving_idle_on_success() -> None:
    _run_node_inline(
        r"""
let resolvePut;
global.fetch = (url, options) => {
  if (options && options.method === "PUT") {
    return new Promise((resolve) => {
      resolvePut = () => resolve(fetchResponse(JSON.parse(options.body)));
    });
  }
  throw new Error("unexpected fetch " + url);
};
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100 },
  session: sessionPayload("a.png", ["r0"]),
});
assert.equal(app.savingState, "idle");
app.scheduleSave();
assert.equal(app.savingState, "saving");
clearTimeout(app.saveTimer);
app.saveTimer = null;
const promise = app._launchSave("a.png", sessionPayload("a.png", ["r0"]), app.saveVersion);
(async () => {
  await tick();
  resolvePut();
  await promise;
  assert.equal(app.savingState, "idle", "successful PUT must restore idle");
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_saving_state_becomes_error_on_failed_put_for_latest_version() -> None:
    _run_node_inline(
        r"""
global.fetch = () => Promise.resolve({ ok: false, status: 500, json: async () => ({}) });
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100 },
  session: sessionPayload("a.png", ["r0"]),
  saveVersion: 1,
  warnings: [],
});
console.error = () => {};
(async () => {
  const result = await app._performSave("a.png", sessionPayload("a.png", ["r0"]), 1);
  assert.equal(result.ok, false);
  assert.equal(app.savingState, "error");
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_report_save_failure_appends_to_warnings_with_image_name_and_message() -> None:
    _run_node_inline(
        r"""
const app = newApp({ warnings: ["pre"] });
app._reportSaveFailure("img.png", new Error("boom"));
assert.equal(app.warnings.length, 2);
assert.equal(app.warnings[0], "pre");
assert.match(app.warnings[1], /img\.png/);
assert.match(app.warnings[1], /boom/);
"""
    )


def test_schedule_save_is_no_op_without_session_or_current_image() -> None:
    _run_node_inline(
        r"""
const noSession = newApp({ session: null, currentImage: { name: "a.png" } });
noSession.scheduleSave();
assert.equal(noSession.saveTimer, null);
assert.equal(noSession.savingState, "idle");

const noImage = newApp({ session: sessionPayload("a.png", []), currentImage: null });
noImage.scheduleSave();
assert.equal(noImage.saveTimer, null);
assert.equal(noImage.savingState, "idle");
"""
    )


# ---------------------------------------------------------------------------
# 3.8 単発 OCR
# ---------------------------------------------------------------------------


def test_run_single_ocr_replaces_region_with_response_payload() -> None:
    _run_node_inline(
        r"""
const updated = {
  rectangle: { rect_id: "r0", draw_order: 0, x: 10, y: 10, width: 20, height: 20 },
  text: "HELLO",
  ocr_status: "done",
  ocr_error: null,
  ocr_completed_at: "2026-01-01T00:00:00Z",
};
global.fetch = (url, options) => {
  assert.equal(options.method, "POST");
  assert.match(url, /\/api\/ocr\/a\.png\/r0$/);
  return Promise.resolve(fetchResponse(updated));
};
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100 },
  session: sessionPayload("a.png", ["r0"]),
});
(async () => {
  await app.runSingleOcr("r0");
  assert.equal(app.session.regions[0].text, "HELLO");
  assert.equal(app.session.regions[0].ocr_status, "done");
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_run_single_ocr_swallows_error_and_keeps_session_intact() -> None:
    _run_node_inline(
        r"""
global.fetch = () => Promise.resolve({ ok: false, status: 500, json: async () => ({}) });
console.error = () => {};
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100 },
  session: sessionPayload("a.png", ["r0"]),
});
(async () => {
  await app.runSingleOcr("r0");
  assert.equal(app.session.regions[0].ocr_status, "pending", "session must remain untouched on failure");
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


# ---------------------------------------------------------------------------
# 3.9 バッチ OCR（SSE）
# ---------------------------------------------------------------------------


def test_run_batch_ocr_parses_sse_chunks_and_applies_each_item() -> None:
    _run_node_inline(
        r"""
const items = [
  { image_name: "a.png", rect_id: "r0", status: "done", text: "AAA", error: null },
  { image_name: "a.png", rect_id: "r1", status: "done", text: "BBB", error: null },
];
const chunks = [
  Buffer.from(`data: ${JSON.stringify(items[0])}\n\n`),
  Buffer.from(`data: ${JSON.stringify(items[1])}\n\n`),
];
let idx = 0;
const body = {
  getReader() {
    return {
      read: () => {
        if (idx < chunks.length) {
          const value = chunks[idx++];
          return Promise.resolve({ value, done: false });
        }
        return Promise.resolve({ value: undefined, done: true });
      },
      releaseLock() {},
    };
  },
};
global.fetch = () => Promise.resolve({ ok: true, status: 200, body });
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100 },
  session: sessionPayload("a.png", ["r0", "r1"]),
});
(async () => {
  await app.runBatchOcr();
  assert.equal(app.session.regions[0].text, "AAA");
  assert.equal(app.session.regions[0].ocr_status, "done");
  assert.equal(app.session.regions[1].text, "BBB");
  assert.equal(app.batchRunning, false);
  assert.equal(app.sseController, null);
  assert.equal(app.ocrLog.length, 2);
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_run_batch_ocr_handles_split_chunk_boundary() -> None:
    _run_node_inline(
        r"""
const item = { image_name: "a.png", rect_id: "r0", status: "done", text: "OK", error: null };
const full = `data: ${JSON.stringify(item)}\n\n`;
const half = Math.floor(full.length / 2);
const chunks = [Buffer.from(full.slice(0, half)), Buffer.from(full.slice(half))];
let idx = 0;
const body = {
  getReader() {
    return {
      read: () => {
        if (idx < chunks.length) {
          return Promise.resolve({ value: chunks[idx++], done: false });
        }
        return Promise.resolve({ value: undefined, done: true });
      },
      releaseLock() {},
    };
  },
};
global.fetch = () => Promise.resolve({ ok: true, status: 200, body });
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100 },
  session: sessionPayload("a.png", ["r0"]),
});
(async () => {
  await app.runBatchOcr();
  assert.equal(app.session.regions[0].text, "OK", "split SSE chunks must reassemble");
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_run_batch_ocr_continues_after_invalid_json_chunk() -> None:
    _run_node_inline(
        r"""
const ok = { image_name: "a.png", rect_id: "r0", status: "done", text: "OK", error: null };
const chunks = [
  Buffer.from(`data: {not json}\n\n`),
  Buffer.from(`data: ${JSON.stringify(ok)}\n\n`),
];
let idx = 0;
const body = {
  getReader() {
    return {
      read: () => {
        if (idx < chunks.length) {
          return Promise.resolve({ value: chunks[idx++], done: false });
        }
        return Promise.resolve({ value: undefined, done: true });
      },
      releaseLock() {},
    };
  },
};
global.fetch = () => Promise.resolve({ ok: true, status: 200, body });
let warnCalls = 0;
console.warn = () => { warnCalls += 1; };
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100 },
  session: sessionPayload("a.png", ["r0"]),
});
(async () => {
  await app.runBatchOcr();
  assert.equal(warnCalls, 1, "exactly one parse warning");
  assert.equal(app.session.regions[0].text, "OK", "later valid item must still apply");
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_run_batch_ocr_is_no_op_when_already_running() -> None:
    _run_node_inline(
        r"""
let calls = 0;
global.fetch = () => {
  calls += 1;
  return new Promise(() => {});
};
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100 },
  session: sessionPayload("a.png", ["r0"]),
  batchRunning: true,
});
(async () => {
  await app.runBatchOcr();
  assert.equal(calls, 0, "second runBatchOcr while running must not fire fetch");
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_cancel_batch_aborts_in_flight_controller() -> None:
    _run_node_inline(
        r"""
const controller = new AbortController();
const app = newApp({ sseController: controller, batchRunning: true });
app.cancelBatch();
assert.equal(controller.signal.aborted, true);
assert.equal(app.sseController, null);
"""
    )


# ---------------------------------------------------------------------------
# 3.10 applyOcrItem
# ---------------------------------------------------------------------------


def test_apply_ocr_item_ignores_items_for_other_image_name() -> None:
    _run_node_inline(
        r"""
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100 },
  session: sessionPayload("a.png", ["r0"]),
});
app.applyOcrItem({ image_name: "other.png", rect_id: "r0", status: "done", text: "X" });
assert.equal(app.session.regions[0].text, null);
assert.equal(app.session.regions[0].ocr_status, "pending");
assert.equal(app.ocrLog.length, 1, "log still records the event");
"""
    )


def test_apply_ocr_item_updates_text_status_error_and_completed_at_for_matching_rect() -> None:
    _run_node_inline(
        r"""
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100 },
  session: sessionPayload("a.png", ["r0"]),
});
app.applyOcrItem({ image_name: "a.png", rect_id: "r0", status: "done", text: "HELLO", error: null });
const region = app.session.regions[0];
assert.equal(region.text, "HELLO");
assert.equal(region.ocr_status, "done");
assert.equal(region.ocr_error, null);
assert.match(region.ocr_completed_at, /^\d{4}-\d{2}-\d{2}T/);

app.applyOcrItem({ image_name: "a.png", rect_id: "r0", status: "error", text: null, error: "boom" });
assert.equal(app.session.regions[0].text, "HELLO", "null text must not overwrite existing text");
assert.equal(app.session.regions[0].ocr_status, "error");
assert.equal(app.session.regions[0].ocr_error, "boom");
"""
    )


def test_apply_ocr_item_pushes_to_ocr_log_and_trims_at_50_entries() -> None:
    _run_node_inline(
        r"""
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100 },
  session: sessionPayload("a.png", ["r0"]),
});
for (let i = 0; i < 55; i++) {
  app.applyOcrItem({ image_name: "a.png", rect_id: "r0", status: "done", text: `t${i}`, error: null, seq: i });
}
assert.equal(app.ocrLog.length, 50, "log must cap at 50");
assert.equal(app.ocrLog[0].seq, 5, "earliest entries are evicted FIFO");
assert.equal(app.ocrLog[49].seq, 54);
"""
    )

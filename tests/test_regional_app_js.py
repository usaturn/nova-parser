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
    "\n;return { clampInt, displayToNatural, generateRectId, nextDrawOrder, hitTestBlock, regionalOcrApp };",
);
const { clampInt, displayToNatural, generateRectId, nextDrawOrder, hitTestBlock, regionalOcrApp } =
  __APP_FACTORY(global.window);
const internals = { clampInt, displayToNatural, generateRectId, nextDrawOrder, hitTestBlock };

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


# ---------------------------------------------------------------------------
# 段組選択: hitTestBlock（純関数）
# ---------------------------------------------------------------------------


def test_hit_test_block_returns_containing_block_or_null() -> None:
    _run_node_inline(
        r"""
const blocks = [{ x: 10, y: 10, width: 30, height: 30 }];
assert.deepEqual(internals.hitTestBlock(blocks, 20, 20), blocks[0]);
assert.equal(internals.hitTestBlock(blocks, 5, 5), null, "外側の点は null");
assert.equal(internals.hitTestBlock([], 20, 20), null, "空配列は null");
"""
    )


def test_hit_test_block_boundary_is_half_open() -> None:
    _run_node_inline(
        r"""
const blocks = [{ x: 10, y: 10, width: 30, height: 30 }];
assert.deepEqual(internals.hitTestBlock(blocks, 10, 10), blocks[0], "左上端は含む");
assert.equal(internals.hitTestBlock(blocks, 40, 40), null, "右下端 (x+width, y+height) は含まない");
assert.deepEqual(internals.hitTestBlock(blocks, 39.9, 39.9), blocks[0]);
"""
    )


def test_hit_test_block_prefers_smallest_area_on_overlap() -> None:
    _run_node_inline(
        r"""
const outer = { x: 0, y: 0, width: 100, height: 100 };
const inner = { x: 20, y: 20, width: 30, height: 30 };
assert.deepEqual(internals.hitTestBlock([outer, inner], 25, 25), inner, "重なりは最小面積を採用");
assert.deepEqual(internals.hitTestBlock([inner, outer], 25, 25), inner, "順序に依存しない");
assert.deepEqual(internals.hitTestBlock([outer, inner], 5, 5), outer, "inner の外なら outer");
"""
    )


# ---------------------------------------------------------------------------
# 段組選択: blockMode の状態遷移・クリック作成・ホバー
# ---------------------------------------------------------------------------

_BLOCKS_PAYLOAD = r"""
function blocksPayload(imageName, blocks) {
  return {
    image_name: imageName,
    image_width: 100,
    image_height: 100,
    blocks,
    detected_at: "2026-07-18T00:00:00Z",
    schema_version: 1,
  };
}
"""


def test_toggle_block_mode_fetches_blocks_once_and_caches() -> None:
    _run_node_inline(
        _BLOCKS_PAYLOAD
        + r"""
let calls = 0;
global.fetch = (url) => {
  if (url === "/api/blocks/a.png") {
    calls += 1;
    return Promise.resolve(
      fetchResponse(blocksPayload("a.png", [{ x: 10, y: 10, width: 30, height: 30 }])),
    );
  }
  throw new Error(`unexpected fetch: ${url}`);
};
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100, mime: "image/png" },
  session: sessionPayload("a.png", []),
  imgLoaded: true,
});
(async () => {
  await app.toggleBlockMode();
  assert.equal(app.blockMode, true);
  assert.deepEqual(app.paragraphBlocks, [{ x: 10, y: 10, width: 30, height: 30 }]);
  assert.equal(calls, 1);

  await app.toggleBlockMode();
  assert.equal(app.blockMode, false, "再トグルで OFF");
  assert.equal(app.hoverBlock, null, "OFF でホバーはクリア");

  await app.toggleBlockMode();
  assert.equal(app.blockMode, true);
  assert.equal(calls, 1, "blocks はキャッシュされ再フェッチしない");
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_toggle_block_mode_appends_warning_and_stays_on_when_zero_blocks() -> None:
    _run_node_inline(
        _BLOCKS_PAYLOAD
        + r"""
global.fetch = () => Promise.resolve(fetchResponse(blocksPayload("a.png", [])));
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100, mime: "image/png" },
  session: sessionPayload("a.png", []),
  imgLoaded: true,
  warnings: [],
});
(async () => {
  await app.toggleBlockMode();
  assert.equal(app.blockMode, true, "0 件は成功扱いでモードは ON のまま");
  assert.deepEqual(app.paragraphBlocks, []);
  assert.equal(app.warnings.length, 1);
  assert.match(app.warnings[0], /テキストブロックが検出されませんでした/);
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_toggle_block_mode_reports_failure_and_turns_off() -> None:
    _run_node_inline(
        _BLOCKS_PAYLOAD
        + r"""
global.fetch = () => Promise.resolve({ ok: false, status: 502, json: async () => ({}) });
console.error = () => {};
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100, mime: "image/png" },
  session: sessionPayload("a.png", []),
  imgLoaded: true,
  warnings: [],
});
(async () => {
  await app.toggleBlockMode();
  assert.equal(app.blockMode, false, "検出失敗時はモードを OFF に戻す");
  assert.equal(app.paragraphBlocks, null);
  assert.equal(app.warnings.length, 1);
  assert.match(app.warnings[0], /テキストブロック検出に失敗/);
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_block_mode_click_creates_pending_region_from_smallest_block() -> None:
    _run_node_inline(
        _BLOCKS_PAYLOAD
        + r"""
setupCanvas({
  imgRect: { left: 0, top: 0, width: 200, height: 200 },
  wrapRect: { left: 0, top: 0, width: 200, height: 200 },
});
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100, mime: "image/png" },
  session: sessionPayload("a.png", ["existing"]),
  imgLoaded: true,
  scaleX: 2,
  scaleY: 2,
  blockMode: true,
  paragraphBlocks: [
    { x: 0, y: 0, width: 100, height: 100 },
    { x: 10, y: 10, width: 30, height: 30 },
  ],
});
app.onMouseDown({
  target: { classList: { contains: () => false } },
  clientX: 30,
  clientY: 30,
});
assert.equal(app.dragMode, null, "blockMode 中は draft ドラッグを開始しない");
assert.equal(app.session.regions.length, 2);
const region = app.session.regions[1];
assert.deepEqual(
  {
    x: region.rectangle.x,
    y: region.rectangle.y,
    width: region.rectangle.width,
    height: region.rectangle.height,
  },
  { x: 10, y: 10, width: 30, height: 30 },
  "display(30,30) → natural(15,15) を含む最小ブロックの矩形になる",
);
assert.equal(region.ocr_status, "pending");
assert.equal(region.rectangle.draw_order, 1);
assert.equal(app.selectedRectId, region.rectangle.rect_id);
assert.equal(app.savingState, "saving", "作成後は autosave がスケジュールされる");
dropAutosaveTimer(app);
"""
    )


def test_block_mode_click_outside_any_block_is_no_op() -> None:
    _run_node_inline(
        _BLOCKS_PAYLOAD
        + r"""
setupCanvas({
  imgRect: { left: 0, top: 0, width: 100, height: 100 },
  wrapRect: { left: 0, top: 0, width: 100, height: 100 },
});
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100, mime: "image/png" },
  session: sessionPayload("a.png", []),
  imgLoaded: true,
  scaleX: 1,
  scaleY: 1,
  blockMode: true,
  paragraphBlocks: [{ x: 50, y: 50, width: 20, height: 20 }],
});
app.onMouseDown({
  target: { classList: { contains: () => false } },
  clientX: 5,
  clientY: 5,
});
assert.equal(app.session.regions.length, 0, "ブロック外クリックでは矩形を作らない");
assert.equal(app.dragMode, null);
assert.equal(app.savingState, "idle");
"""
    )


def test_block_mode_mousemove_sets_and_clears_hover_block() -> None:
    _run_node_inline(
        _BLOCKS_PAYLOAD
        + r"""
setupCanvas({
  imgRect: { left: 0, top: 0, width: 100, height: 100 },
  wrapRect: { left: 0, top: 0, width: 100, height: 100 },
});
const block = { x: 10, y: 10, width: 30, height: 30 };
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100, mime: "image/png" },
  session: sessionPayload("a.png", []),
  imgLoaded: true,
  scaleX: 1,
  scaleY: 1,
  blockMode: true,
  paragraphBlocks: [block],
});
app.onMouseMove({ clientX: 20, clientY: 20 });
assert.deepEqual(app.hoverBlock, block, "ブロック上でホバーがセットされる");

app.onMouseMove({ clientX: 90, clientY: 90 });
assert.equal(app.hoverBlock, null, "ブロック外でホバーはクリアされる");
"""
    )


def test_select_image_resets_blocks_and_hover() -> None:
    _run_node_inline(
        _BLOCKS_PAYLOAD
        + r"""
global.fetch = (url, options = {}) => {
  if (url === "/api/image/new.png") {
    return Promise.resolve(fetchResponse({ image_width: 200, image_height: 200, mime_type: "image/png" }));
  }
  if (url === "/api/session/new.png") {
    return Promise.resolve(fetchResponse(sessionPayload("new.png", [])));
  }
  throw new Error(`unexpected fetch: ${url}`);
};
const app = newApp({
  currentImage: { name: "old.png", width: 100, height: 100, mime: "image/png" },
  session: sessionPayload("old.png", []),
  paragraphBlocks: [{ x: 1, y: 1, width: 2, height: 2 }],
  hoverBlock: { x: 1, y: 1, width: 2, height: 2 },
  blockMode: false,
});
(async () => {
  await app.selectImage("new.png");
  assert.equal(app.paragraphBlocks, null, "画像切替で blocks はリセット");
  assert.equal(app.hoverBlock, null, "画像切替で hoverBlock はリセット");
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_select_image_refetches_blocks_when_block_mode_stays_on() -> None:
    _run_node_inline(
        _BLOCKS_PAYLOAD
        + r"""
const fetches = [];
global.fetch = (url, options = {}) => {
  fetches.push(url);
  if (url === "/api/image/new.png") {
    return Promise.resolve(fetchResponse({ image_width: 200, image_height: 200, mime_type: "image/png" }));
  }
  if (url === "/api/session/new.png") {
    return Promise.resolve(fetchResponse(sessionPayload("new.png", [])));
  }
  if (url === "/api/blocks/new.png") {
    return Promise.resolve(fetchResponse(blocksPayload("new.png", [{ x: 5, y: 5, width: 10, height: 10 }])));
  }
  throw new Error(`unexpected fetch: ${url}`);
};
const app = newApp({
  currentImage: { name: "old.png", width: 100, height: 100, mime: "image/png" },
  session: sessionPayload("old.png", []),
  paragraphBlocks: [{ x: 1, y: 1, width: 2, height: 2 }],
  blockMode: true,
});
(async () => {
  await app.selectImage("new.png");
  await tick();
  assert.ok(fetches.includes("/api/blocks/new.png"), "モード ON のまま画像切替すると新画像の blocks を再取得する");
  assert.deepEqual(app.paragraphBlocks, [{ x: 5, y: 5, width: 10, height: 10 }]);
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_rapid_image_switch_during_blocks_fetch_still_loads_new_image_blocks() -> None:
    _run_node_inline(
        _BLOCKS_PAYLOAD
        + r"""
let resolveA;
global.fetch = (url, options = {}) => {
  if (url === "/api/blocks/a.png") {
    return new Promise((resolve) => {
      resolveA = () => resolve(fetchResponse(blocksPayload("a.png", [{ x: 1, y: 1, width: 2, height: 2 }])));
    });
  }
  if (url === "/api/image/b.png") {
    return Promise.resolve(fetchResponse({ image_width: 100, image_height: 100, mime_type: "image/png" }));
  }
  if (url === "/api/session/b.png") {
    return Promise.resolve(fetchResponse(sessionPayload("b.png", [])));
  }
  if (url === "/api/blocks/b.png") {
    return Promise.resolve(fetchResponse(blocksPayload("b.png", [{ x: 5, y: 5, width: 10, height: 10 }])));
  }
  throw new Error(`unexpected fetch: ${url}`);
};
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100, mime: "image/png" },
  session: sessionPayload("a.png", []),
  imgLoaded: true,
  blockMode: true,
});
(async () => {
  const ensuring = app._ensureBlocks();
  await tick();
  assert.equal(app.blocksLoading, true, "a.png の取得が in-flight");

  const selecting = app.selectImage("b.png");
  await selecting;
  await tick();

  resolveA();
  await ensuring;
  await tick();

  assert.deepEqual(
    app.paragraphBlocks,
    [{ x: 5, y: 5, width: 10, height: 10 }],
    "b.png の blocks が取得される（a.png の in-flight に飢餓させられない）",
  );
  assert.equal(app.blockMode, true);
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_stale_blocks_response_during_image_switch_meta_await_is_not_applied() -> None:
    _run_node_inline(
        _BLOCKS_PAYLOAD
        + r"""
let resolveABlocks;
let resolveBMeta;
global.fetch = (url) => {
  if (url === "/api/blocks/a.png") {
    return new Promise((resolve) => {
      resolveABlocks = () => resolve(fetchResponse(blocksPayload("a.png", [{ x: 1, y: 1, width: 2, height: 2 }])));
    });
  }
  if (url === "/api/image/b.png") {
    return new Promise((resolve) => {
      resolveBMeta = () => resolve(fetchResponse({ image_width: 100, image_height: 100, mime_type: "image/png" }));
    });
  }
  if (url === "/api/session/b.png") {
    return Promise.resolve(fetchResponse(sessionPayload("b.png", [])));
  }
  if (url === "/api/blocks/b.png") {
    return Promise.resolve(fetchResponse(blocksPayload("b.png", [{ x: 5, y: 5, width: 10, height: 10 }])));
  }
  throw new Error(`unexpected fetch: ${url}`);
};
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100, mime: "image/png" },
  session: sessionPayload("a.png", []),
  imgLoaded: true,
  blockMode: true,
});
(async () => {
  const ensuringA = app._ensureBlocks();
  await tick();
  assert.equal(app.blocksLoading, true, "a.png の取得が in-flight");

  const selecting = app.selectImage("b.png");
  await tick();
  assert.equal(
    app.currentImage.name,
    "a.png",
    "selectImage は meta fetch を await 中で、currentImage はまだ a.png のまま",
  );

  // この時点で a.png の stale な blocks 応答が届く。currentImage.name はまだ
  // "a.png" のままなので、画像名だけの stale ガードだと素通りしてしまう。
  resolveABlocks();
  await ensuringA;
  await tick();

  assert.equal(
    app.paragraphBlocks,
    null,
    "meta/session await 中に届いた a.png の stale blocks を適用してはいけない（epoch 不一致で弾く）",
  );

  resolveBMeta();
  await selecting;
  await tick();

  assert.deepEqual(
    app.paragraphBlocks,
    [{ x: 5, y: 5, width: 10, height: 10 }],
    "最終的には b.png の blocks が反映される",
  );
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_zero_block_warning_does_not_duplicate_on_revisiting_same_image() -> None:
    _run_node_inline(
        _BLOCKS_PAYLOAD
        + r"""
global.fetch = (url) => {
  if (url === "/api/blocks/a.png") {
    return Promise.resolve(fetchResponse(blocksPayload("a.png", [])));
  }
  if (url === "/api/blocks/b.png") {
    return Promise.resolve(fetchResponse(blocksPayload("b.png", [])));
  }
  if (url === "/api/image/b.png") {
    return Promise.resolve(fetchResponse({ image_width: 100, image_height: 100, mime_type: "image/png" }));
  }
  if (url === "/api/session/b.png") {
    return Promise.resolve(fetchResponse(sessionPayload("b.png", [])));
  }
  if (url === "/api/image/a.png") {
    return Promise.resolve(fetchResponse({ image_width: 100, image_height: 100, mime_type: "image/png" }));
  }
  if (url === "/api/session/a.png") {
    return Promise.resolve(fetchResponse(sessionPayload("a.png", [])));
  }
  throw new Error(`unexpected fetch: ${url}`);
};
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100, mime: "image/png" },
  session: sessionPayload("a.png", []),
  imgLoaded: true,
  // selectImage 内の _ensureBlocks 呼び出しは blockMode 時のみ発火し、かつ
  // await されない（fire-and-forget）。本テストは _ensureBlocks の警告重複抑止
  // ロジック自体を検証したいので、blockMode は false のままにして selectImage
  // 側の自動発火とは競合させず、各切替後に明示的に _ensureBlocks を await する。
  blockMode: false,
  warnings: [],
});
(async () => {
  await app._ensureBlocks(); // a.png: 0 件 -> 警告 #1

  await app.selectImage("b.png");
  await app._ensureBlocks(); // b.png: 0 件（別文言の警告、本テストでは対象外）

  await app.selectImage("a.png");
  await app._ensureBlocks(); // a.png に再訪問: 0 件だが同文言を重複追加してはいけない

  const matches = app.warnings.filter((w) => /a\.png」からテキストブロックが検出されませんでした/.test(w));
  assert.equal(matches.length, 1, "同一画像への再訪問で同文言の警告が重複蓄積してはいけない");
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_detect_failure_warning_does_not_duplicate_on_repeated_failures() -> None:
    _run_node_inline(
        _BLOCKS_PAYLOAD
        + r"""
global.fetch = () => Promise.resolve({ ok: false, status: 502, json: async () => ({}) });
console.error = () => {};
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100, mime: "image/png" },
  session: sessionPayload("a.png", []),
  imgLoaded: true,
  warnings: [],
});
(async () => {
  // 1 回目の失敗で blockMode は OFF に戻る。再度 ON にして 2 回目も失敗させる。
  await app.toggleBlockMode();
  assert.equal(app.blockMode, false, "1 回目失敗でモード OFF");
  await app.toggleBlockMode();
  const matches = app.warnings.filter((w) => /a\.png」のテキストブロック検出に失敗/.test(w));
  assert.equal(matches.length, 1, "同一画像の失敗を繰り返しても同文言の警告は 1 件に留まる");
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_reselecting_same_image_during_blocks_fetch_recovers() -> None:
    _run_node_inline(
        _BLOCKS_PAYLOAD
        + r"""
let resolveA;
let aCalls = 0;
global.fetch = (url) => {
  if (url === "/api/blocks/a.png") {
    aCalls += 1;
    return new Promise((resolve) => {
      resolveA = () => resolve(fetchResponse(blocksPayload("a.png", [{ x: 1, y: 1, width: 2, height: 2 }])));
    });
  }
  if (url === "/api/image/a.png") {
    return Promise.resolve(fetchResponse({ image_width: 100, image_height: 100, mime_type: "image/png" }));
  }
  if (url === "/api/session/a.png") {
    return Promise.resolve(fetchResponse(sessionPayload("a.png", [])));
  }
  throw new Error(`unexpected fetch: ${url}`);
};
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100, mime: "image/png" },
  session: sessionPayload("a.png", []),
  imgLoaded: true,
  blockMode: true,
});
(async () => {
  const ensuring = app._ensureBlocks();      // a.png (A1) を in-flight にする
  await tick();
  assert.equal(app.blocksLoading, true, "A1 が in-flight");
  const firstResolve = resolveA;

  // in-flight のまま同じ画像を再選択する（selectImage が blocks=null, epoch++ する）
  await app.selectImage("a.png");
  await tick();

  // A1 応答が届く（epoch 不一致で破棄されるはず）
  firstResolve();
  await ensuring;
  await tick();

  // 再選択で起動した A2 応答を解決する
  resolveA();
  await tick();
  await tick();

  assert.deepEqual(
    app.paragraphBlocks,
    [{ x: 1, y: 1, width: 2, height: 2 }],
    "同名再選択後も最終的に blocks が反映される",
  );
  assert.equal(app.blocksLoading, false, "loading が正しく解除される");
  assert.equal(app.blockMode, true);
  assert.equal(aCalls, 2, "A1 破棄後に A2 が起動する（飢餓しない）");
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_stale_finally_does_not_release_new_generation_loading() -> None:
    _run_node_inline(
        _BLOCKS_PAYLOAD
        + r"""
let resolveA1;
let aCalls = 0;
global.fetch = (url) => {
  if (url === "/api/blocks/a.png") {
    aCalls += 1;
    if (aCalls === 1) {
      return new Promise((resolve) => {
        resolveA1 = () => resolve(fetchResponse(blocksPayload("a.png", [{ x: 1, y: 1, width: 2, height: 2 }])));
      });
    }
    // A2 以降は未解決のまま（in-flight を維持）
    return new Promise(() => {});
  }
  if (url === "/api/image/a.png" || url === "/api/image/b.png") {
    return Promise.resolve(fetchResponse({ image_width: 100, image_height: 100, mime_type: "image/png" }));
  }
  if (url === "/api/session/a.png" || url === "/api/session/b.png") {
    return Promise.resolve(fetchResponse(sessionPayload(url.endsWith("a.png") ? "a.png" : "b.png", [])));
  }
  if (url === "/api/blocks/b.png") {
    return Promise.resolve(fetchResponse(blocksPayload("b.png", [{ x: 5, y: 5, width: 10, height: 10 }])));
  }
  throw new Error(`unexpected fetch: ${url}`);
};
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100, mime: "image/png" },
  session: sessionPayload("a.png", []),
  imgLoaded: true,
  blockMode: true,
});
(async () => {
  const ensuringA1 = app._ensureBlocks();   // A1 in-flight
  await tick();

  await app.selectImage("b.png");            // B（blocks 即解決）
  await tick();

  await app.selectImage("a.png");            // A に戻る → A2 in-flight
  await tick();
  assert.equal(app.blocksLoading, true, "A2 が in-flight で loading 中");

  // ここで stale な A1 が解決する。A1 の finally は A2 の loading を奪ってはいけない。
  resolveA1();
  await ensuringA1;
  await tick();

  assert.equal(app.blocksLoading, true, "stale A1 の finally で A2 の loading が落ちない");

  // loading が落ちていないので、追加の _ensureBlocks は新規 fetch を起動しない
  await app._ensureBlocks();
  await tick();
  assert.equal(aCalls, 2, "不要な 3 本目 fetch が立たない（A1, A2 の 2 本のみ）");
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


def test_toggle_off_during_detection_discards_incoming_blocks() -> None:
    _run_node_inline(
        _BLOCKS_PAYLOAD
        + r"""
let resolveA;
global.fetch = (url) => {
  if (url === "/api/blocks/a.png") {
    return new Promise((resolve) => {
      resolveA = () => resolve(fetchResponse(blocksPayload("a.png", [{ x: 1, y: 1, width: 2, height: 2 }])));
    });
  }
  throw new Error(`unexpected fetch: ${url}`);
};
const app = newApp({
  currentImage: { name: "a.png", width: 100, height: 100, mime: "image/png" },
  session: sessionPayload("a.png", []),
  imgLoaded: true,
  blockMode: true,
});
(async () => {
  const ensuring = app._ensureBlocks();  // in-flight
  await tick();
  assert.equal(app.blocksLoading, true, "検出中");

  // 検出中に OFF する
  await app.toggleBlockMode();
  assert.equal(app.blockMode, false, "検出中でも OFF にできる");
  assert.equal(app.blocksLoading, false, "OFF でローディング表示が即消える");

  // 遅れて応答が届いても blocks / blockMode に反映されない
  resolveA();
  await ensuring;
  await tick();
  assert.equal(app.paragraphBlocks, null, "OFF 後に到着した応答は適用されない");
  assert.equal(app.blockMode, false, "OFF のまま");
})().catch((err) => { console.error(err); process.exit(1); });
"""
    )


# ---------------------------------------------------------------------------
# ブロック選択: 粒度 (vertical / paragraph)
# ---------------------------------------------------------------------------


def test_initial_granularity_is_vertical_and_persists_across_images() -> None:
    """blockGranularity の初期値は vertical で、画像切替後も維持される（スペック 9）。"""
    _run_node(
        r"""
const assert = require("node:assert/strict");
global.window = {};
global.fetch = (url) => {
  if (url.startsWith("/api/image/")) {
    return Promise.resolve({
      ok: true,
      json: async () => ({ image_width: 100, image_height: 100, mime_type: "image/png" }),
    });
  }
  if (url.startsWith("/api/session/")) {
    return Promise.resolve({
      ok: true,
      json: async () => ({
        image_name: "a.png",
        image_width: 100,
        image_height: 100,
        regions: [],
        schema_version: 1,
      }),
    });
  }
  throw new Error(`unexpected fetch: ${url}`);
};
require("./src/nova_parser/regional_ocr/static/app.js");

(async () => {
  const app = window.regionalOcrApp();
  assert.equal(app.blockGranularity, "vertical", "初期粒度は縦ブロック");
  app.setGranularity("paragraph");
  await app.selectImage("a.png");
  assert.equal(app.blockGranularity, "paragraph", "画像切替で粒度を維持する");
  assert.equal(app.paragraphBlocks, null, "画像切替で矩形一覧はリセットされる");
  assert.equal(app.verticalBlocks, null);
})();
"""
    )


def test_set_granularity_clears_hover_and_does_not_fetch() -> None:
    """粒度変更はホバーをクリアするだけで、追加 fetch は行わない（スペック 9）。"""
    _run_node(
        r"""
const assert = require("node:assert/strict");
global.window = {};
let fetchCount = 0;
global.fetch = () => { fetchCount += 1; throw new Error("must not fetch"); };
require("./src/nova_parser/regional_ocr/static/app.js");

const app = window.regionalOcrApp();
Object.assign(app, {
  currentImage: { name: "a.png", width: 100, height: 100, mime: "image/png" },
  blockMode: true,
  paragraphBlocks: [{ x: 0, y: 0, width: 10, height: 10 }],
  verticalBlocks: [{ x: 0, y: 0, width: 20, height: 20 }],
  hoverBlock: { x: 0, y: 0, width: 20, height: 20 },
});
app.setGranularity("paragraph");
assert.equal(app.blockGranularity, "paragraph");
assert.equal(app.hoverBlock, null, "粒度変更でホバーをクリアする");
assert.equal(fetchCount, 0, "粒度変更で fetch してはいけない");
assert.deepEqual(app.activeBlocks(), [{ x: 0, y: 0, width: 10, height: 10 }]);
app.setGranularity("vertical");
assert.deepEqual(app.activeBlocks(), [{ x: 0, y: 0, width: 20, height: 20 }]);
"""
    )


def test_active_blocks_falls_back_to_paragraphs_when_vertical_empty() -> None:
    """縦ブロック 0 件・段落ありなら段落矩形へフォールバックする（スペック 10）。"""
    _run_node(
        r"""
const assert = require("node:assert/strict");
global.window = {};
require("./src/nova_parser/regional_ocr/static/app.js");

const app = window.regionalOcrApp();
app.paragraphBlocks = [{ x: 1, y: 1, width: 5, height: 5 }];
app.verticalBlocks = [];
assert.equal(app.blockGranularity, "vertical");
assert.deepEqual(app.activeBlocks(), [{ x: 1, y: 1, width: 5, height: 5 }]);
"""
    )


def test_ensure_blocks_stores_both_lists_and_warns_only_when_both_empty() -> None:
    """_ensureBlocks は両矩形を保持し、両方 0 件のときだけ警告する（スペック 10）。"""
    _run_node(
        r"""
const assert = require("node:assert/strict");
global.window = {};
let payload = { blocks: [{ x: 0, y: 0, width: 10, height: 10 }], vertical_blocks: [] };
global.fetch = () => Promise.resolve({ ok: true, json: async () => payload });
require("./src/nova_parser/regional_ocr/static/app.js");

(async () => {
  const app = window.regionalOcrApp();
  app.currentImage = { name: "a.png", width: 100, height: 100, mime: "image/png" };
  await app._ensureBlocks();
  assert.deepEqual(app.paragraphBlocks, [{ x: 0, y: 0, width: 10, height: 10 }]);
  assert.deepEqual(app.verticalBlocks, []);
  assert.deepEqual(app.warnings, [], "段落があれば警告しない");

  const app2 = window.regionalOcrApp();
  app2.currentImage = { name: "b.png", width: 100, height: 100, mime: "image/png" };
  payload = { blocks: [], vertical_blocks: [] };
  await app2._ensureBlocks();
  assert.deepEqual(app2.warnings, ["「b.png」からテキストブロックが検出されませんでした"]);
})();
"""
    )

def test_init_refreshes_undone_list_and_failure_appends_warning() -> None:
    """init() が未 OCR 一覧を取得して undoneItems を埋め、取得失敗時は warnings に追記して前回一覧を維持する。"""
    _run_node(
        r"""
const assert = require("node:assert/strict");

global.window = { addEventListener: () => {} };

let failNext = false;
global.fetch = (url) => {
  if (url === "/api/images") {
    return Promise.resolve({ ok: true, json: async () => ({ images: [], warnings: [] }) });
  }
  if (url === "/api/regions/undone") {
    if (failNext) return Promise.resolve({ ok: false, status: 500 });
    return Promise.resolve({
      ok: true,
      json: async () => ({
        items: [
          { image_name: "a.png", rect_id: "r1", draw_order: 0, ocr_status: "pending", ocr_error: null },
        ],
        warnings: ["stem collision: x.png, x.webp"],
      }),
    });
  }
  throw new Error(`unexpected fetch: ${url}`);
};

require("./src/nova_parser/regional_ocr/static/app.js");

(async () => {
  const app = window.regionalOcrApp();
  await app.init();
  assert.equal(app.undoneItems.length, 1);
  assert.equal(app.undoneItems[0].rect_id, "r1");
  assert.ok(app.warnings.some((w) => w.includes("stem collision")), "サーバ warnings を表示に反映する");

  failNext = true;
  await app.refreshUndone();
  assert.equal(app.undoneItems.length, 1, "取得失敗時は前回の一覧を維持する");
  assert.ok(app.warnings.some((w) => w.includes("未 OCR 一覧の取得に失敗")));
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
""",
    )


def test_sync_undone_replaces_only_current_image_rows() -> None:
    """_syncUndoneForCurrentImage は現在画像の行だけを session.regions から再構成し、他画像の行は保持する。"""
    _run_node(
        r"""
const assert = require("node:assert/strict");

global.window = {};

require("./src/nova_parser/regional_ocr/static/app.js");

const app = window.regionalOcrApp();
app.currentImage = { name: "b.png", width: 100, height: 100, mime: "image/png" };
app.session = {
  image_name: "b.png",
  image_width: 100,
  image_height: 100,
  schema_version: 1,
  regions: [
    {
      rectangle: { rect_id: "b0", draw_order: 0, x: 0, y: 0, width: 30, height: 30 },
      text: "済み",
      ocr_status: "done",
      ocr_error: null,
      ocr_completed_at: null,
    },
    {
      rectangle: { rect_id: "b1", draw_order: 1, x: 40, y: 0, width: 30, height: 30 },
      text: null,
      ocr_status: "pending",
      ocr_error: null,
      ocr_completed_at: null,
    },
  ],
};
app.undoneItems = [
  { image_name: "a.png", rect_id: "a9", draw_order: 0, ocr_status: "pending", ocr_error: null },
  { image_name: "b.png", rect_id: "b0", draw_order: 0, ocr_status: "pending", ocr_error: null },
];

app._syncUndoneForCurrentImage();

assert.deepEqual(
  app.undoneItems.map((i) => [i.image_name, i.rect_id, i.ocr_status]),
  [["a.png", "a9", "pending"], ["b.png", "b1", "pending"]],
  "done になった b0 は消え、b1 が入り、a.png の行は保持される",
);

// scheduleSave 経由でも即時に同期される（500ms タイマは後始末する）
app.session.regions = app.session.regions.filter((r) => r.rectangle.rect_id !== "b1");
app.scheduleSave();
assert.deepEqual(
  app.undoneItems.map((i) => [i.image_name, i.rect_id]),
  [["a.png", "a9"]],
  "リージョン削除が scheduleSave 時点で一覧へ反映される",
);
clearTimeout(app.saveTimer);
app.saveTimer = null;
""",
    )


def test_run_single_ocr_success_removes_row_from_undone_list() -> None:
    """runSingleOcr 成功で該当行が未 OCR 一覧から消える。"""
    _run_node(
        r"""
const assert = require("node:assert/strict");

global.window = {};

global.fetch = (url, options = {}) => {
  if (options.method === "POST" && url === "/api/ocr/c.png/c0") {
    return Promise.resolve({
      ok: true,
      json: async () => ({
        rectangle: { rect_id: "c0", draw_order: 0, x: 0, y: 0, width: 30, height: 30 },
        text: "OK",
        ocr_status: "done",
        ocr_error: null,
        ocr_completed_at: "2026-07-19T00:00:00Z",
      }),
    });
  }
  throw new Error(`unexpected fetch: ${url}`);
};

require("./src/nova_parser/regional_ocr/static/app.js");

(async () => {
  const app = window.regionalOcrApp();
  app.currentImage = { name: "c.png", width: 100, height: 100, mime: "image/png" };
  app.session = {
    image_name: "c.png",
    image_width: 100,
    image_height: 100,
    schema_version: 1,
    regions: [
      {
        rectangle: { rect_id: "c0", draw_order: 0, x: 0, y: 0, width: 30, height: 30 },
        text: null,
        ocr_status: "pending",
        ocr_error: null,
        ocr_completed_at: null,
      },
    ],
  };
  app.undoneItems = [
    { image_name: "c.png", rect_id: "c0", draw_order: 0, ocr_status: "pending", ocr_error: null },
  ];

  await app.runSingleOcr("c0");

  assert.equal(app.session.regions[0].ocr_status, "done");
  assert.deepEqual(app.undoneItems, [], "done になった行は一覧から消える");
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
""",
    )


def test_run_undone_ocr_drains_saves_then_streams_with_include_errors() -> None:
    """runUndoneOcr は保存 drain（PUT 完了）後に include_errors=true で SSE を開始し、終了時に一覧を再取得する。"""
    _run_node(
        r"""
const assert = require("node:assert/strict");

global.window = {};

const calls = [];

function sseResponse(payloads) {
  const encoder = new TextEncoder();
  const chunks = payloads.map((p) => encoder.encode(`data: ${JSON.stringify(p)}\n\n`));
  let i = 0;
  return {
    ok: true,
    body: {
      getReader: () => ({
        read: async () =>
          i < chunks.length ? { value: chunks[i++], done: false } : { value: undefined, done: true },
        releaseLock: () => {},
      }),
    },
  };
}

global.fetch = (url, options = {}) => {
  if (options.method === "PUT") {
    calls.push("PUT");
    return Promise.resolve({ ok: true, json: async () => JSON.parse(options.body) });
  }
  if (url.startsWith("/api/ocr/batch/stream")) {
    calls.push(`POST ${url}`);
    return Promise.resolve(
      sseResponse([{ image_name: "a.png", rect_id: "r1", status: "done", text: "T" }]),
    );
  }
  if (url === "/api/regions/undone") {
    calls.push("GET_UNDONE");
    return Promise.resolve({ ok: true, json: async () => ({ items: [], warnings: [] }) });
  }
  throw new Error(`unexpected fetch: ${url}`);
};

require("./src/nova_parser/regional_ocr/static/app.js");

(async () => {
  const app = window.regionalOcrApp();
  app.currentImage = { name: "a.png", width: 100, height: 100, mime: "image/png" };
  app.session = {
    image_name: "a.png",
    image_width: 100,
    image_height: 100,
    schema_version: 1,
    regions: [
      {
        rectangle: { rect_id: "r1", draw_order: 0, x: 0, y: 0, width: 30, height: 30 },
        text: null,
        ocr_status: "pending",
        ocr_error: null,
        ocr_completed_at: null,
      },
    ],
  };
  app.undoneItems = [
    { image_name: "a.png", rect_id: "r1", draw_order: 0, ocr_status: "pending", ocr_error: null },
  ];
  // debounce 中の未保存編集を再現する
  app.scheduleSave();

  await app.runUndoneOcr();

  assert.equal(calls[0], "PUT", "SSE 開始前に未保存分が flush される");
  assert.ok(
    calls[1] === "POST /api/ocr/batch/stream?include_errors=true",
    `include_errors=true で呼ぶこと (actual: ${calls[1]})`,
  );
  assert.equal(calls[2], "GET_UNDONE", "終了時に一覧を再取得する");
  assert.deepEqual(app.undoneItems, []);
  assert.equal(app.session.regions[0].ocr_status, "done", "現在画像の表示にも反映される");
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
""",
    )


def test_apply_undone_from_batch_item_removes_done_and_updates_error() -> None:
    """SSE item の done は行削除、error はバッジとメッセージを更新する。"""
    _run_node(
        r"""
const assert = require("node:assert/strict");

global.window = {};

require("./src/nova_parser/regional_ocr/static/app.js");

const app = window.regionalOcrApp();
app.undoneItems = [
  { image_name: "a.png", rect_id: "r1", draw_order: 0, ocr_status: "pending", ocr_error: null },
  { image_name: "a.png", rect_id: "r2", draw_order: 1, ocr_status: "pending", ocr_error: null },
];

app._applyUndoneFromBatchItem({ image_name: "a.png", rect_id: "r1", status: "done", text: "T" });
assert.deepEqual(
  app.undoneItems.map((i) => i.rect_id),
  ["r2"],
  "done の行は削除される",
);

app._applyUndoneFromBatchItem({ image_name: "a.png", rect_id: "r2", status: "error", error: "boom" });
assert.equal(app.undoneItems[0].ocr_status, "error");
assert.equal(app.undoneItems[0].ocr_error, "boom");
""",
    )


def test_run_undone_ocr_does_not_start_batch_when_save_fails() -> None:
    """保存 drain が失敗したら一括 OCR を開始せず、error 状態と一覧の行を維持する。"""
    _run_node(
        r"""
const assert = require("node:assert/strict");

global.window = {};

const calls = [];

global.fetch = (url, options = {}) => {
  if (options.method === "PUT") {
    calls.push("PUT");
    return Promise.resolve({ ok: false, status: 500 });
  }
  if (url.startsWith("/api/ocr/batch/stream")) {
    calls.push("POST_BATCH");
    throw new Error("保存失敗時にバッチを開始してはいけない");
  }
  if (url === "/api/regions/undone") {
    calls.push("GET_UNDONE");
    return Promise.resolve({ ok: true, json: async () => ({ items: [], warnings: [] }) });
  }
  throw new Error(`unexpected fetch: ${url}`);
};

require("./src/nova_parser/regional_ocr/static/app.js");

(async () => {
  const app = window.regionalOcrApp();
  app.currentImage = { name: "a.png", width: 100, height: 100, mime: "image/png" };
  app.session = {
    image_name: "a.png",
    image_width: 100,
    image_height: 100,
    schema_version: 1,
    regions: [
      {
        rectangle: { rect_id: "r1", draw_order: 0, x: 0, y: 0, width: 30, height: 30 },
        text: null,
        ocr_status: "pending",
        ocr_error: null,
        ocr_completed_at: null,
      },
    ],
  };
  app.undoneItems = [
    { image_name: "a.png", rect_id: "r1", draw_order: 0, ocr_status: "pending", ocr_error: null },
  ];
  app.scheduleSave();

  await app.runUndoneOcr();

  assert.deepEqual(calls, ["PUT"], "PUT 失敗後はバッチ SSE も一覧再取得も行わない");
  assert.equal(app.savingState, "error", "保存失敗の error 表示を維持する");
  assert.equal(app.undoneItems.length, 1, "未 OCR 行を消さない");
  assert.ok(
    app.warnings.some((w) => w.includes("保存に失敗したため一括 OCR を中止しました")),
    `中止理由の警告が追加される (actual: ${JSON.stringify(app.warnings)})`,
  );
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
""",
    )


def test_refresh_undone_keeps_unsaved_pending_rows_of_current_image() -> None:
    """debounce 中に「更新」しても現在画像の pending 行が消えず、保存成功後も残る。"""
    _run_node(
        r"""
const assert = require("node:assert/strict");

global.window = {};

global.fetch = (url, options = {}) => {
  if (options.method === "PUT") {
    return Promise.resolve({ ok: true, json: async () => JSON.parse(options.body) });
  }
  if (url === "/api/regions/undone") {
    // サーバはまだ現在画像の新規 pending を知らない
    return Promise.resolve({
      ok: true,
      json: async () => ({
        items: [
          { image_name: "b.png", rect_id: "b0", draw_order: 0, ocr_status: "pending", ocr_error: null },
        ],
        warnings: [],
      }),
    });
  }
  throw new Error(`unexpected fetch: ${url}`);
};

require("./src/nova_parser/regional_ocr/static/app.js");

(async () => {
  const app = window.regionalOcrApp();
  app.currentImage = { name: "a.png", width: 100, height: 100, mime: "image/png" };
  app.session = {
    image_name: "a.png",
    image_width: 100,
    image_height: 100,
    schema_version: 1,
    regions: [
      {
        rectangle: { rect_id: "r1", draw_order: 0, x: 0, y: 0, width: 30, height: 30 },
        text: null,
        ocr_status: "pending",
        ocr_error: null,
        ocr_completed_at: null,
      },
    ],
  };
  app.scheduleSave(); // debounce 中（サーバ未反映の編集がある状態）

  await app.refreshUndone();

  assert.deepEqual(
    app.undoneItems.map((i) => `${i.image_name}:${i.rect_id}`),
    ["a.png:r1", "b.png:b0"],
    "サーバ未反映の現在画像 pending 行を失わない",
  );

  await app._drainSaves(); // その後の保存成功

  assert.ok(
    app.undoneItems.some((i) => i.image_name === "a.png" && i.rect_id === "r1"),
    "保存成功後も現在画像の行が残る",
  );
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
""",
    )


def test_refresh_undone_during_inflight_put_keeps_row_after_save_completes() -> None:
    """PUT 実行中に「更新」しても現在画像の pending 行が消えず、保存完了後も残る。"""
    _run_node(
        r"""
const assert = require("node:assert/strict");

global.window = {};

const putResolvers = [];

global.fetch = (url, options = {}) => {
  if (options.method === "PUT") {
    return new Promise((resolve) => {
      putResolvers.push(() => resolve({ ok: true, json: async () => JSON.parse(options.body) }));
    });
  }
  if (url === "/api/regions/undone") {
    // サーバはまだ保存中の pending を知らない
    return Promise.resolve({ ok: true, json: async () => ({ items: [], warnings: [] }) });
  }
  throw new Error(`unexpected fetch: ${url}`);
};

require("./src/nova_parser/regional_ocr/static/app.js");

(async () => {
  const app = window.regionalOcrApp();
  app.currentImage = { name: "a.png", width: 100, height: 100, mime: "image/png" };
  app.session = {
    image_name: "a.png",
    image_width: 100,
    image_height: 100,
    schema_version: 1,
    regions: [
      {
        rectangle: { rect_id: "r1", draw_order: 0, x: 0, y: 0, width: 30, height: 30 },
        text: null,
        ocr_status: "pending",
        ocr_error: null,
        ocr_completed_at: null,
      },
    ],
  };
  app.saveVersion = 1;
  app._launchSave("a.png", JSON.parse(JSON.stringify(app.session)), 1); // PUT 実行中の状態を作る

  await app.refreshUndone();

  assert.ok(
    app.undoneItems.some((i) => i.image_name === "a.png" && i.rect_id === "r1"),
    "PUT 実行中の更新でも現在画像の行を失わない",
  );

  putResolvers.shift()(); // PUT 完了（保存成功）
  await app._drainSaves();

  assert.ok(
    app.undoneItems.some((i) => i.image_name === "a.png" && i.rect_id === "r1"),
    "保存成功後も行が残る",
  );
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
""",
    )

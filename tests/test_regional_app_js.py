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

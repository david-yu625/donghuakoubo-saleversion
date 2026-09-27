const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const filename = path.resolve(__dirname, '../src/video/camera.ts');
const compiled = new Module(filename, module);
compiled.filename = filename;
compiled.paths = Module._nodeModulePaths(path.dirname(filename));
compiled._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, esModuleInterop: true},
}).outputText, filename);
const {cameraAtFrame, focusCamera, fitCamera, travelWindow, viewport, cardHeight} = compiled.exports;
const manifest = require('../public/manifest.json');
const nodes = manifest.nodes;
const duration = Math.round(manifest.durationSeconds * 30);

test('camera travels through actual world coordinates and returns to a readable close view', () => {
  for (let i = 1; i < nodes.length; i++) {
    const w = travelWindow(nodes, i, duration);
    const start = cameraAtFrame(nodes, w.start, duration);
    const middle = cameraAtFrame(nodes, (w.start + w.end) / 2, duration);
    const end = cameraAtFrame(nodes, w.end, duration);
    assert.deepEqual(start, focusCamera(nodes[i - 1]));
    assert.ok(Math.abs(end.x - nodes[i].x) < 0.001);
    assert.ok(Math.abs(end.y - nodes[i].y) < 0.001);
    assert.ok(middle.zoom < start.zoom && middle.zoom < end.zoom);
    // At the wide midpoint both image centers are in view, showing the route.
    for (const n of [nodes[i - 1], nodes[i]]) {
      assert.ok(Math.abs(n.x - middle.x) * middle.zoom < viewport.width / 2);
      assert.ok(Math.abs(n.y - middle.y) * middle.zoom < viewport.height / 2);
    }
  }
});

test('camera does not jump at travel boundaries and windows do not overlap', () => {
  for (let i = 1; i < nodes.length; i++) {
    const w = travelWindow(nodes, i, duration);
    if (i > 1) assert.ok(w.start > travelWindow(nodes, i - 1, duration).end);
    for (const boundary of [w.start, w.end]) {
      const a = cameraAtFrame(nodes, boundary - 0.0001, duration);
      const b = cameraAtFrame(nodes, boundary + 0.0001, duration);
      assert.ok(Math.hypot(a.x - b.x, a.y - b.y) < 0.01);
      assert.ok(Math.abs(a.zoom - b.zoom) < 0.0001);
    }
  }
});

test('short camera moves leave most of each beat for viewing the image', () => {
  for (let i = 1; i < nodes.length; i++) {
    const w = travelWindow(nodes, i, duration);
    const gap = (nodes[i + 1]?.start ?? duration) - nodes[i].start;
    assert.ok(w.end - w.start <= gap * 0.5, `Travel for node ${i} consumed too much of its ${gap}-frame beat`);
    assert.ok(nodes[i].start - w.start >= 0, 'Move begins before the incoming asset cue');
  }
});

test('every video frame keeps at least one illustration in view instead of empty travel', () => {
  for (let frame = 0; frame < duration; frame++) {
    const c = cameraAtFrame(nodes, frame, duration);
    assert.ok(Number.isFinite(c.x) && Number.isFinite(c.y) && c.zoom > 0);
    assert.ok(nodes.some(n =>
      Math.abs(n.x - c.x) < viewport.width / (2 * c.zoom) + n.width / 2 &&
      Math.abs(n.y - c.y) < viewport.height / (2 * c.zoom) + cardHeight(n) / 2
    ), `Empty camera viewport at frame ${frame}`);
  }
});

test('ending pulls out to the complete shared canvas', () => {
  const end = cameraAtFrame(nodes, duration - 1, duration);
  const overview = fitCamera(nodes, 500);
  assert.ok(Math.abs(end.x - overview.x) < 0.001);
  assert.ok(Math.abs(end.y - overview.y) < 0.001);
  assert.ok(Math.abs(end.zoom - overview.zoom) < 0.001);
});

test('empty and single-node scenes remain valid', () => {
  assert.deepEqual(cameraAtFrame([], 0, 30), {x: 0, y: 0, zoom: 1});
  const n = [{x: 0, y: 0, width: 1120, start: 0}];
  for (const frame of [0, 1, 10, 29]) assert.ok(cameraAtFrame(n, frame, 30).zoom > 0);
});

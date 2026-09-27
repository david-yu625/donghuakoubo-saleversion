const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const catalog = require('../effect_catalog.json');
const filename = path.resolve(__dirname, '../src/video/effects.ts');
const compiled = new Module(filename, module);
compiled.filename = filename;
compiled.paths = Module._nodeModulePaths(path.dirname(filename));
compiled._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, esModuleInterop: true},
}).outputText, filename);
const {transitionStyles, imageAnimationStyle, effectDuration} = compiled.exports;

test('every catalog transition has distinct geometry, not a common fade', () => {
  const midpoints = Object.keys(catalog.transitions).map(id => transitionStyles(id, 0.5));
  assert.equal(new Set(midpoints.map(item => JSON.stringify(item))).size, midpoints.length);
  for (const pair of midpoints) {
    assert.ok(pair.incoming.transform || pair.incoming.clipPath);
  }
});

test('transitions retain the outgoing image at the start and fully expose incoming at completion', () => {
  for (const id of Object.keys(catalog.transitions)) {
    assert.deepEqual(transitionStyles(id, 0), {incoming: {opacity: 0}, outgoing: {}});
    assert.deepEqual(transitionStyles(id, 1), {incoming: {}, outgoing: {opacity: 0}});
    assert.deepEqual(transitionStyles(id, 2), transitionStyles(id, 1));
    for (const p of [0.01, 0.25, 0.5, 0.75, 0.99]) {
      assert.doesNotMatch(JSON.stringify(transitionStyles(id, p)), /NaN|Infinity/);
    }
    assert.equal(effectDuration('transitions', id), catalog.transitions[id].duration_frames);
  }
});

test('all image animations differ and finish without residual cropping or opacity', () => {
  const ids = Object.keys(catalog.image_animations);
  assert.equal(new Set(ids.map(id => JSON.stringify(imageAnimationStyle(id, 0.25)))).size, ids.length);
  for (const id of ids) {
    assert.deepEqual(imageAnimationStyle(id, 1), {});
    assert.equal(effectDuration('image_animations', id), catalog.image_animations[id].duration_frames);
  }
});

test('legacy manifests without effect IDs and unknown IDs have a safe fallback', () => {
  assert.deepEqual(transitionStyles(undefined, 0.5), transitionStyles('glide', 0.5));
  assert.deepEqual(transitionStyles('missing', 0.5), transitionStyles('glide', 0.5));
  assert.deepEqual(imageAnimationStyle(undefined, 0.5), imageAnimationStyle('rise', 0.5));
});

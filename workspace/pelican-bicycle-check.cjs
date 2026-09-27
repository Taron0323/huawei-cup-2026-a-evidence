#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = __dirname;
const htmlPath = path.join(root, 'pelican-bicycle.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const svgMatch = html.match(/<svg\b[\s\S]*?<\/svg>/i);
if (!svgMatch) throw new Error('SVG_NOT_FOUND');
const svg = svgMatch[0];

const ids = [...html.matchAll(/\bid\s*=\s*["']([^"']+)["']/g)].map((match) => match[1]);
const duplicateIds = ids.filter((id, index) => ids.indexOf(id) !== index);
if (duplicateIds.length) throw new Error(`DUPLICATE_IDS:${[...new Set(duplicateIds)].join(',')}`);

const references = [...html.matchAll(/url\(#([^)]+)\)|(?:href|xlink:href)\s*=\s*["']#([^"']+)["']/g)]
  .map((match) => match[1] || match[2]);
const idSet = new Set(ids);
const missingReferences = [...new Set(references.filter((id) => !idSet.has(id)))];
if (missingReferences.length) throw new Error(`MISSING_REFERENCES:${missingReferences.join(',')}`);
if (/<(?:script|img)\b[^>]+\b(?:src|href)\s*=\s*["']https?:/i.test(html)) throw new Error('EXTERNAL_RUNTIME_DEPENDENCY');

class FakeElement {
  constructor(id) {
    this.id = id;
    this.attributes = new Map();
    this.listeners = new Map();
    this.hidden = false;
    this.value = id === 'speedRange' ? '1' : '';
    this.textContent = '';
    this.title = '';
    this.style = {};
    this.classList = { toggle: (name, enabled) => this.attributes.set(`class:${name}`, Boolean(enabled)) };
  }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name); }
  addEventListener(type, callback) { this.listeners.set(type, callback); }
}

const elementIds = [...new Set(ids)];
const elements = new Map(elementIds.map((id) => [id, new FakeElement(id)]));
const documentListeners = new Map();
let rafCallback = null;
const context = {
  console,
  document: {
    getElementById: (id) => elements.get(id) || null,
    addEventListener: (type, callback) => documentListeners.set(type, callback)
  },
  performance: { now: () => 0 },
  window: {
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    requestAnimationFrame: (callback) => { rafCallback = callback; return 1; }
  }
};
context.window.window = context.window;
context.window.document = context.document;
vm.createContext(context);
const script = html.match(/<script>([\s\S]*?)<\/script>/i)[1];
new vm.Script(script, { filename: 'pelican-bicycle.html' }).runInContext(context);
const api = context.window.__pelicanAnimation;
if (!api) throw new Error('ANIMATION_API_NOT_EXPOSED');

function parsePath(node) {
  const numbers = [...String(node.getAttribute('d') || '').matchAll(/-?\d+(?:\.\d+)?/g)].map((match) => Number(match[0]));
  if (numbers.length !== 6 || numbers.some((number) => !Number.isFinite(number))) throw new Error(`INVALID_LEG_PATH:${node.id}`);
  return { hip: { x: numbers[0], y: numbers[1] }, knee: { x: numbers[2], y: numbers[3] }, foot: { x: numbers[4], y: numbers[5] } };
}

function distance(a, b) { return Math.hypot(a.x - b.x, a.y - b.y); }
function assertClose(actual, expected, tolerance, label) {
  if (Math.abs(actual - expected) > tolerance) throw new Error(`${label}:${actual}!=${expected}`);
}

const samples = [];
for (let frame = 0; frame < 600; frame += 1) {
  api.render(frame * 1000 / 60);
  for (const id of ['nearLeg', 'farLeg']) {
    const leg = parsePath(elements.get(id));
    assertClose(distance(leg.hip, leg.knee), api.legLengths.upper, 0.08, `${id}_UPPER_${frame}`);
    assertClose(distance(leg.knee, leg.foot), api.legLengths.lower, 0.08, `${id}_LOWER_${frame}`);
  }
  samples.push(elements.get('rearWheel').getAttribute('transform'));
}
if (new Set(samples).size < 500) throw new Error('WHEEL_MOTION_TOO_SMALL');

api.setPlaying(true);
if (typeof rafCallback !== 'function') throw new Error('RAF_NOT_REGISTERED');
rafCallback(1000);
const movingTransform = elements.get('rearWheel').getAttribute('transform');
api.setPlaying(false);
rafCallback(2000);
const pausedTransform = elements.get('rearWheel').getAttribute('transform');
if (movingTransform !== pausedTransform) throw new Error('PAUSE_DID_NOT_HOLD_FRAME');
api.setPlaying(true);
rafCallback(3000);
const resumedTransform = elements.get('rearWheel').getAttribute('transform');
if (resumedTransform === pausedTransform) throw new Error('RESUME_DID_NOT_MOVE');

api.setSpeed(1.6);
if (api.getState().speed !== 1.6 || elements.get('speedValue').textContent !== '1.6×') throw new Error('SPEED_CONTROL_FAILED');
api.restart();
if (api.getState().elapsed !== 0 || !/rotate\(28\.40\)/.test(elements.get('rearWheel').getAttribute('transform'))) throw new Error('RESTART_FAILED');

(async () => {
  const svgOutput = path.join(root, 'pelican-bicycle-preview.png');
  let rasterMessage = 'RASTER_SKIPPED: install sharp to generate the PNG preview';
  try {
    const sharp = require('sharp');
    const image = sharp(Buffer.from(svg));
    const metadata = await image.metadata();
    await image.png().toFile(svgOutput);
    const raw = await sharp(svgOutput).raw().toBuffer({ resolveWithObject: true });
    const nonZero = raw.data.some((value) => value !== 0);
    if (!metadata.width || !metadata.height || !nonZero) throw new Error('RASTER_BLANK');
    rasterMessage = `RASTER_OK:${metadata.width}x${metadata.height}`;
  } catch (error) {
    if (error && error.code !== 'MODULE_NOT_FOUND') throw error;
  }

  console.log(`PASS: 600 frames, constant leg lengths, pause/resume, speed, restart, IDs and references; ${rasterMessage}`);
})().catch((error) => {
  console.error(`FAIL: ${error.message}`);
  process.exitCode = 1;
});

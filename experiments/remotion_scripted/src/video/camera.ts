import catalog from '../../effect_catalog.json';
import type {Manifest, Shot} from './types';
import {FPS} from './types';

export type CameraPose = {x: number; y: number; zoom: number};
const clamp = (v: number) => Math.max(0, Math.min(1, v));
const smooth = (v: number) => {const t = clamp(v); return t * t * (3 - 2 * t);};
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const cardHeight = (shot: Pick<Shot, 'width' | 'height'>) => shot.height || shot.width * 9 / 16;
const focus = (shot: Shot): CameraPose => ({x: shot.x, y: shot.y, zoom: Math.min(0.96, 1320 / shot.width, 605 / cardHeight(shot))});

export function fitCamera(shots: Shot[], padding = 220): CameraPose {
  if (!shots.length) return {x: 0, y: 0, zoom: 1};
  const left = Math.min(...shots.map(s => s.x - s.width / 2));
  const right = Math.max(...shots.map(s => s.x + s.width / 2));
  const top = Math.min(...shots.map(s => s.y - cardHeight(s) / 2));
  const bottom = Math.max(...shots.map(s => s.y + cardHeight(s) / 2));
  return {x: (left + right) / 2, y: (top + bottom) / 2, zoom: Math.min(0.96, 1920 / (right - left + padding), 704 / (bottom - top + padding))};
}

export function travelWindow(shots: Shot[], index: number, duration: number) {
  const shot = shots[index], previous = shots[index - 1];
  const nextStart = shots[index + 1]?.start ?? duration / FPS;
  const requested = shot.camera_frames ?? catalog.camera_moves[shot.camera_effect as keyof typeof catalog.camera_moves]?.duration_frames ?? 66;
  // Start the move while the previous card is still comfortably visible and
  // leave enough frames after arrival for the target to settle.  A camera move
  // that is only a few frames long reads as a dissolve, especially on a wide
  // canvas where the distance between cards is large.
  const lead = previous ? Math.min(requested * 0.42, (shot.start - previous.start) * FPS * 0.24) : 0;
  const tail = Math.max(1, Math.min(requested * 0.16, (nextStart - shot.start) * FPS * 0.10));
  return {start: shot.start * FPS - lead, end: shot.start * FPS + tail};
}

function travel(from: Shot, to: Shot, t: number): CameraPose {
  const a = focus(from), b = focus(to), raw = clamp(t), p = smooth(raw);
  const dx = b.x - a.x, dy = b.y - a.y, distance = Math.max(1, Math.hypot(dx, dy));
  const bell = Math.sin(Math.PI * raw) ** 2, key = to.camera_effect ?? 'pan';
  const xProgress = key === 'crane' ? smooth(raw ** 1.22) : p;
  const yProgress = key === 'crane' ? smooth(1 - (1 - raw) ** 1.22) : p;
  const bend = key === 'arc' ? Math.min(420, distance * 0.16) * bell : 0;
  // The shared view is deliberately wider than either close-up.  This is the
  // visual signature of the infinite canvas: pull out far enough to reveal the
  // route and neighbouring node, travel through that view, then push back in.
  const bridgeFactor = key === 'overview' ? 0.54 : key === 'dolly' ? 0.62 : key === 'arc' ? 0.68 : key === 'crane' ? 0.72 : 0.76;
  const bridge = fitCamera([from, to], 600).zoom * bridgeFactor;
  const pullback = raw < 0.38 ? smooth(raw / 0.38) : raw > 0.76 ? smooth((1 - raw) / 0.24) : 1;
  const zoom = lerp(lerp(a.zoom, b.zoom, p), bridge, pullback);
  return {x: lerp(a.x, b.x, xProgress) - dy / distance * bend, y: lerp(a.y, b.y, yProgress) + dx / distance * bend, zoom};
}

export function cameraAtFrame(shots: Shot[], frame: number, duration: number): CameraPose {
  if (!shots.length) return {x: 0, y: 0, zoom: 1};
  const first = focus(shots[0]), firstTravel = shots.length > 1 ? travelWindow(shots, 1, duration).start : duration;
  const introEnd = Math.max(1, Math.min(36, firstTravel * 0.52));
  if (frame < introEnd) {
    const overview = fitCamera(shots.slice(0, 3), 420), p = smooth(frame / introEnd);
    return {x: lerp(overview.x, first.x, p), y: lerp(overview.y, first.y, p), zoom: lerp(overview.zoom, first.zoom, p)};
  }
  for (let i = 1; i < shots.length; i++) {
    const window = travelWindow(shots, i, duration);
    if (frame < window.start) return focus(shots[i - 1]);
    if (frame <= window.end) return travel(shots[i - 1], shots[i], (frame - window.start) / Math.max(1, window.end - window.start));
  }
  const last = focus(shots[shots.length - 1]), lastLanding = shots.length > 1 ? travelWindow(shots, shots.length - 1, duration).end : introEnd;
  const outroStart = Math.max(lastLanding + 12, duration - 54), p = smooth((frame - outroStart) / Math.max(1, duration - 1 - outroStart));
  const overview = fitCamera(shots, 520);
  return {x: lerp(last.x, overview.x, p), y: lerp(last.y, overview.y, p), zoom: lerp(last.zoom, overview.zoom, p)};
}

export function cameraFor(frame: number, project: Manifest): CameraPose {
  return cameraAtFrame(project.shots, frame, Math.round(project.durationSeconds * FPS));
}

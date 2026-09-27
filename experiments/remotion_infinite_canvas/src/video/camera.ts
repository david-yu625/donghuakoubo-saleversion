import catalog from '../../effect_catalog.json';

export type CameraNode = {x: number; y: number; width: number; start: number; camera_move?: string; camera_frames?: number};
export type Camera = {x: number; y: number; zoom: number};
export const viewport = {width: 1920, height: 704};
const clamp = (v: number) => Math.max(0, Math.min(1, v));
const smooth = (v: number) => {const t = clamp(v); return t * t * (3 - 2 * t);};
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const cardHeight = (node: CameraNode) => node.width * 9 / 16;
export const focusCamera = (node: CameraNode): Camera => ({x: node.x, y: node.y, zoom: Math.min(0.96, 1320 / node.width, 605 / cardHeight(node))});

export function fitCamera(nodes: CameraNode[], padding = 220): Camera {
  if (!nodes.length) return {x: 0, y: 0, zoom: 1};
  const left = Math.min(...nodes.map(n => n.x - n.width / 2));
  const right = Math.max(...nodes.map(n => n.x + n.width / 2));
  const top = Math.min(...nodes.map(n => n.y - cardHeight(n) / 2));
  const bottom = Math.max(...nodes.map(n => n.y + cardHeight(n) / 2));
  return {x: (left + right) / 2, y: (top + bottom) / 2, zoom: Math.min(0.96, viewport.width / (right - left + padding), viewport.height / (bottom - top + padding))};
}

export function travelWindow(nodes: CameraNode[], index: number, duration: number) {
  const node = nodes[index];
  const previous = nodes[index - 1];
  const nextStart = nodes[index + 1]?.start ?? duration;
  const key = node.camera_move as keyof typeof catalog.camera_moves;
  const requested = node.camera_frames ?? catalog.camera_moves[key]?.duration_frames ?? 66;
  // Keep travel brief and centered near the asset cue. Both the departing and
  // arriving cards then get a longer steady close-up, even on short beats.
  const lead = previous ? Math.min(requested * 0.20, (node.start - previous.start) * 0.14) : 0;
  const tail = Math.max(1, Math.min(requested * 0.20, (nextStart - node.start) * 0.12));
  return {start: node.start - lead, end: node.start + tail};
}

function travel(from: CameraNode, to: CameraNode, t: number): Camera {
  const a = focusCamera(from), b = focusCamera(to);
  const p = smooth(t);
  const dx = b.x - a.x, dy = b.y - a.y;
  const distance = Math.max(1, Math.hypot(dx, dy));
  const bell = Math.sin(Math.PI * clamp(t)) ** 2;
  const key = to.camera_move ?? 'pan';
  const xProgress = key === 'crane' ? smooth(clamp(t) ** 1.22) : p;
  const yProgress = key === 'crane' ? smooth(1 - (1 - clamp(t)) ** 1.22) : p;
  const bend = key === 'arc' ? Math.min(180, distance * 0.12) * bell : 0;
  const bridge = fitCamera([from, to], 600).zoom * (key === 'overview' ? 0.70 : key === 'dolly' ? 0.82 : 1);
  // Pull back early enough to show BOTH nodes and their connecting route;
  // travel through that shared view before settling onto the destination.
  const pullback = t < 0.32 ? smooth(t / 0.32) : t > 0.68 ? smooth((1 - t) / 0.32) : 1;
  return {
    x: lerp(a.x, b.x, xProgress) - dy / distance * bend,
    y: lerp(a.y, b.y, yProgress) + dx / distance * bend,
    zoom: lerp(lerp(a.zoom, b.zoom, p), bridge, pullback),
  };
}

export function cameraAtFrame(nodes: CameraNode[], frame: number, duration: number): Camera {
  if (!nodes.length) return {x: 0, y: 0, zoom: 1};
  const first = focusCamera(nodes[0]);
  const firstTravel = nodes.length > 1 ? travelWindow(nodes, 1, duration).start : duration;
  const introEnd = Math.max(1, Math.min(48, firstTravel * 0.65));
  if (frame < introEnd) {
    const overview = fitCamera(nodes.slice(0, 3), 420);
    const p = smooth(frame / introEnd);
    return {x: lerp(overview.x, first.x, p), y: lerp(overview.y, first.y, p), zoom: lerp(overview.zoom, first.zoom, p)};
  }
  for (let i = 1; i < nodes.length; i++) {
    const window = travelWindow(nodes, i, duration);
    if (frame < window.start) return focusCamera(nodes[i - 1]);
    if (frame <= window.end) return travel(nodes[i - 1], nodes[i], (frame - window.start) / (window.end - window.start));
  }
  const last = focusCamera(nodes[nodes.length - 1]);
  const lastLanding = nodes.length > 1 ? travelWindow(nodes, nodes.length - 1, duration).end : introEnd;
  const outroStart = Math.max(lastLanding + 20, duration - 76);
  const p = smooth((frame - outroStart) / Math.max(1, duration - 1 - outroStart));
  const overview = fitCamera(nodes, 500);
  return {x: lerp(last.x, overview.x, p), y: lerp(last.y, overview.y, p), zoom: lerp(last.zoom, overview.zoom, p)};
}

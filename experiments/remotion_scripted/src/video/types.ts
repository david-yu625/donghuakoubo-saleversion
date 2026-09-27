export type Shot = {
  id: string;
  start: number;
  end: number;
  asset: string;
  x: number;
  y: number;
  width: number;
  height: number;
  title: string;
  voice: string;
  keyword: string;
  accent: string;
  camera_move?: string;
  camera_effect?: string;
  transition?: string;
  transition_frames?: number;
  image_animation?: string;
  image_animation_frames?: number;
  camera_frames?: number;
  keyword_delay_ratio?: number;
  mediaType?: 'image' | 'video';
  styleId?: string;
  cacheBust?: string;
};

export type Caption = {start: number; end: number; text: string};

export type Manifest = {
  contractVersion: string;
  visualStyle: string;
  infiniteCanvas: boolean;
  title: string;
  durationSeconds: number;
  shots: Shot[];
  captions: Caption[];
  audio: string;
  viewport: {width: number; height: number; headerHeight: number};
  world: {width: number; height: number};
  subtitleSafeArea: {left: number; right: number; bottom: number};
};

export const FPS = 30;
export const clamp = (n: number) => Math.max(0, Math.min(1, n));
export const smooth = (n: number) => {
  const t = clamp(n);
  return t * t * (3 - 2 * t);
};

export function assertManifest(project: Manifest): Manifest {
  if (!project.infiniteCanvas || !project.shots?.length || !project.viewport || !project.world) {
    throw new Error('Invalid Remotion manifest: infinite canvas, viewport, world and shots are required');
  }
  if (project.world.width <= project.viewport.width || project.world.height <= project.viewport.height) {
    throw new Error('Invalid Remotion manifest: world must exceed viewport');
  }
  for (const shot of project.shots) {
    if (!shot.asset || !shot.mediaType || !shot.styleId) throw new Error(`Invalid media contract for shot ${shot.id}`);
  }
  return project;
}

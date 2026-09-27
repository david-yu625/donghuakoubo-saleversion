import React from 'react';
import {interpolate, spring, useCurrentFrame} from 'remotion';
import type {Manifest, Shot} from '../types';
import {FPS} from '../types';
import {cameraFor} from '../camera';

type Rect = {left: number; top: number; width: number; height: number};
type Anchor = Rect & {side: 'left' | 'right'; name: string};

const overlap = (a: Rect, b: Rect) => {
  const width = Math.max(0, Math.min(a.left + a.width, b.left + b.width) - Math.max(a.left, b.left));
  const height = Math.max(0, Math.min(a.top + a.height, b.top + b.height) - Math.max(a.top, b.top));
  return width * height;
};

function keywordAnchors(project: Manifest, shot: Shot, index: number, frame: number, width: number, height: number): Anchor[] {
  const camera = cameraFor(frame, project);
  const viewport = project.viewport;
  const card: Rect = {
    left: viewport.width / 2 + (shot.x - camera.x) * camera.zoom - shot.width * camera.zoom / 2,
    top: viewport.headerHeight + viewport.height / 2 + (shot.y - camera.y) * camera.zoom - shot.height * camera.zoom / 2,
    width: shot.width * camera.zoom,
    height: shot.height * camera.zoom,
  };
  const safe = {left: 72, right: viewport.width - 72, top: viewport.headerHeight + 28, bottom: viewport.headerHeight + viewport.height - 58};
  const yMid = Math.max(safe.top, Math.min(safe.bottom - height, card.top + card.height * 0.42 - height / 2));
  const yTop = Math.max(safe.top, Math.min(safe.bottom - height, card.top - height - 28));
  const yLow = Math.max(safe.top, Math.min(safe.bottom - height, card.top + card.height + 28));
  const left = safe.left;
  const right = safe.right - width;
  const rightSide = (top: number, name: string): Anchor => ({left: right, top, width, height, side: 'right', name});
  const leftSide = (top: number, name: string): Anchor => ({left, top, width, height, side: 'left', name});
  const orders: Anchor[][] = [
    [rightSide(yMid, 'right-mid'), rightSide(yTop, 'right-top'), leftSide(yMid, 'left-mid'), leftSide(yTop, 'left-top'), rightSide(yLow, 'right-low'), leftSide(yLow, 'left-low')],
    [leftSide(yMid, 'left-mid'), leftSide(yTop, 'left-top'), rightSide(yMid, 'right-mid'), rightSide(yTop, 'right-top'), leftSide(yLow, 'left-low'), rightSide(yLow, 'right-low')],
    [rightSide(yTop, 'right-top'), leftSide(yTop, 'left-top'), rightSide(yMid, 'right-mid'), leftSide(yMid, 'left-mid'), rightSide(yLow, 'right-low'), leftSide(yLow, 'left-low')],
  ];
  const preferred = orders[index % orders.length];
  const scored = preferred.map((anchor, rank) => ({anchor, rank, overlap: overlap(anchor, card)}));
  scored.sort((a, b) => (a.overlap - b.overlap) * 1000 + a.rank - b.rank);
  return scored.map(item => item.anchor);
}

export const KeywordLayer: React.FC<{project: Manifest}> = ({project}) => {
  const frame = useCurrentFrame();
  const time = frame / FPS;
  const shotIndex = project.shots.findIndex(item => time >= item.start && time < item.end);
  const shot = shotIndex >= 0 ? project.shots[shotIndex] : undefined;
  if (!shot?.keyword) return null;

  const cueFrame = Math.min(
    shot.end * FPS - 26,
    Math.max(shot.start * FPS + 8, shot.start * FPS + (shot.end - shot.start) * FPS * (shot.keyword_delay_ratio ?? 0.3)),
  );
  const local = Math.max(0, frame - cueFrame);
  const enter = spring({frame: local, fps: FPS, config: {damping: 14, stiffness: 155, mass: 0.72}});
  const fadeOut = interpolate(time, [shot.end - 0.42, shot.end - 0.08], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const progress = Math.min(enter, fadeOut);
  const visualStyle = shotIndex % 3;
  const boxWidth = Math.min(500, Math.max(390, 250 + shot.keyword.length * 56));
  const boxHeight = visualStyle === 1 ? 144 : 132;
  const anchor = keywordAnchors(project, shot, shotIndex, frame, boxWidth, boxHeight)[0];
  const translateX = anchor.side === 'right' ? (1 - enter) * 74 : -(1 - enter) * 74;
  const translateY = visualStyle === 2 ? (1 - enter) * 28 : visualStyle === 1 ? (1 - enter) * 12 : 0;
  const rotate = visualStyle === 1 ? (1 - enter) * -5 : visualStyle === 2 ? (1 - enter) * 3 : 0;
  const align = anchor.side === 'right' ? 'right' as const : 'left' as const;
  const textStyle = {
    position: 'relative' as const,
    fontFamily: '得意黑, 庞门正道标题体, Microsoft YaHei, sans-serif',
    fontSize: visualStyle === 1 ? 58 : 64,
    lineHeight: 1.05,
    fontWeight: 900,
    letterSpacing: 1,
    color: '#182d3a',
    textShadow: '0 3px 0 #fff, 0 7px 18px rgba(24,59,77,0.14)',
  };
  return <div style={{position: 'absolute', left: anchor.left, top: anchor.top, width: anchor.width, height: anchor.height, pointerEvents: 'none', opacity: progress, transform: `translate(${translateX}px, ${translateY}px) rotate(${rotate}deg)`, transformOrigin: anchor.side === 'right' ? '100% 50%' : '0 50%'}}>
    <div style={{display: 'flex', flexDirection: 'column', alignItems: align === 'right' ? 'flex-end' : 'flex-start', gap: 8}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 10, color: shot.accent, fontSize: 15, fontWeight: 800, letterSpacing: 3}}>
        {align === 'right' && <span style={{width: 46, height: 4, background: shot.accent, borderRadius: 4, transform: `scaleX(${enter})`, transformOrigin: '100% 50%'}} />}
        <span>重点 {String(shotIndex + 1).padStart(2, '0')}</span>
        {align === 'left' && <span style={{width: 46, height: 4, background: shot.accent, borderRadius: 4, transform: `scaleX(${enter})`, transformOrigin: '0 50%'}} />}
      </div>
      <div style={textStyle}>
        {visualStyle === 0 && <span style={{position: 'absolute', left: '-3%', right: '-3%', bottom: 2, height: 25, background: shot.accent, opacity: 0.34, transform: `skewX(-12deg) scaleX(${enter})`, transformOrigin: align === 'right' ? '100% 50%' : '0 50%', borderRadius: 5}} />}
        <span style={{position: 'relative'}}>{shot.keyword}</span>
        {visualStyle === 1 && <span style={{position: 'absolute', left: -15, right: -15, top: '49%', height: 16, border: `4px solid ${shot.accent}`, borderTopColor: 'transparent', borderRadius: '50%', transform: `scaleX(${enter}) rotate(-3deg)`, opacity: 0.86}} />}
        {visualStyle === 2 && <span style={{position: 'absolute', left: '3%', right: '3%', bottom: -14, height: 8, background: shot.accent, transform: `scaleX(${enter}) rotate(-1deg)`, transformOrigin: align === 'right' ? '100% 50%' : '0 50%', borderRadius: 8, boxShadow: `0 0 8px ${shot.accent}88`}} />}
      </div>
    </div>
  </div>;
};

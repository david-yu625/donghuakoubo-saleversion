import React from 'react';
import {Audio} from '@remotion/media';
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import manifest from '../../public/manifest.json';

type NodeSpec = {
  asset: string;
  x: number;
  y: number;
  width: number;
  start: number;
  eyebrow: string;
  headline: string;
  accent: string;
  rotate?: number;
  effect?: 'reveal' | 'process' | 'timeline' | 'compare' | 'spotlight' | 'data' | 'orbit' | 'parallax' | 'scan' | 'burst';
  layout?: 'center' | 'wide' | 'low' | 'high' | 'close';
  end?: number;
  shot_id?: string;
};

const projectManifest = manifest as typeof manifest & {nodes?: NodeSpec[]};
const nodes: NodeSpec[] = projectManifest.nodes ?? [];

const shotGroups = nodes.reduce<Array<{start: number; end: number; nodes: NodeSpec[]}>>((groups, node) => {
  const previous = groups[groups.length - 1];
  const sameShot = previous && node.shot_id && previous.nodes[0]?.shot_id === node.shot_id;
  const overlaps = previous && node.start < previous.end;
  // Prefer explicit shot ownership. Time overlap is only a fallback for
  // legacy manifests that do not carry shot IDs.
  if (previous && (sameShot || (!node.shot_id && overlaps))) {
    previous.nodes.push(node);
    previous.end = Math.max(previous.end, node.end ?? node.start + 120);
  } else {
    groups.push({start: node.start, end: node.end ?? node.start + 120, nodes: [node]});
  }
  return groups;
}, []);

const cameraStops = shotGroups.map((group, index) => {
  const left = Math.min(...group.nodes.map((node) => node.x - node.width / 2));
  const right = Math.max(...group.nodes.map((node) => node.x + node.width / 2));
  const top = Math.min(...group.nodes.map((node) => node.y - 330));
  const bottom = Math.max(...group.nodes.map((node) => node.y + 330));
  const center = (left + right) / 2;
  const centerY = (top + bottom) / 2;
  const effects = new Set(group.nodes.map((node) => node.effect));
  const span = Math.max(right - left, bottom - top);
  const layout = group.nodes[0]?.layout ?? 'center';
  const zoom = effects.has('spotlight') || layout === 'close'
    ? 0.98
    : effects.has('data') || layout === 'wide'
      ? 0.84
      : Math.min(0.98, 1550 / span);
  return {
    frame: group.start,
    // The world container already starts at the viewport center (960, 540),
    // so the camera origin is simply the desired world-space group center.
    x: center,
    y: centerY,
    zoom,
  };
});

const cameraValue = (frame: number, key: 'x' | 'y' | 'zoom') => {
  if (!cameraStops.length) return key === 'zoom' ? 0.9 : 0;
  const index = Math.max(0, cameraStops.findIndex((stop, i) => frame < (cameraStops[i + 1]?.frame ?? Number.POSITIVE_INFINITY)));
  const current = cameraStops[index];
  const next = cameraStops[index + 1];
  if (!next) return current[key];
  const transition = Math.min(90, Math.max(1, next.frame - current.frame));
  const end = next.frame;
  const start = Math.max(current.frame, end - transition);
  if (frame < start) return current[key];
  return interpolate(frame, [start, end], [current[key], next[key]], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic)});
};

const PaperGrid: React.FC = () => (
  <AbsoluteFill
    style={{
      backgroundColor: '#f7f7f3',
      backgroundImage:
        'linear-gradient(rgba(24,32,43,.055) 1px, transparent 1px), linear-gradient(90deg, rgba(24,32,43,.055) 1px, transparent 1px)',
      backgroundSize: '80px 80px',
    }}
  />
);

const WorldPath: React.FC<{frame: number}> = ({frame}) => {
  const progress = interpolate(frame, [25, Math.max(80, Math.round(manifest.durationSeconds * 30) - 50)], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const path = nodes.length
    ? `M ${nodes[0].x} ${nodes[0].y} ${nodes.slice(1).map((node) => `L ${node.x} ${node.y}`).join(' ')}`
    : 'M 0 0 L 1000 0';
  return (
    <svg width="11000" height="6000" viewBox="0 0 11000 6000" style={{position: 'absolute', left: -1000, top: -1000, overflow: 'visible'}}>
      <path
        d={path}
        fill="none"
        stroke="#1c2430"
        strokeWidth="8"
        strokeLinecap="round"
        strokeDasharray="24 22"
        pathLength={1}
        strokeDashoffset={1 - progress}
        opacity={0.22}
      />
      <path
        d={path}
        fill="none"
        stroke="#ff4d4d"
        strokeWidth="4"
        pathLength={1}
        strokeDasharray={1}
        strokeDashoffset={1 - progress}
      />
    </svg>
  );
};

const EffectOverlay: React.FC<{node: NodeSpec; localFrame: number; progress: number}> = ({node, localFrame, progress}) => {
  const effect = node.effect ?? 'reveal';
  const pulse = 0.5 + 0.5 * Math.sin(localFrame / 7);
  if (effect === 'process') {
    return (
      <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none" style={{position: 'absolute', inset: 0, overflow: 'visible', pointerEvents: 'none'}}>
        <path d="M 8 78 C 22 58, 28 28, 50 34 S 76 70, 92 20" fill="none" stroke={node.accent} strokeWidth="1.2" strokeDasharray="5 4" pathLength={1} strokeDashoffset={1 - progress} opacity={0.9} />
        <circle cx={8 + progress * 84} cy={78 - Math.sin(progress * Math.PI) * 43} r="2.8" fill={node.accent} opacity={progress} />
        <path d="M 92 20 l -7 1 l 4 5" fill="none" stroke={node.accent} strokeWidth="1.4" opacity={progress} />
      </svg>
    );
  }
  if (effect === 'timeline') {
    return (
      <div style={{position: 'absolute', left: '7%', right: '7%', bottom: '4%', height: 54, opacity: progress}}>
        <div style={{position: 'absolute', left: 0, right: 0, top: 20, height: 4, background: node.accent, opacity: 0.45}} />
        {[0, 0.5, 1].map((stop, index) => (
          <div key={stop} style={{position: 'absolute', left: `${stop * 100}%`, top: 9, transform: 'translateX(-50%)', width: 24, height: 24, borderRadius: '50%', background: '#f7f7f3', border: `5px solid ${node.accent}`, boxShadow: '0 3px 8px rgba(21,27,36,.18)'}}>
            <div style={{position: 'absolute', top: 27, left: '50%', transform: 'translateX(-50%)', color: '#151b24', fontSize: 18, fontWeight: 900, whiteSpace: 'nowrap'}}>{index === 0 ? '过去' : index === 1 ? '转折' : '现在'}</div>
          </div>
        ))}
      </div>
    );
  }
  if (effect === 'compare') {
    const split = interpolate(localFrame, [0, 22], [0.08, 0.54], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
    return (
      <>
        <div style={{position: 'absolute', left: `${split * 100}%`, top: 0, bottom: 0, width: 6, transform: 'translateX(-50%)', background: '#fff', boxShadow: `0 0 0 3px ${node.accent}, 0 0 22px ${node.accent}`, opacity: progress}} />
        <div style={{position: 'absolute', left: `${Math.max(2, split * 100 - 18)}%`, top: 16, color: '#fff', background: node.accent, padding: '5px 12px', fontSize: 18, fontWeight: 900, opacity: progress}}>对比</div>
      </>
    );
  }
  if (effect === 'spotlight') {
    return (
      <>
        <div style={{position: 'absolute', left: '50%', top: '50%', width: `${62 + pulse * 8}%`, height: `${62 + pulse * 8}%`, transform: 'translate(-50%, -50%)', border: `5px solid ${node.accent}`, borderRadius: '50%', opacity: 0.34 * progress, boxShadow: `0 0 45px ${node.accent}`}} />
        <div style={{position: 'absolute', inset: 0, background: `radial-gradient(circle at 50% 50%, transparent 36%, rgba(21,27,36,${0.25 * progress}) 72%)`, opacity: progress}} />
      </>
    );
  }
  if (effect === 'data') {
    const grow = interpolate(localFrame, [0, 24], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
    return (
      <div style={{position: 'absolute', right: '-196px', top: '10%', width: 178, height: 108, padding: '12px 10px 8px', display: 'flex', alignItems: 'flex-end', gap: 10, background: 'rgba(247,247,243,.92)', border: `3px solid ${node.accent}`, boxShadow: `8px 8px 0 ${node.accent}44`, opacity: progress}}>
        {[0.36, 0.62, 0.9].map((height, index) => (
          <div key={height} style={{flex: 1, height: `${height * 100}%`, background: `linear-gradient(180deg, ${node.accent}, ${node.accent}55)`, border: `2px solid ${node.accent}`, transformOrigin: 'bottom', transform: `scaleY(${grow})`}}>
            <div style={{position: 'relative', top: -25, textAlign: 'center', color: node.accent, fontSize: 18, fontWeight: 900}}>{['基准', '提升', '峰值'][index]}</div>
          </div>
        ))}
      </div>
    );
  }
  if (effect === 'orbit') {
    const angle = interpolate(localFrame, [0, 60], [-18, 360], {extrapolateLeft: 'clamp', extrapolateRight: 'extend'});
    return (
      <>
        <div style={{position: 'absolute', left: '50%', top: '50%', width: '64%', height: '64%', transform: `translate(-50%, -50%) rotate(${angle}deg)`, border: `4px solid ${node.accent}66`, borderTopColor: node.accent, borderRadius: '50%', opacity: 0.9 * progress}} />
        <div style={{position: 'absolute', left: '50%', top: '50%', width: '80%', height: '80%', transform: `translate(-50%, -50%) rotate(${-angle * 0.7}deg)`, border: `3px dashed ${node.accent}88`, borderRadius: '50%', opacity: 0.5 * progress}} />
        <div style={{position: 'absolute', left: `${50 + 32 * Math.cos(angle * Math.PI / 180)}%`, top: `${50 + 32 * Math.sin(angle * Math.PI / 180)}%`, width: 20, height: 20, transform: 'translate(-50%, -50%)', background: node.accent, borderRadius: '50%', boxShadow: `0 0 24px ${node.accent}`, opacity: progress}} />
      </>
    );
  }
  if (effect === 'parallax') {
    const drift = Math.sin(localFrame / 13) * 12;
    return (
      <>
        <div style={{position: 'absolute', inset: '6%', transform: `translate(${drift}px, ${-drift * 0.45}px)`, border: `4px solid ${node.accent}88`, boxShadow: `14px 14px 0 ${node.accent}33`, opacity: 0.8 * progress}} />
        <div style={{position: 'absolute', left: '10%', right: '10%', top: '50%', height: 5, background: node.accent, opacity: 0.5 * progress, transform: `translateY(${drift}px)`}} />
      </>
    );
  }
  if (effect === 'scan') {
    const scanY = (localFrame * 4) % 108;
    return (
      <>
        <div style={{position: 'absolute', inset: 0, background: `repeating-linear-gradient(0deg, transparent 0 18px, ${node.accent}18 19px, transparent 21px)`, opacity: 0.55 * progress}} />
        <div style={{position: 'absolute', left: 0, right: 0, top: `${scanY}%`, height: 8, background: node.accent, boxShadow: `0 0 28px ${node.accent}`, opacity: 0.8 * progress, transform: 'translateY(-50%)'}} />
      </>
    );
  }
  if (effect === 'burst') {
    return (
      <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none" style={{position: 'absolute', inset: 0, overflow: 'visible', pointerEvents: 'none', opacity: progress}}>
        {[0, 45, 90, 135, 180, 225, 270, 315].map((angle) => {
          const length = 34 + 8 * Math.sin((localFrame + angle) / 12);
          const radians = angle * Math.PI / 180;
          return <line key={angle} x1="50" y1="50" x2={50 + Math.cos(radians) * length} y2={50 + Math.sin(radians) * length} stroke={node.accent} strokeWidth="1.3" strokeDasharray="4 3" opacity="0.8" />;
        })}
      </svg>
    );
  }
  return (
    <div style={{position: 'absolute', left: 0, right: 0, top: `${progress * 100}%`, height: 8, background: node.accent, boxShadow: `0 0 22px ${node.accent}`, opacity: 0.75, transform: 'translateY(-50%)'}} />
  );
};

const KnowledgeNode: React.FC<{node: NodeSpec; index: number; cameraX: number; cameraY: number}> = ({node, index, cameraX, cameraY}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const rawEntrance = spring({fps, frame: frame - node.start + 1, config: {damping: 16, stiffness: 95, mass: 0.8}});
  const entrance = frame < node.start ? 0 : interpolate(rawEntrance, [0, 1], [0.28, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const localFrame = Math.max(0, frame - node.start);
  const effectProgress = interpolate(localFrame, [0, 20], [0.35, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const float = Math.sin((frame + index * 33) / 28) * 9;
  const marker = interpolate(entrance, [0, 1], [0.2, 1]);
  const distance = Math.hypot(node.x - cameraX, node.y - cameraY);
  const focusOpacity = interpolate(distance, [800, 1250, 1900], [1, 0.14, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const exit = node.end === undefined
    ? 1
    : interpolate(frame, [node.end - 8, node.end], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const isActive = frame >= node.start && frame <= (node.end ?? Number.POSITIVE_INFINITY);
  return (
    <div
      style={{
        position: 'absolute',
        left: node.x,
        top: node.y + float,
        width: node.width,
        transform: `translate(-50%, -50%) scale(${interpolate(entrance, [0, 1], [0.72, 1])}) rotate(${node.rotate ?? 0}deg)`,
        opacity: entrance * exit * focusOpacity * (isActive ? 1 : 0),
        transformOrigin: 'center',
      }}
    >
      <div style={{position: 'relative'}}>
        <div
          style={{
            position: 'absolute',
            left: '50%',
            top: '50%',
            width: '78%',
            height: '72%',
            transform: 'translate(-50%, -50%)',
            background: node.accent,
            filter: 'blur(70px)',
            opacity: 0.14 * marker,
            borderRadius: '50%',
          }}
        />
        <div style={{position: 'relative', overflow: 'visible', clipPath: node.effect === 'reveal' ? `inset(0 ${(1 - effectProgress) * 100}% 0 0)` : undefined}}>
          <Img
            src={staticFile(`assets/${node.asset}`)}
            style={{
              width: '100%',
              display: 'block',
              filter: 'drop-shadow(0 24px 20px rgba(16,25,38,.15))',
              transform: node.effect === 'spotlight'
                ? `scale(${1 + 0.035 * Math.sin(localFrame / 10)})`
                : node.effect === 'orbit'
                  ? `scale(${1 + 0.018 * Math.sin(localFrame / 8)}) rotate(${Math.sin(localFrame / 18) * 1.2}deg)`
                  : node.effect === 'parallax'
                    ? `translateY(${Math.sin(localFrame / 13) * 8}px) scale(1.015)`
                    : undefined,
            }}
          />
          {node.effect === 'compare' && (
            <Img
              src={staticFile(`assets/${node.asset}`)}
              style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', filter: 'grayscale(1) contrast(.85)', opacity: 0.82, clipPath: 'inset(0 50% 0 0)'}}
            />
          )}
          <EffectOverlay node={node} localFrame={localFrame} progress={effectProgress} />
        </div>
      </div>
    </div>
  );
};

const HeroIntro: React.FC = () => {
  const frame = useCurrentFrame();
  const exit = interpolate(frame, [20, 55], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const x = interpolate(frame, [0, 55], [0, -260]);
  return (
    <div style={{position: 'absolute', left: -760 + x, top: -260, width: 950, opacity: exit}}>
      <div style={{fontSize: 28, color: '#ff4d4d', fontWeight: 900}}>ORIGIN / 1956</div>
      <div style={{fontSize: 104, lineHeight: 1.02, fontWeight: 950, color: '#151b24', marginTop: 16}}>
        {manifest.title}
        <br />
        从一个问题开始
      </div>
      <div style={{width: 580, height: 12, background: '#ff4d4d', marginTop: 34}} />
    </div>
  );
};

const Caption: React.FC = () => {
  const frame = useCurrentFrame();
  const time = frame / 30;
  const caption = manifest.captions.find((item) => time >= item.start && time < item.end);
  if (!caption) return null;
  const localFrame = frame - Math.round(caption.start * 30);
  const reveal = interpolate(localFrame, [0, 10], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <div style={{position: 'absolute', left: 126, right: 126, bottom: 62, display: 'flex', justifyContent: 'center'}}>
      <div
        style={{
          maxWidth: 1540,
          padding: '18px 34px 20px',
          background: 'rgba(19,25,34,.94)',
          color: '#fff',
          fontSize: 36,
          lineHeight: 1.35,
          fontWeight: 760,
          textAlign: 'center',
          clipPath: `inset(0 ${(1 - reveal) * 100}% 0 0)`,
          boxShadow: '10px 10px 0 rgba(255,77,77,.85)',
        }}
      >
        {caption.text}
      </div>
    </div>
  );
};

const Hud: React.FC = () => {
  const frame = useCurrentFrame();
  const currentNode = [...nodes].reverse().find((node) => frame >= node.start && frame <= (node.end ?? Number.POSITIVE_INFINITY));
  const year = currentNode?.eyebrow ?? 'ORIGIN';
  const progress = Math.min(1, frame / Math.max(1, Math.round(manifest.durationSeconds * 30)));
  return (
    <>
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: 0,
          height: 108,
          background: 'rgba(247,247,243,.96)',
          boxShadow: '0 12px 28px rgba(20,28,38,.035)',
        }}
      />
      <div style={{position: 'absolute', left: 58, top: 42, color: '#151b24', fontSize: 20, fontWeight: 900}}>
        HARD DISK ARCHIVE&nbsp;&nbsp;/&nbsp;&nbsp;01
      </div>
      <div style={{position: 'absolute', right: 58, top: 38, color: '#151b24', fontSize: 26, fontWeight: 950}}>{year}</div>
      <div style={{position: 'absolute', left: 58, right: 58, top: 82, height: 4, background: 'rgba(21,27,36,.12)'}}>
        <div style={{height: '100%', width: `${progress * 100}%`, background: '#ff4d4d'}} />
      </div>
    </>
  );
};

export const InfiniteCanvas: React.FC = () => {
  const frame = useCurrentFrame();
  const cameraX = cameraValue(frame, 'x');
  const cameraY = cameraValue(frame, 'y');
  const zoom = cameraValue(frame, 'zoom');
  return (
    <AbsoluteFill style={{fontFamily: 'PingFang SC, Microsoft YaHei, sans-serif', overflow: 'hidden'}}>
      <PaperGrid />
      <div
        style={{
          position: 'absolute',
          left: 960,
          top: 540,
          width: 1,
          height: 1,
          transform: `scale(${zoom}) translate(${-cameraX}px, ${-cameraY}px)`,
          transformOrigin: '0 0',
        }}
      >
        <WorldPath frame={frame} />
        <HeroIntro />
        {nodes.map((node, index) => (
          <KnowledgeNode
            key={node.asset}
            node={node}
            index={index}
            cameraX={cameraX}
            cameraY={cameraY}
          />
        ))}
      </div>
      <Hud />
      <Caption />
      <Audio src={staticFile('audio/narration.wav')} volume={1} />
    </AbsoluteFill>
  );
};

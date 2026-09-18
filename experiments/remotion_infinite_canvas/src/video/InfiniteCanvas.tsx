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
};

const projectManifest = manifest as typeof manifest & {nodes?: NodeSpec[]};
const nodes: NodeSpec[] = projectManifest.nodes ?? [];

const cameraStops = nodes.reduce<Array<{frame: number; x: number; y: number; zoom: number}>>(
  (stops, node, index) => {
    const previous = stops[stops.length - 1];
    const frame = Math.max(node.start, (previous?.frame ?? -1) + 1);
    stops.push({
      frame,
      x: node.x,
      y: node.y,
      zoom: index % 3 === 0 ? 1.04 : index % 3 === 1 ? 1.12 : 0.9,
    });
    return stops;
  }, [
    {frame: 0, x: (nodes[0]?.x ?? 850) - 700, y: (nodes[0]?.y ?? 520) - 250, zoom: 0.78},
  ],
);

const cameraValue = (frame: number, key: 'x' | 'y' | 'zoom') =>
  interpolate(
    frame,
    cameraStops.map((stop) => stop.frame),
    cameraStops.map((stop) => stop[key]),
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic)},
  );

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

const KnowledgeNode: React.FC<{node: NodeSpec; index: number; cameraX: number; cameraY: number}> = ({node, index, cameraX, cameraY}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const entrance = spring({fps, frame: frame - node.start, config: {damping: 16, stiffness: 95, mass: 0.8}});
  const float = Math.sin((frame + index * 33) / 28) * 9;
  const marker = interpolate(entrance, [0, 1], [0.2, 1]);
  const distance = Math.hypot(node.x - cameraX, node.y - cameraY);
  const focusOpacity = interpolate(distance, [800, 1250, 1900], [1, 0.14, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return (
    <div
      style={{
        position: 'absolute',
        left: node.x,
        top: node.y + float,
        width: node.width,
        transform: `translate(-50%, -50%) scale(${interpolate(entrance, [0, 1], [0.72, 1])}) rotate(${node.rotate ?? 0}deg)`,
        opacity: entrance * focusOpacity,
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
        <Img
          src={staticFile(`assets/${node.asset}`)}
          style={{width: '100%', display: 'block', filter: 'drop-shadow(0 24px 20px rgba(16,25,38,.15))'}}
        />
        <div
          style={{
            position: 'absolute',
            left: index % 2 === 0 ? 24 : 'auto',
            right: index % 2 === 0 ? 'auto' : 24,
            bottom: -92,
            color: '#151b24',
            textAlign: index % 2 === 0 ? 'left' : 'right',
            whiteSpace: 'nowrap',
          }}
        >
          <div style={{fontSize: 24, fontWeight: 800, letterSpacing: 0, color: node.accent}}>{node.eyebrow}</div>
          <div style={{fontSize: 48, fontWeight: 950, letterSpacing: 0, marginTop: 6}}>{node.headline}</div>
        </div>
      </div>
    </div>
  );
};

const HeroIntro: React.FC = () => {
  const frame = useCurrentFrame();
  const exit = interpolate(frame, [30, 110], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const x = interpolate(frame, [0, 100], [0, -260]);
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
  const currentNode = [...nodes].reverse().find((node) => frame >= node.start);
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

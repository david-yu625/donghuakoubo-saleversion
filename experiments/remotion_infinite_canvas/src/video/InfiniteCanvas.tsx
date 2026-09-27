import React from 'react';
import {Audio} from '@remotion/media';
import {AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame} from 'remotion';
import manifest from '../../public/manifest.json';
import {effectDuration, imageAnimationStyle, transitionStyles} from './effects';
import {cameraAtFrame, cardHeight, viewport} from './camera';
import {extractKeywords} from './keywords';

type NodeSpec = {asset: string; x: number; y: number; width: number; start: number; end?: number; shot_id?: string; headline?: string; accent: string; transition?: string; transition_frames?: number; image_animation?: string; image_animation_frames?: number; camera_move?: string; camera_frames?: number};
type CaptionSpec = {start: number; end: number; text: string; shot_id?: string};
type ManifestSpec = {title: string; durationSeconds: number; captions: CaptionSpec[]; chapters?: CaptionSpec[]; nodes?: NodeSpec[]};
const project = manifest as ManifestSpec;
const nodes = [...(project.nodes ?? [])].sort((a, b) => a.start - b.start);

const World: React.FC = () => {
  const frame = useCurrentFrame();
  const duration = Math.round(project.durationSeconds * 30);
  const camera = cameraAtFrame(nodes, frame, duration);
  const activeIndex = Math.max(0, nodes.reduce((found, node, i) => frame >= node.start ? i : found, -1));
  const path = nodes.map((node, index) => `${index ? 'L' : 'M'} ${node.x} ${node.y}`).join(' ');
  const left = Math.min(0, ...nodes.map(n => n.x - n.width)) - 2400;
  const top = Math.min(0, ...nodes.map(n => n.y - cardHeight(n))) - 2400;
  const right = Math.max(0, ...nodes.map(n => n.x + n.width)) + 2400;
  const bottom = Math.max(0, ...nodes.map(n => n.y + cardHeight(n))) + 2400;
  return (
    <AbsoluteFill style={{overflow: 'hidden', top: 192, height: viewport.height, background: '#f4f8fa'}}>
      <div style={{position: 'absolute', left: viewport.width / 2, top: viewport.height / 2, transform: `scale(${camera.zoom}) translate(${-camera.x}px, ${-camera.y}px)`, transformOrigin: '0 0'}}>
        <div style={{position: 'absolute', left, top, width: right - left, height: bottom - top, backgroundImage: 'radial-gradient(#b3c7d2 2px, transparent 2px), linear-gradient(#dce7ec 1px, transparent 1px), linear-gradient(90deg, #dce7ec 1px, transparent 1px)', backgroundSize: '96px 96px, 480px 480px, 480px 480px'}} />
        <svg width="1" height="1" style={{position: 'absolute', overflow: 'visible', pointerEvents: 'none'}}>
          <path d={path} fill="none" stroke="#8db4c5" strokeWidth="6" strokeDasharray="16 14" strokeLinejoin="round" />
          <path d={nodes.slice(0, activeIndex + 1).map((node, i) => `${i ? 'L' : 'M'} ${node.x} ${node.y}`).join(' ')} fill="none" stroke="#237d9c" strokeWidth="7" strokeLinejoin="round" />
        </svg>
        {nodes.map((node, index) => {
          const nextStart = nodes[index + 1]?.start ?? duration;
          const elapsed = frame - node.start;
          const animationFrames = Math.max(1, Math.min(node.image_animation_frames ?? effectDuration('image_animations', node.image_animation), nextStart - node.start - 1));
          const transitionFrames = Math.max(1, Math.min(node.transition_frames ?? effectDuration('transitions', node.transition), nextStart - node.start - 1));
          const reveal = Math.max(0, Math.min(1, elapsed / transitionFrames));
          const active = index === activeIndex;
          const opacity = elapsed < 0 ? 0.46 : active ? 1 : 0.83;
          return (
            <div key={node.asset} style={{position: 'absolute', left: node.x, top: node.y, width: node.width, height: cardHeight(node), transform: 'translate(-50%, -50%)', opacity, background: '#fff', borderRadius: 8, boxShadow: active ? '0 0 0 5px #237d9c, 0 16px 36px #183b4d24' : '0 10px 28px #183b4d18'}}>
              <div style={{position: 'absolute', left: 0, top: -48, color: active ? '#176983' : '#627f8e', fontSize: 28, fontWeight: 700, whiteSpace: 'nowrap'}}>{String(index + 1).padStart(2, '0')} · {node.headline ?? ''}</div>
              <div style={{position: 'relative', width: '100%', height: '100%', overflow: 'hidden', borderRadius: 8}}>
                {elapsed >= 0 && elapsed < Math.max(animationFrames, transitionFrames) && <Img src={staticFile(`assets/${node.asset}`)} delayRenderRetries={2} style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', opacity: 0.46 * (1 - Math.min(1, elapsed / Math.max(animationFrames, transitionFrames)))}} />}
                <div style={{position: 'relative', width: '100%', height: '100%', ...(elapsed >= 0 && index > 0 ? transitionStyles(node.transition, reveal).incoming : {})}}>
                  <Img src={staticFile(`assets/${node.asset}`)} delayRenderRetries={2} style={{display: 'block', width: '100%', height: '100%', objectFit: 'contain', ...(elapsed >= 0 ? imageAnimationStyle(node.image_animation, elapsed / animationFrames) : {})}} />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const Caption: React.FC = () => {
  const time = useCurrentFrame() / 30;
  const caption = project.captions.find((item) => time >= item.start && time < item.end);
  if (!caption) return null;
  return (
    <div style={{position: 'absolute', left: 140, right: 140, bottom: 42, height: 90, display: 'flex', justifyContent: 'center', alignItems: 'center'}}>
      <div style={{maxWidth: '100%', padding: '12px 26px', borderRadius: 8, background: '#18212be8', color: '#fff', fontSize: 40, fontWeight: 600, lineHeight: 1.4, textAlign: 'center'}}>
        {caption.text}
      </div>
    </div>
  );
};

const KeywordSpotlight: React.FC = () => {
  const frame = useCurrentFrame();
  const time = frame / 30;
  const chapterIndex = project.chapters?.findIndex((item) => time >= item.start && time < item.end) ?? -1;
  const chapter = chapterIndex >= 0 ? project.chapters?.[chapterIndex] : undefined;
  if (!chapter) return null;
  const chapterCaptions = project.captions.filter((item) => item.start < chapter.end && item.end > chapter.start);
  const keywords = extractKeywords([chapter.text, ...chapterCaptions.map((item) => item.text)].join(' '), 3);
  if (!keywords.length) return null;

  const positions = [
    {right: 112, top: 286, align: 'right' as const},
    {left: 112, top: 360, align: 'left' as const},
    {right: 132, top: 498, align: 'right' as const},
  ];
  const cues = keywords.map((keyword, index) => {
    const caption = chapterCaptions.find((item) => item.text.toLocaleLowerCase().includes(keyword.text.toLocaleLowerCase()));
    const start = caption?.start ?? chapter.start + index * 1.2;
    const next = keywords[index + 1];
    const nextCaption = next ? chapterCaptions.find((item) => item.text.toLocaleLowerCase().includes(next.text.toLocaleLowerCase())) : undefined;
    const end = Math.min(chapter.end, Math.max(start + 0.95, nextCaption ? nextCaption.start - 0.08 : start + 1.25));
    return {keyword, index, start, end};
  });
  const cue = cues.find((item) => time >= item.start && time < item.end);
  if (!cue) return null;
  const local = (time - cue.start) * 30;
  const inProgress = spring({frame: Math.max(0, local), fps: 30, config: {damping: 13, stiffness: 175, mass: 0.7}});
  const outProgress = interpolate(time, [cue.end - 0.28, cue.end], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const progress = Math.min(inProgress, outProgress);
  const position = positions[cue.index % positions.length];
  const style = cue.index % 3;
  const translateX = position.align === 'right' ? (1 - inProgress) * 46 : -(1 - inProgress) * 46;
  const translateY = style === 2 ? (1 - inProgress) * 28 : style === 1 ? (1 - inProgress) * 14 : 0;
  const rotate = style === 1 ? (1 - inProgress) * -7 : style === 2 ? (1 - inProgress) * 5 : 0;
  return (
    <div style={{position: 'absolute', ...position, width: 420, pointerEvents: 'none', opacity: progress, transform: 'translate(' + translateX + 'px, ' + translateY + 'px) rotate(' + rotate + 'deg)', transformOrigin: position.align === 'right' ? '100% 50%' : '0 50%'}}>
      <div style={{display: 'flex', flexDirection: 'column', alignItems: position.align === 'right' ? 'flex-end' : 'flex-start', gap: 8}}>
        <div style={{display: 'flex', alignItems: 'center', gap: 10, color: cue.keyword.color, fontSize: 16, fontWeight: 800, letterSpacing: 3}}>
          {position.align === 'right' && <span style={{width: 42, height: 3, background: cue.keyword.color, boxShadow: '0 0 14px ' + cue.keyword.color}} />}
          <span>重点 {String(cue.index + 1).padStart(2, '0')}</span>
          {position.align === 'left' && <span style={{width: 42, height: 3, background: cue.keyword.color, boxShadow: '0 0 14px ' + cue.keyword.color}} />}
        </div>
        <div style={{position: 'relative', fontSize: style === 1 ? 58 : 64, lineHeight: 1.05, fontWeight: 900, letterSpacing: 2, color: '#183b4d', textShadow: '0 3px 0 #fff, 0 7px 18px rgba(24,59,77,0.16)'}}>
          <span>{cue.keyword.text}</span>
          {style === 1 && <span style={{position: 'absolute', left: -12, right: -12, top: '50%', height: 14, border: '4px solid ' + cue.keyword.color, borderTopColor: 'transparent', borderRadius: '50%', transform: 'scaleX(' + inProgress + ') rotate(-3deg)', opacity: 0.8}} />}
          {style === 2 && <span style={{position: 'absolute', left: '4%', right: '4%', bottom: -13, height: 7, background: cue.keyword.color, transform: 'scaleX(' + inProgress + ')', transformOrigin: position.align === 'right' ? '100% 50%' : '0 50%', borderRadius: 6, boxShadow: '0 0 12px ' + cue.keyword.color}} />}
        </div>
      </div>
    </div>
  );
};

const Header: React.FC = () => {
  const frame = useCurrentFrame();
  const chapter = project.chapters?.find((item) => frame / 30 >= item.start && frame / 30 < item.end);
  const progress = Math.min(1, frame / Math.max(1, Math.round(project.durationSeconds * 30) - 1));
  return (
    <>
      <div style={{position: 'absolute', left: 72, top: 32, color: '#687886', fontSize: 23, fontWeight: 500}}>{project.title}</div>
      <div style={{position: 'absolute', left: 72, top: 83, right: 72, display: 'flex', alignItems: 'center', gap: 20}}>
        <div style={{width: 5, height: 40, background: '#237d9c', borderRadius: 3}} />
        <div style={{color: '#182d3a', fontSize: 42, fontWeight: 750}}>{chapter?.text ?? project.title}</div>
      </div>
      <div style={{position: 'absolute', left: 72, right: 72, top: 161, height: 2, background: '#dfe5e9'}}>
        <div style={{height: '100%', width: `${progress * 100}%`, background: '#237d9c'}} />
      </div>
    </>
  );
};

export const InfiniteCanvas: React.FC = () => {
  return (
    <AbsoluteFill style={{fontFamily: 'Microsoft YaHei, PingFang SC, sans-serif', background: '#f8fafb', overflow: 'hidden'}}>
      <AbsoluteFill style={{backgroundImage: 'radial-gradient(#c7d4dd 1px, transparent 1px)', backgroundSize: '32px 32px', opacity: 0.32}} />
      <World />
      <Header />
      <KeywordSpotlight />
      <Caption />
      <Audio src={staticFile('audio/narration.wav')} volume={1} />
    </AbsoluteFill>
  );
};

import React from 'react';
import {Img, OffthreadVideo, staticFile} from 'remotion';
import type {Shot} from '../types';
import {clamp, FPS} from '../types';
import {effectDuration, imageAnimationStyle, transitionStyles} from '../effects';

type Props = {shot: Shot; previous?: Shot; index: number; active: boolean; frame: number; card: {width: number; height: number}};

export const SceneMediaLayer: React.FC<Props> = ({shot, previous, index, active, frame, card}) => {
  const local = frame - shot.start * FPS;
  const beatFrames = Math.max(1, Math.round((shot.end - shot.start) * FPS));
  const imageFrames = Math.min(shot.image_animation_frames ?? effectDuration('image_animations', shot.image_animation), Math.max(1, beatFrames - 2));
  const transitionFrames = Math.min(shot.transition_frames ?? effectDuration('transitions', shot.transition), Math.max(1, beatFrames - 2));
  const imageProgress = clamp(local / imageFrames);
  const transitionProgress = clamp(local / transitionFrames);
  const transition = transitionStyles(shot.transition, transitionProgress);
  const before = previous && local >= 0 && local < transitionFrames;
  const opacity = frame < shot.start * FPS ? 0.22 : active ? 1 : 0.76;
  const mediaStyle = {display: 'block', width: '100%', height: '100%', objectFit: 'contain' as const, borderRadius: 8};
  const asset = staticFile(`assets/${shot.asset}`) + `?v=${shot.cacheBust ?? 'current'}`;
  const previousAsset = previous ? staticFile(`assets/${previous.asset}`) + `?v=${previous.cacheBust ?? 'current'}` : undefined;
  return (
    <div style={{position: 'absolute', left: shot.x, top: shot.y, width: card.width, height: card.height, transform: 'translate(-50%, -50%)', opacity, borderRadius: 8, overflow: 'visible', boxShadow: active ? `0 0 0 4px ${shot.accent}66, 0 24px 60px #17342b2e` : '0 14px 34px #17342b18'}}>
      <div style={{position: 'absolute', left: 26, top: -42, color: active ? '#176453' : '#6e8980', fontSize: 24, fontWeight: 800, whiteSpace: 'nowrap'}}>{String(index + 1).padStart(2, '0')}  {shot.title}</div>
      <div style={{position: 'relative', width: '100%', height: '100%', overflow: 'hidden', borderRadius: 8, background: '#fff'}}>
        {before && previousAsset && <Img src={previousAsset} style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', ...transition.outgoing}} />}
        <div style={{position: 'absolute', inset: 0, ...((index > 0 && local >= 0) ? transition.incoming : {})}}>
          {shot.mediaType === 'video'
            ? <OffthreadVideo src={staticFile(shot.asset)} muted style={{...mediaStyle, ...imageAnimationStyle(shot.image_animation, imageProgress)}} />
            : <Img src={asset} style={{...mediaStyle, ...imageAnimationStyle(shot.image_animation, imageProgress)}} />}
        </div>
      </div>
    </div>
  );
};

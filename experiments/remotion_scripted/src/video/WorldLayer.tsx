import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {cameraFor} from './camera';
import type {Manifest} from './types';
import {FPS} from './types';
import {SceneMediaLayer} from './layers/SceneMediaLayer';

export const WorldLayer: React.FC<{project: Manifest}> = ({project}) => {
  const frame = useCurrentFrame();
  const camera = cameraFor(frame, project);
  const active = Math.max(0, project.shots.reduce((found, shot, index) => frame >= shot.start * FPS ? index : found, -1));
  const route = project.shots.map((shot, index) => `${index ? 'L' : 'M'} ${shot.x} ${shot.y}`).join(' ');
  const routeDone = project.shots.slice(0, active + 1).map((shot, index) => `${index ? 'L' : 'M'} ${shot.x} ${shot.y}`).join(' ');

  return (
    <AbsoluteFill style={{top: project.viewport.headerHeight, height: project.viewport.height, overflow: 'hidden', background: '#f4f7f5'}}>
      <div style={{position: 'absolute', left: project.viewport.width / 2, top: project.viewport.height / 2, transform: `scale(${camera.zoom}) translate(${-camera.x}px, ${-camera.y}px)`, transformOrigin: '0 0'}}>
        <div style={{position: 'absolute', left: -3000, top: -1800, width: project.world.width, height: project.world.height, backgroundImage: 'radial-gradient(#b7cbc6 2px, transparent 2px), linear-gradient(#dce8e4 1px, transparent 1px), linear-gradient(90deg, #dce8e4 1px, transparent 1px)', backgroundSize: '96px 96px, 480px 480px, 480px 480px'}} />
        <svg width="1" height="1" style={{position: 'absolute', overflow: 'visible', pointerEvents: 'none'}}>
          <path d={route} fill="none" stroke="#a8c3ba" strokeWidth="8" strokeDasharray="18 16" />
          <path d={routeDone} fill="none" stroke="#1d7767" strokeWidth="9" />
        </svg>
        {project.shots.map((shot, index) => (
          <SceneMediaLayer key={shot.id} shot={shot} previous={index > 0 ? project.shots[index - 1] : undefined} index={index} active={index === active} frame={frame} card={{width: shot.width, height: shot.height}} />
        ))}
      </div>
    </AbsoluteFill>
  );
};

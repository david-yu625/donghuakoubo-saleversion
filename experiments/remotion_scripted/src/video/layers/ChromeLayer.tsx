import React from 'react';
import {useCurrentFrame} from 'remotion';
import type {Manifest} from '../types';
import {clamp, FPS} from '../types';

export const ChromeLayer: React.FC<{project: Manifest}> = ({project}) => {
  const time = useCurrentFrame() / FPS;
  const shot = project.shots.find((item) => time >= item.start && time < item.end);
  const progress = clamp(time / project.durationSeconds);
  return <>
    <div style={{position: 'absolute', left: 72, top: 32, color: '#6c817a', fontSize: 23, fontWeight: 600}}>脚本驱动实验 · {project.title}</div>
    <div style={{position: 'absolute', left: 72, top: 82, right: 72, display: 'flex', alignItems: 'center', gap: 18}}><div style={{width: 6, height: 40, background: '#1d7767', borderRadius: 3}} /><div style={{color: '#172c27', fontSize: 42, fontWeight: 800}}>{shot?.title ?? project.title}</div></div>
    <div style={{position: 'absolute', left: 72, right: 72, top: 161, height: 3, background: '#dce7e3'}}><div style={{height: '100%', width: `${progress * 100}%`, background: '#1d7767'}} /></div>
  </>;
};

import React from 'react';
import {useCurrentFrame} from 'remotion';
import type {Manifest} from '../types';
import {FPS} from '../types';

export const CaptionLayer: React.FC<{project: Manifest}> = ({project}) => {
  const time = useCurrentFrame() / FPS;
  const caption = project.captions.find((item) => time >= item.start && time < item.end);
  if (!caption) return null;
  return <div style={{position: 'absolute', left: 160, right: 160, bottom: 32, minHeight: 62, display: 'flex', alignItems: 'center', justifyContent: 'center', pointerEvents: 'none'}}><div style={{maxWidth: 1600, padding: '5px 22px', borderRadius: 4, background: '#222222e8', color: '#fff', fontSize: 32, fontWeight: 600, lineHeight: 1.25, textAlign: 'center', whiteSpace: 'normal', fontFamily: 'Microsoft YaHei, PingFang SC, sans-serif'}}>{caption.text}</div></div>;
};

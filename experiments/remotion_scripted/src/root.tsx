import React from 'react';
import {Composition} from 'remotion';
import manifest from '../public/manifest.json';
import {ScriptedCanvas} from './video/ScriptedCanvas';

export const RemotionRoot: React.FC = () => (
  <Composition
    id="ScriptedCanvas"
    component={ScriptedCanvas}
    durationInFrames={Math.max(1, Math.round(manifest.durationSeconds * 30))}
    fps={30}
    width={1920}
    height={1080}
  />
);

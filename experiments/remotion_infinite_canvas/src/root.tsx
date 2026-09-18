import React from 'react';
import {Composition} from 'remotion';
import manifest from '../public/manifest.json';
import {InfiniteCanvas} from './video/InfiniteCanvas';

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="InfiniteCanvas"
      component={InfiniteCanvas}
      durationInFrames={Math.round(manifest.durationSeconds * 30)}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};

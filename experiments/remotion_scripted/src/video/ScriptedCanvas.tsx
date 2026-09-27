import React from 'react';
import {AbsoluteFill} from 'remotion';
import manifest from '../../public/manifest.json';
import {AudioLayer} from './layers/AudioLayer';
import {CaptionLayer} from './layers/CaptionLayer';
import {ChromeLayer} from './layers/ChromeLayer';
import {KeywordLayer} from './layers/KeywordLayer';
import {WorldLayer} from './WorldLayer';
import {assertManifest, type Manifest} from './types';

const project = assertManifest(manifest as unknown as Manifest);

export const ScriptedCanvas: React.FC = () => (
  <AbsoluteFill style={{fontFamily: 'Microsoft YaHei, PingFang SC, sans-serif', background: '#f5f8f7', overflow: 'hidden'}}>
    <AbsoluteFill style={{backgroundImage: 'radial-gradient(#c8d6d1 1px, transparent 1px)', backgroundSize: '32px 32px', opacity: 0.32}} />
    <WorldLayer project={project} />
    <ChromeLayer project={project} />
    <KeywordLayer project={project} />
    <CaptionLayer project={project} />
    <AudioLayer project={project} />
  </AbsoluteFill>
);

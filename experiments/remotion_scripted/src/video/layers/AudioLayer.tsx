import React from 'react';
import {Audio, staticFile} from 'remotion';
import type {Manifest} from '../types';

export const AudioLayer: React.FC<{project: Manifest}> = ({project}) => <Audio src={staticFile(project.audio)} volume={1} />;

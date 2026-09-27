import type {CSSProperties} from 'react';
import catalog from '../../effect_catalog.json';

export type TransitionId = keyof typeof catalog.transitions;
export type ImageAnimationId = keyof typeof catalog.image_animations;
type Layers = {incoming: CSSProperties; outgoing: CSSProperties};
const clamp = (p: number) => Math.max(0, Math.min(1, p));
const ease = (p: number) => p < 0.5 ? 4 * p ** 3 : 1 - (-2 * p + 2) ** 3 / 2;

// Each entry has its own geometry. Wipes/iris keep the outgoing image intact
// below the incoming opaque canvas, rather than reducing everything to a fade.
const transitions: Record<TransitionId, (p: number) => Layers> = {
  glide: (p) => ({incoming: {transform: `translateX(${(1 - p) * 100}%)`}, outgoing: {transform: `translateX(${-p * 100}%)`}}),
  drift: (p) => ({incoming: {transform: `translateY(${(1 - p) * 100}%)`}, outgoing: {transform: `translateY(${-p * 100}%)`}}),
  push: (p) => ({incoming: {transform: `scale(${0.55 + 0.45 * p})`, opacity: p}, outgoing: {transform: `scale(${1 + 0.3 * p})`, opacity: 1 - p}}),
  pull: (p) => ({incoming: {transform: `scale(${1.45 - 0.45 * p})`, opacity: p}, outgoing: {transform: `scale(${1 - 0.3 * p})`, opacity: 1 - p}}),
  wipe_left: (p) => ({incoming: {clipPath: `inset(0 ${(1 - p) * 100}% 0 0)`}, outgoing: {}}),
  wipe_up: (p) => ({incoming: {clipPath: `inset(${(1 - p) * 100}% 0 0 0)`}, outgoing: {}}),
  iris: (p) => ({incoming: {clipPath: `circle(${p * 110}% at 50% 50%)`}, outgoing: {}}),
  arc: (p) => ({incoming: {transform: `translate(${(1 - p) * 38}%, ${-Math.sin(p * Math.PI) * 14}%) rotate(${(1 - p) * 12}deg) scale(${0.8 + 0.2 * p})`, opacity: p}, outgoing: {transform: `translate(${-p * 30}%, ${Math.sin(p * Math.PI) * 14}%) rotate(${-p * 10}deg)`, opacity: 1 - p}}),
};

const images: Record<ImageAnimationId, (p: number) => CSSProperties> = {
  rise: (p) => ({transform: `translateY(${(1 - p) * 65}px)`}),
  slide_left: (p) => ({transform: `translateX(${(p - 1) * 120}px)`}),
  slide_right: (p) => ({transform: `translateX(${(1 - p) * 120}px)`}),
  scale: (p) => ({transform: `scale(${0.76 + 0.24 * p})`}),
  wipe: (p) => ({clipPath: `inset(0 ${(1 - p) * 92}% 0 0)`}),
  unfold: (p) => ({clipPath: `inset(0 ${(1 - p) * 46}% 0 ${(1 - p) * 46}%)`}),
  tilt: (p) => ({transform: `rotate(${(p - 1) * 6}deg) scale(${0.88 + 0.12 * p})`}),
  flip: (p) => ({transform: `perspective(1400px) rotateY(${(1 - p) * 65}deg)`}),
};

export function transitionStyles(id: string | undefined, progress: number): Layers {
  const p = clamp(progress);
  if (p >= 1) return {incoming: {}, outgoing: {opacity: 0}};
  if (p <= 0) return {incoming: {opacity: 0}, outgoing: {}};
  const effect = Object.prototype.hasOwnProperty.call(transitions, id ?? '') ? id as TransitionId : 'glide';
  return transitions[effect](ease(p));
}

export function imageAnimationStyle(id: string | undefined, progress: number): CSSProperties {
  const p = clamp(progress);
  if (p >= 1) return {};
  const effect = Object.prototype.hasOwnProperty.call(images, id ?? '') ? id as ImageAnimationId : 'rise';
  return images[effect](1 - (1 - p) ** 3);
}

export function effectDuration(kind: 'transitions' | 'image_animations', id: string | undefined): number {
  const pool: Record<string, {duration_frames: number}> = catalog[kind];
  return Object.prototype.hasOwnProperty.call(pool, id ?? '') ? pool[id!].duration_frames : kind === 'transitions' ? 26 : 42;
}

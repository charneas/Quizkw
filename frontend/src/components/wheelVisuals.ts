import type { WheelSpinResponse } from '../types'

// Partagé entre WheelModal (host) et WheelResultPopup (équipes) : les deux
// écrans doivent dessiner la même roue et atterrir sur le même secteur pour
// un résultat donné.

export type EffectType = WheelSpinResponse['effect_type']
export type SegmentKey = EffectType | 'bonus_big'

export interface WheelLikeResult {
  effect_type: string
  value: number | null
}

// La vraie décision (effect_type/value) vient du serveur — voir
// _roll_wheel_effect (main.py) pour la source de vérité des règles de
// plateau. Ces secteurs ne servent qu'à donner à la roue un segment visuel
// sur lequel atterrir, mais leur TAILLE reflète les vraies probabilités sur
// d20 : 1-5 malus, 6-10 bonus, 11-18 ping-pong, 19-20 bonus (le gros lot).
export const SEGMENTS: { key: SegmentKey; span: number }[] = [
  { key: 'malus', span: 90 }, // 5/20
  { key: 'ping_pong', span: 144 }, // 8/20
  { key: 'bonus', span: 90 }, // 5/20 (6-10, +1)
  { key: 'bonus_big', span: 36 }, // 2/20 (19-20, +3)
]
export const SEGMENT_STARTS = SEGMENTS.reduce<number[]>((acc, _seg, i) => {
  acc.push(i === 0 ? 0 : acc[i - 1] + SEGMENTS[i - 1].span)
  return acc
}, [])
export const SPIN_SPEED_DEG_PER_MS = 0.6
export const LANDING_DURATION_MS = 2200
// Durée d'atterrissage repliée pour prefers-reduced-motion : la roue va
// directement au bon secteur au lieu de tourner plusieurs tours, sans pour
// autant sauter instantanément (garde un minimum de perception du changement).
export const LANDING_DURATION_MS_REDUCED = 150

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

export const SEGMENT_COLORS: Record<SegmentKey, string> = {
  bonus: '#16a34a',
  bonus_big: '#f59e0b',
  malus: '#dc2626',
  ping_pong: '#7c3aed',
}

export const SEGMENT_EMOJIS: Record<SegmentKey, string> = {
  malus: '💀',
  bonus: '🎉',
  bonus_big: '⭐',
  ping_pong: '🏓',
}

export const effectColors: Record<EffectType, string> = {
  malus: 'text-danger',
  bonus: 'text-success',
  ping_pong: 'text-brand',
}

// Distinction purement visuelle : le backend renvoie effect_type: 'bonus'
// pour +1 (6-10) ET +3 (19-20), mais ce dernier est un tirage bien plus rare
// et généreux — on route vers 'bonus_big' selon result.value pour que la
// roue ne les confonde pas visuellement.
export function segmentKeyForResult(result: WheelLikeResult): SegmentKey {
  if (result.effect_type === 'bonus' && (result.value ?? 0) >= 3) return 'bonus_big'
  return result.effect_type as SegmentKey
}

export const wheelBackground = `conic-gradient(${SEGMENTS.map(
  (seg, i) => `${SEGMENT_COLORS[seg.key]} ${SEGMENT_STARTS[i]}deg ${SEGMENT_STARTS[i] + seg.span}deg`
).join(', ')})`

// easeOutCubic : décélération franche façon roue qui s'arrête.
export function easeOutCubic(t: number) {
  return 1 - Math.pow(1 - t, 3)
}

import { useEffect, useRef, useState } from 'react'
import type { WheelSpinResponse } from '../types'

interface WheelModalProps {
  onSpin: () => void | Promise<void>
  result: WheelSpinResponse | null
  onClose: () => void
  teamName?: string
  teamProgress?: string
  isLastTeam?: boolean
}

type EffectType = WheelSpinResponse['effect_type']
type Phase = 'idle' | 'spinning' | 'landing'
// Distinction purement visuelle : le backend renvoie effect_type: 'bonus'
// pour +1 (6-10) ET +3 (19-20), mais ce dernier est un tirage bien plus rare
// et généreux — segmentKeyForResult() ci-dessous route vers 'bonus_big'
// selon result.value pour que la roue ne les confonde pas visuellement.
type SegmentKey = EffectType | 'bonus_big'

// La vraie décision (effect_type/value) vient du serveur dans handleSpin —
// voir _roll_wheel_effect (main.py) pour la source de vérité des règles de
// plateau. Ces secteurs ne servent qu'à donner à la roue un segment visuel
// sur lequel atterrir, mais leur TAILLE reflète les vraies probabilités sur
// d20 : 1-5 malus, 6-10 bonus, 11-18 ping-pong, 19-20 bonus (le gros lot).
const SEGMENTS: { key: SegmentKey; span: number }[] = [
  { key: 'malus', span: 90 }, // 5/20
  { key: 'ping_pong', span: 144 }, // 8/20
  { key: 'bonus', span: 90 }, // 5/20 (6-10, +1)
  { key: 'bonus_big', span: 36 }, // 2/20 (19-20, +3)
]
const SEGMENT_STARTS = SEGMENTS.reduce<number[]>((acc, _seg, i) => {
  acc.push(i === 0 ? 0 : acc[i - 1] + SEGMENTS[i - 1].span)
  return acc
}, [])
const SPIN_SPEED_DEG_PER_MS = 0.6
const LANDING_DURATION_MS = 2200

const SEGMENT_COLORS: Record<SegmentKey, string> = {
  bonus: '#16a34a',
  bonus_big: '#f59e0b',
  malus: '#dc2626',
  ping_pong: '#7c3aed',
}

const SEGMENT_EMOJIS: Record<SegmentKey, string> = {
  malus: '💀',
  bonus: '🎉',
  bonus_big: '⭐',
  ping_pong: '🏓',
}

const effectColors: Record<EffectType, string> = {
  malus: 'text-game-danger',
  bonus: 'text-game-success',
  ping_pong: 'text-primary-400',
}

// Le résultat réel du serveur ne connaît que 3 effect_type ; on affine vers
// 'bonus_big' seulement pour choisir/afficher le bon secteur de la roue.
function segmentKeyForResult(result: WheelSpinResponse): SegmentKey {
  if (result.effect_type === 'bonus' && (result.value ?? 0) >= 3) return 'bonus_big'
  return result.effect_type
}

const wheelBackground = `conic-gradient(${SEGMENTS.map(
  (seg, i) => `${SEGMENT_COLORS[seg.key]} ${SEGMENT_STARTS[i]}deg ${SEGMENT_STARTS[i] + seg.span}deg`
).join(', ')})`

// easeOutCubic : décélération franche façon roue qui s'arrête.
function easeOutCubic(t: number) {
  return 1 - Math.pow(1 - t, 3)
}

function WheelModal({ onSpin, result, onClose, teamName, teamProgress, isLastTeam = true }: WheelModalProps) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [rotation, setRotation] = useState(0)
  const [showResultPanel, setShowResultPanel] = useState(false)
  const rotationRef = useRef(0)
  const rafRef = useRef<number | null>(null)
  const landedForResultRef = useRef<WheelSpinResponse | null>(null)
  // Génération du spin en cours (une par appel à handleSpin, une par équipe
  // dans la queue). Non-null tant qu'on attend activement un résultat pour
  // CETTE génération : permet de détecter l'atterrissage même si le filet
  // de sécurité a déjà remis `phase` à 'idle' avant qu'un résultat lent
  // n'arrive (sinon ce résultat serait perdu en silence), et empêche un
  // filet expiré d'annuler le spin suivant.
  const awaitingGenerationRef = useRef<number | null>(null)
  const spinGenerationRef = useRef(0)

  useEffect(() => {
    rotationRef.current = rotation
  }, [rotation])

  // Rotation entièrement pilotée en JS (rAF), jamais de @keyframes CSS ici :
  // mélanger une animation CSS indéterminée puis une transition vers un
  // angle précis pose un problème de reprise d'état (la roue reste figée
  // au lieu de décélérer, cf. revue manuelle) — un seul mécanisme d'un bout
  // à l'autre du spin évite ce piège.
  useEffect(() => {
    if (phase === 'spinning') {
      let last = performance.now()
      const tick = (now: number) => {
        const delta = now - last
        last = now
        setRotation((r) => r + delta * SPIN_SPEED_DEG_PER_MS)
        rafRef.current = requestAnimationFrame(tick)
      }
      rafRef.current = requestAnimationFrame(tick)
      return () => {
        if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
      }
    }
    if (phase === 'landing' && result) {
      const key = segmentKeyForResult(result)
      const foundIndex = SEGMENTS.findIndex((seg) => seg.key === key)
      const targetIndex = foundIndex >= 0 ? foundIndex : 0
      if (foundIndex < 0) {
        console.error('[WheelModal] segment introuvable pour', key, '— repli sur le premier secteur')
      }
      const segmentCenter = SEGMENT_STARTS[targetIndex] + SEGMENTS[targetIndex].span / 2
      const startRotation = rotationRef.current
      // Toujours vers l'avant (jamais de retour en arrière visuel) : le
      // prochain multiple de 360 au-delà de la rotation actuelle, plus
      // quelques tours pleins pour l'effet, moins l'offset du secteur visé.
      const nextFullTurn = Math.ceil((startRotation + 1) / 360) * 360
      const endRotation = nextFullTurn + 3 * 360 - segmentCenter
      const startTime = performance.now()
      const tick = (now: number) => {
        const t = Math.min(1, (now - startTime) / LANDING_DURATION_MS)
        setRotation(startRotation + (endRotation - startRotation) * easeOutCubic(t))
        if (t < 1) {
          rafRef.current = requestAnimationFrame(tick)
        } else {
          setPhase('idle')
          setShowResultPanel(true)
        }
      }
      rafRef.current = requestAnimationFrame(tick)
      return () => {
        if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
      }
    }
  }, [phase, result])

  // Dès que le résultat arrive pour la génération activement attendue —
  // qu'on soit encore en 'spinning' ou que le filet de sécurité ait déjà
  // remis la phase à 'idle' entre-temps — on bascule sur l'atterrissage.
  useEffect(() => {
    if (result && awaitingGenerationRef.current !== null && landedForResultRef.current !== result) {
      landedForResultRef.current = result
      awaitingGenerationRef.current = null
      setPhase('landing')
    }
    if (!result) {
      landedForResultRef.current = null
      setShowResultPanel(false)
      // Le parent renvoie `result` à null en changeant d'équipe dans la
      // queue ou à la fermeture du modal — jamais pendant qu'on attend
      // activement un résultat, qu'il ne faut donc pas annuler ici.
      if (awaitingGenerationRef.current === null) setPhase('idle')
    }
  }, [result])

  const handleSpin = async () => {
    if (phase !== 'idle') return
    const generation = ++spinGenerationRef.current
    awaitingGenerationRef.current = generation
    setPhase('spinning')
    setShowResultPanel(false)
    try {
      // Délai plancher pour que la phase "ça tourne" soit perceptible même
      // si le serveur répond quasi instantanément — l'atterrissage réel est
      // de toute façon piloté par l'arrivée de `result` via l'effet ci-dessus.
      await Promise.all([new Promise((resolve) => setTimeout(resolve, 700)), Promise.resolve(onSpin())])
    } catch (err) {
      // onSpin() (handleSpinWheel côté HostGame) avale déjà ses erreurs dans
      // son propre setError affiché ailleurs dans l'écran ; ce catch ne
      // couvre que le cas imprévu d'un throw synchrone, d'où le log dédié.
      console.error('[WheelModal] échec du spin', err)
      awaitingGenerationRef.current = null
      setPhase('idle')
      return
    }
    // Filet de sécurité : si onSpin() a résolu sans jamais faire arriver de
    // nouveau `result` (échec silencieux avalé côté parent, cf.
    // handleSpinWheel qui ne fait que setError sans relancer), la roue
    // resterait bloquée en rotation indéfiniment sans ce délai de secours.
    // Le contrôle de génération évite qu'un filet expiré (spin déjà atterri)
    // n'annule le spin suivant de la queue par équipe.
    setTimeout(() => {
      if (awaitingGenerationRef.current === generation) {
        awaitingGenerationRef.current = null
        setPhase((p) => (p === 'spinning' ? 'idle' : p))
      }
    }, 4000)
  }

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <div className="card max-w-md w-full text-center">
        <h2 className="text-2xl font-bold mb-2">🎡 Roue de Fortune</h2>

        {teamName && (
          <div className="mb-4">
            <p className="text-lg font-semibold text-game-accent">{teamName}</p>
            {teamProgress && (
              <p className="text-xs text-slate-500">Équipe {teamProgress}</p>
            )}
          </div>
        )}

        {/* Roue à secteurs : pointeur fixe en haut, disque qui tourne puis
            décélère jusqu'à s'arrêter sur un secteur du type de résultat. */}
        <div className="relative w-48 h-48 mx-auto mb-6">
          <div
            className="absolute -top-2 left-1/2 -translate-x-1/2 z-10 w-0 h-0
                       border-l-[10px] border-l-transparent
                       border-r-[10px] border-r-transparent
                       border-t-[16px] border-t-game-accent drop-shadow"
          />
          <div
            className="w-full h-full rounded-full border-4 border-game-accent shadow-xl"
            style={{ background: wheelBackground, transform: `rotate(${rotation}deg)` }}
          >
            {SEGMENTS.map((seg, i) => {
              const angle = SEGMENT_STARTS[i] + seg.span / 2
              return (
                <div
                  key={seg.key}
                  className="absolute inset-0 flex justify-center"
                  style={{ transform: `rotate(${angle}deg)` }}
                >
                  <span className="text-2xl mt-2">{SEGMENT_EMOJIS[seg.key]}</span>
                </div>
              )
            })}
          </div>
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="w-8 h-8 rounded-full bg-game-accent border-2 border-white/70 shadow" />
          </div>
        </div>

        {result && showResultPanel ? (
          <div className="space-y-4">
            <div className={`text-xl font-bold ${effectColors[result.effect_type]}`}>
              {SEGMENT_EMOJIS[segmentKeyForResult(result)]} {result.effect_type.toUpperCase()}
            </div>
            <p className="text-slate-300">
              {result.message}
            </p>
            {result.value !== null && (
              <p className="text-2xl font-bold text-game-accent">
                {result.value > 0 ? '+' : ''}{result.value} points
              </p>
            )}
            <button onClick={onClose} className="btn-primary w-full mt-4">
              {isLastTeam ? 'Continuer →' : 'Équipe suivante →'}
            </button>
          </div>
        ) : (
          <div>
            <p className="text-slate-400 mb-4">
              {phase === 'idle' ? "C'est l'heure de la roue ! 5 tours joués." : '🎡 La roue tourne...'}
            </p>
            <button
              onClick={handleSpin}
              disabled={phase !== 'idle'}
              className="btn-primary w-full text-lg disabled:opacity-60"
            >
              {phase !== 'idle' ? '🎡 En rotation...' : '🎡 Tourner la roue !'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default WheelModal
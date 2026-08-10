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

// Roue purement décorative (item misc playtest 2026-07-31, "ajouter une
// animation pour la roue") : la vraie décision (effect_type/value) vient du
// serveur dans handleSpin ; ces secteurs ne servent qu'à donner à la roue un
// segment visuel sur lequel atterrir une fois le résultat connu.
const SEGMENTS: EffectType[] = ['bonus', 'malus', 'ping_pong', 'bonus', 'malus', 'ping_pong']
const SEGMENT_ANGLE = 360 / SEGMENTS.length
const SPIN_SPEED_DEG_PER_MS = 0.6
const LANDING_DURATION_MS = 2200

const SEGMENT_COLORS: Record<EffectType, string> = {
  bonus: '#16a34a',
  malus: '#dc2626',
  ping_pong: '#7c3aed',
}

const effectColors: Record<EffectType, string> = {
  malus: 'text-game-danger',
  bonus: 'text-game-success',
  ping_pong: 'text-primary-400',
}

const effectEmojis: Record<EffectType, string> = {
  malus: '💀',
  bonus: '🎉',
  ping_pong: '🏓',
}

const wheelBackground = `conic-gradient(${SEGMENTS.map(
  (seg, i) => `${SEGMENT_COLORS[seg]} ${i * SEGMENT_ANGLE}deg ${(i + 1) * SEGMENT_ANGLE}deg`
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
  // Identifie chaque appel à handleSpin (une par équipe dans la queue) pour
  // que le filet de sécurité d'un spin déjà terminé ne puisse pas annuler
  // le spin suivant, démarré entre-temps.
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
      const matchingIndices = SEGMENTS.map((seg, i) => (seg === result.effect_type ? i : -1)).filter((i) => i >= 0)
      const targetIndex = matchingIndices[Math.floor(Math.random() * matchingIndices.length)]
      const segmentCenter = targetIndex * SEGMENT_ANGLE + SEGMENT_ANGLE / 2
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

  // Dès que le résultat arrive pendant qu'on tourne, on bascule sur la
  // phase d'atterrissage (gérée par l'effet ci-dessus).
  useEffect(() => {
    if (result && phase === 'spinning' && landedForResultRef.current !== result) {
      landedForResultRef.current = result
      setPhase('landing')
    }
    if (!result) {
      landedForResultRef.current = null
      setShowResultPanel(false)
      // Le parent renvoie `result` à null en changeant d'équipe dans la
      // queue ou à la fermeture du modal — jamais pendant qu'on attend la
      // réponse réseau d'un spin en cours (phase 'spinning'), qu'il ne faut
      // donc pas annuler ici.
      if (phase !== 'spinning') setPhase('idle')
    }
  }, [result, phase])

  const handleSpin = async () => {
    if (phase !== 'idle') return
    const generation = ++spinGenerationRef.current
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
      if (spinGenerationRef.current === generation) {
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
              const angle = i * SEGMENT_ANGLE + SEGMENT_ANGLE / 2
              return (
                <div
                  key={i}
                  className="absolute inset-0 flex justify-center"
                  style={{ transform: `rotate(${angle}deg)` }}
                >
                  <span className="text-2xl mt-2">{effectEmojis[seg]}</span>
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
              {effectEmojis[result.effect_type]} {result.effect_type.toUpperCase()}
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
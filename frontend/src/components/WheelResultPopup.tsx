import { useEffect, useRef, useState } from 'react'
import {
  SEGMENTS,
  SEGMENT_STARTS,
  SPIN_SPEED_DEG_PER_MS,
  LANDING_DURATION_MS,
  SEGMENT_EMOJIS,
  segmentKeyForResult,
  wheelBackground,
  easeOutCubic,
  type WheelLikeResult,
} from './wheelVisuals'

interface WheelResultPopupProps {
  result: WheelLikeResult & { message: string }
  onClose: () => void
}

const SPIN_DURATION_MS = 900

// Contrairement à WheelModal (host), le résultat est déjà connu au moment où
// ce popup apparaît côté équipe : on ne l'attend pas d'une requête, on
// rejoue juste une phase de rotation puis d'atterrissage sur le bon secteur
// avant de révéler le message, pour que la roue soit visible côté joueurs
// aussi (BUG : jusqu'ici le résultat s'affichait sans aucune animation).
function WheelResultPopup({ result, onClose }: WheelResultPopupProps) {
  const [rotation, setRotation] = useState(0)
  const [showResult, setShowResult] = useState(false)
  const rotationRef = useRef(0)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    rotationRef.current = rotation
  }, [rotation])

  useEffect(() => {
    let cancelled = false
    const spinStart = performance.now()

    const spinTick = (now: number) => {
      if (cancelled) return
      const elapsed = now - spinStart
      if (elapsed < SPIN_DURATION_MS) {
        setRotation((r) => r + SPIN_SPEED_DEG_PER_MS * 16)
        rafRef.current = requestAnimationFrame(spinTick)
        return
      }
      startLanding()
    }

    const startLanding = () => {
      const key = segmentKeyForResult(result)
      const foundIndex = SEGMENTS.findIndex((seg) => seg.key === key)
      const targetIndex = foundIndex >= 0 ? foundIndex : 0
      const segmentCenter = SEGMENT_STARTS[targetIndex] + SEGMENTS[targetIndex].span / 2
      const startRotation = rotationRef.current
      const nextFullTurn = Math.ceil((startRotation + 1) / 360) * 360
      const endRotation = nextFullTurn + 3 * 360 - segmentCenter
      const landingStart = performance.now()

      const landingTick = (now: number) => {
        if (cancelled) return
        const t = Math.min(1, (now - landingStart) / LANDING_DURATION_MS)
        setRotation(startRotation + (endRotation - startRotation) * easeOutCubic(t))
        if (t < 1) {
          rafRef.current = requestAnimationFrame(landingTick)
        } else {
          setShowResult(true)
        }
      }
      rafRef.current = requestAnimationFrame(landingTick)
    }

    rafRef.current = requestAnimationFrame(spinTick)
    return () => {
      cancelled = true
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <div className="card max-w-sm w-full text-center">
        <h3 className="text-lg font-semibold text-text mb-4">🎡 Roue de fortune !</h3>

        <div className="relative w-40 h-40 mx-auto mb-6">
          <div
            className="absolute -top-2 left-1/2 -translate-x-1/2 z-10 w-0 h-0
                       border-l-[8px] border-l-transparent
                       border-r-[8px] border-r-transparent
                       border-t-[14px] border-t-game-accent drop-shadow"
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
                  <span className="text-xl mt-2">{SEGMENT_EMOJIS[seg.key]}</span>
                </div>
              )
            })}
          </div>
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="w-6 h-6 rounded-full bg-game-accent border-2 border-white/70 shadow" />
          </div>
        </div>

        {showResult ? (
          <div className="space-y-4">
            <p className="text-sm text-text-muted">{result.message}</p>
            <button onClick={onClose} className="btn-primary w-full min-h-[44px]">
              Continuer →
            </button>
          </div>
        ) : (
          <p className="text-sm text-text-muted">La roue tourne...</p>
        )}
      </div>
    </div>
  )
}

export default WheelResultPopup

import { useEffect, useRef, useState } from 'react'
import type { BlindtestFoundElement } from '../types'

interface ClassicRoundProps {
  durationSeconds: number
  // Temps déjà écoulé à l'affichage, pour un joueur qui arrive en cours de round.
  elapsedSeconds: number
  found: BlindtestFoundElement[]
  misses: number
  onSubmit: (text: string) => void
}

const CHIPS: { element: BlindtestFoundElement; label: string }[] = [
  { element: 'title', label: 'Titre' },
  { element: 'artist', label: 'Artiste' },
]

/**
 * Un round du blind test classique : un seul champ, autant d'essais que voulu,
 * le titre et l'artiste y compris sur la même ligne. Le compte à rebours n'est
 * qu'un repère : le serveur chronomètre et ferme le round.
 */
export default function ClassicRound({ durationSeconds, elapsedSeconds, found, misses, onSubmit }: ClassicRoundProps) {
  const [text, setText] = useState('')
  const [remaining, setRemaining] = useState(durationSeconds - elapsedSeconds)
  const inputRef = useRef<HTMLInputElement>(null)
  const allFound = found.length === CHIPS.length

  useEffect(() => {
    const deadline = Date.now() + (durationSeconds - elapsedSeconds) * 1000
    const tick = () => setRemaining(Math.max(0, (deadline - Date.now()) / 1000))
    tick()
    const interval = window.setInterval(tick, 200)
    return () => window.clearInterval(interval)
  }, [durationSeconds, elapsedSeconds])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  function handleSubmit() {
    const answer = text.trim()
    if (!answer) return
    onSubmit(answer)
    setText('')
  }

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-text-muted">Écoute et tape ce que tu reconnais.</p>
        <span
          role="timer"
          aria-label={`${Math.ceil(remaining)} secondes restantes`}
          className="font-display font-semibold text-2xl tabular-nums text-accent"
        >
          {Math.ceil(remaining)}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-border overflow-hidden" aria-hidden="true">
        <div
          className="h-full bg-accent transition-[width] duration-200 ease-linear"
          style={{ width: `${(remaining / durationSeconds) * 100}%` }}
        />
      </div>

      <ul className="flex gap-2" aria-label="Ce que tu as trouvé">
        {CHIPS.map(({ element, label }) => {
          const isFound = found.includes(element)
          return (
            <li
              key={element}
              className={`flex-1 rounded-lg border px-3 py-2 text-center text-sm font-semibold ${
                isFound ? 'border-success text-success' : 'border-border text-text-muted'
              }`}
            >
              {isFound ? `✓ ${label} trouvé` : label}
            </li>
          )
        })}
      </ul>

      {allFound ? (
        <p className="text-success font-semibold text-center">Tout trouvé ! Profite de la fin du morceau.</p>
      ) : (
        <div className="space-y-2">
          <div className="flex gap-2">
            <input
              ref={inputRef}
              type="text"
              className="input-field flex-1"
              placeholder="Artiste, titre, ou les deux"
              aria-label="Ta réponse"
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
              maxLength={200}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
            />
            <button className="btn-primary" onClick={handleSubmit} disabled={!text.trim()}>
              Valider
            </button>
          </div>
          <p key={misses} role="status" className={`text-sm text-text-muted ${misses > 0 ? 'animate-fade-in' : 'invisible'}`}>
            Pas ça, réessaie : aucune pénalité.
          </p>
        </div>
      )}
    </div>
  )
}

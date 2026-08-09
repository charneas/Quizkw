import { useState } from 'react'
import type { WheelSpinResponse } from '../types'

interface WheelModalProps {
  onSpin: () => void | Promise<void>
  result: WheelSpinResponse | null
  onClose: () => void
  teamName?: string
  teamProgress?: string
  isLastTeam?: boolean
}

function WheelModal({ onSpin, result, onClose, teamName, teamProgress, isLastTeam = true }: WheelModalProps) {
  const [spinning, setSpinning] = useState(false)

  const handleSpin = async () => {
    if (spinning) return
    setSpinning(true)
    // Revue de code (story J.004) : onSpin persiste désormais réellement le
    // score côté serveur — le bouton doit rester désactivé jusqu'à la
    // résolution effective de l'appel réseau, pas seulement pendant
    // l'animation, sinon un double-clic double le score pour de vrai.
    try {
      await Promise.all([
        new Promise((resolve) => setTimeout(resolve, 2000)), // animation minimale
        Promise.resolve(onSpin()),
      ])
    } finally {
      setSpinning(false)
    }
  }

  const effectColors = {
    malus: 'text-game-danger',
    bonus: 'text-game-success',
    ping_pong: 'text-primary-400',
  }

  const effectEmojis = {
    malus: '💀',
    bonus: '🎉',
    ping_pong: '🏓',
  }

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <div className="card max-w-md w-full text-center">
        <h2 className="text-2xl font-bold mb-2">🎡 Roue de Fortune</h2>

        {/* Nom de l'équipe et progression */}
        {teamName && (
          <div className="mb-4">
            <p className="text-lg font-semibold text-game-accent">{teamName}</p>
            {teamProgress && (
              <p className="text-xs text-slate-500">Équipe {teamProgress}</p>
            )}
          </div>
        )}

        {/* Roue animée */}
        <div className="relative w-48 h-48 mx-auto mb-6">
          <div
            className={`w-full h-full rounded-full border-4 border-game-accent flex items-center justify-center text-6xl bg-gradient-to-br from-primary-700 to-primary-900 ${
              spinning ? 'animate-spin-slow' : ''
            }`}
          >
            {result ? effectEmojis[result.effect_type] : '🎡'}
          </div>
        </div>

        {/* Résultat */}
        {result ? (
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
              C'est l'heure de la roue ! 5 tours joués.
            </p>
            <button
              onClick={handleSpin}
              disabled={spinning}
              className="btn-primary w-full text-lg"
            >
              {spinning ? '🎡 En rotation...' : '🎡 Tourner la roue !'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default WheelModal

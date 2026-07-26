import { useState } from 'react'
import type { Team } from '../types'

interface PingPongDuelProps {
  theme: {
    id: number
    title: string
    description: string | null
    correct_answers: string[]
    min_answers_to_win: number
  }
  team1: Team
  team2: Team
  currentTurnTeamId: number
  answersUsed: string[]
  turnNumber: number
  isCurrentTeam: boolean
  onSubmit: (answer: string) => void
  onPass: () => void
  disabled: boolean
}

function PingPongQuestion({
  theme,
  team1,
  team2,
  currentTurnTeamId,
  answersUsed,
  turnNumber,
  isCurrentTeam,
  onSubmit,
  onPass,
  disabled,
}: PingPongDuelProps) {
  const [answer, setAnswer] = useState('')

  const handleSubmit = () => {
    if (answer.trim().length > 0) {
      onSubmit(answer.trim())
      setAnswer('')
    }
  }

  const currentTeam = currentTurnTeamId === team1.id ? team1 : team2

  return (
    <div className="card">
      {/* Header */}
      <div className="text-center mb-6">
        <div className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 rounded-full mb-4">
          <span className="text-2xl">🏓</span>
          <span className="font-bold text-white">DUEL PING-PONG</span>
        </div>
        <h2 className="text-2xl font-bold mb-2">{theme.title}</h2>
        {theme.description && (
          <p className="text-slate-400 text-sm">{theme.description}</p>
        )}
      </div>

      {/* Affrontement */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div
          className={`p-4 rounded-lg border-2 text-center transition-colors ${
            currentTurnTeamId === team1.id
              ? 'border-game-accent bg-game-accent/10'
              : 'border-slate-700 bg-slate-800/50'
          }`}
        >
          <p className="text-sm text-slate-400">Équipe 1</p>
          <p className="text-xl font-bold">{team1.name}</p>
          {currentTurnTeamId === team1.id && (
            <span className="inline-block mt-1 px-2 py-0.5 bg-game-accent text-black text-xs rounded-full font-bold">
              JOUE
            </span>
          )}
        </div>

        <div
          className={`p-4 rounded-lg border-2 text-center transition-colors ${
            currentTurnTeamId === team2.id
              ? 'border-game-accent bg-game-accent/10'
              : 'border-slate-700 bg-slate-800/50'
          }`}
        >
          <p className="text-sm text-slate-400">Équipe 2</p>
          <p className="text-xl font-bold">{team2.name}</p>
          {currentTurnTeamId === team2.id && (
            <span className="inline-block mt-1 px-2 py-0.5 bg-game-accent text-black text-xs rounded-full font-bold">
              JOUE
            </span>
          )}
        </div>
      </div>

      {/* Turn indicator */}
      <div className="text-center mb-4">
        <p className="text-slate-400 text-sm">
          Tour {turnNumber} • Au tour de{' '}
          <span className="font-bold text-game-accent">{currentTeam.name}</span>
        </p>
      </div>

      {/* Réponses déjà données */}
      {answersUsed.length > 0 && (
        <div className="bg-slate-700/30 rounded-lg p-4 mb-6">
          <h4 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-2">
            Réponses déjà données ({answersUsed.length})
          </h4>
          <div className="flex flex-wrap gap-2">
            {answersUsed.map((ans, i) => (
              <span
                key={i}
                className="px-3 py-1 bg-slate-600 text-white rounded-full text-sm"
              >
                {ans}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Zone de réponse */}
      {isCurrentTeam ? (
        <div className="space-y-4">
          <div>
            <input
              type="text"
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && answer.trim() && !disabled) {
                  e.preventDefault()
                  handleSubmit()
                }
              }}
              placeholder="Votre réponse..."
              className="w-full px-4 py-3 bg-slate-700 border border-slate-600 rounded-lg focus:outline-none focus:border-game-accent transition-colors text-lg"
              autoFocus
              disabled={disabled}
            />
          </div>

          <div className="flex gap-3">
            <button
              onClick={handleSubmit}
              disabled={disabled || answer.trim().length === 0}
              className="btn-primary flex-1 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Valider la réponse
            </button>
            <button
              onClick={onPass}
              disabled={disabled}
              className="btn-danger px-6 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Abandonner
            </button>
          </div>

          <p className="text-center text-xs text-slate-500">
            Une seule réponse à la fois • +2 points par bonne réponse au gagnant
          </p>
        </div>
      ) : (
        <div className="text-center py-6 bg-slate-700/30 rounded-lg">
          <p className="text-slate-400 text-lg">
            ⏳ En attente de la réponse de{' '}
            <span className="font-bold text-game-accent">{currentTeam.name}</span>...
          </p>
        </div>
      )}
    </div>
  )
}

export default PingPongQuestion
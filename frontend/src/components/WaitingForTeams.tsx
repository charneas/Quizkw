import { useEffect, useState } from 'react'
import type { Team } from '../types'

interface WaitingForTeamsProps {
  currentTeam: Team
  totalTeams: number
  answeredCount: number
  onAllAnswered: () => void
}

function WaitingForTeams({ currentTeam, totalTeams, answeredCount, onAllAnswered }: WaitingForTeamsProps) {
  const [dots, setDots] = useState('.')

  useEffect(() => {
    // Animation des points
    const interval = setInterval(() => {
      setDots(prev => prev.length >= 3 ? '.' : prev + '.')
    }, 500)

    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    // Vérifier si tous ont répondu
    if (answeredCount === totalTeams) {
      onAllAnswered()
    }
  }, [answeredCount, totalTeams, onAllAnswered])

  const progress = (answeredCount / totalTeams) * 100

  return (
    <div className="card text-center py-8">
      <div className="mb-6">
        <div className="text-6xl mb-4 animate-pulse">⏳</div>
        <h2 className="text-2xl font-bold text-game-accent mb-2">
          Attente des autres équipes{dots}
        </h2>
        <p className="text-slate-400">
          Votre équipe <span className="text-white font-semibold">{currentTeam.name}</span> a répondu !
        </p>
      </div>

      {/* Barre de progression */}
      <div className="max-w-md mx-auto mb-6">
        <div className="flex justify-between text-sm mb-2">
          <span className="text-slate-400">Équipes ayant répondu</span>
          <span className="text-game-accent font-bold">{answeredCount} / {totalTeams}</span>
        </div>
        <div className="w-full bg-slate-700 rounded-full h-4 overflow-hidden">
          <div 
            className="h-full bg-gradient-to-r from-game-primary to-game-accent transition-all duration-500 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Liste d'attente stylisée */}
      <div className="flex justify-center gap-2 flex-wrap max-w-md mx-auto">
        {Array.from({ length: totalTeams }).map((_, index) => (
          <div
            key={index}
            className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-all duration-300 ${
              index < answeredCount
                ? 'bg-game-success text-white scale-110'
                : 'bg-slate-700 text-slate-500'
            }`}
          >
            {index < answeredCount ? '✓' : index + 1}
          </div>
        ))}
      </div>

      <p className="text-slate-500 text-sm mt-6">
        La prochaine question apparaîtra automatiquement...
      </p>
    </div>
  )
}

export default WaitingForTeams

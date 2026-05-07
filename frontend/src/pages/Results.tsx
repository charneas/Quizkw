import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getGame } from '../services/api'
import type { GameSession } from '../types'

function Results() {
  const { code } = useParams<{ code: string }>()
  const navigate = useNavigate()
  const [game, setGame] = useState<GameSession | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (code) loadGame()
  }, [code])

  const loadGame = async () => {
    try {
      const gameData = await getGame(code!)
      setGame(gameData)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-2xl text-slate-400 animate-pulse">Chargement...</div>
      </div>
    )
  }

  if (!game) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="card text-center">
          <p className="text-slate-400">Partie non trouvée</p>
          <button onClick={() => navigate('/')} className="btn-primary mt-4">Retour</button>
        </div>
      </div>
    )
  }

  // Trier les équipes par score décroissant
  const sortedTeams = [...game.teams].sort((a, b) => b.score - a.score)

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="max-w-lg w-full space-y-6">
        {/* Titre */}
        <div className="text-center">
          <h1 className="text-4xl font-bold">🏆 Résultats</h1>
          <p className="text-slate-400 mt-2">Partie {game.code}</p>
        </div>

        {/* Podium */}
        <div className="card">
          {sortedTeams.map((team, index) => (
            <div
              key={team.id}
              className={`flex items-center justify-between p-4 rounded-lg mb-3 last:mb-0 ${
                index === 0
                  ? 'bg-yellow-900/30 border border-yellow-600'
                  : index === 1
                    ? 'bg-slate-600/30 border border-slate-500'
                    : index === 2
                      ? 'bg-orange-900/30 border border-orange-700'
                      : 'bg-slate-800 border border-slate-700'
              }`}
            >
              <div className="flex items-center gap-4">
                <span className="text-3xl">
                  {index === 0 ? '🥇' : index === 1 ? '🥈' : index === 2 ? '🥉' : `${index + 1}.`}
                </span>
                <div>
                  <p className="font-bold text-lg">{team.name}</p>
                  <p className="text-sm text-slate-400">{team.players.length} joueurs</p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-2xl font-bold text-game-accent">{team.score}</p>
                <p className="text-xs text-slate-400">points</p>
              </div>
            </div>
          ))}
        </div>

        {/* Actions */}
        <div className="flex gap-3">
          <button onClick={() => navigate('/')} className="btn-primary flex-1">
            🏠 Nouvelle partie
          </button>
        </div>
      </div>
    </div>
  )
}

export default Results

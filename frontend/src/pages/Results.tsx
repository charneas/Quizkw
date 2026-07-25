import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getGame, getFinalStandings } from '../services/api'
import type { GameSession } from '../types'
import type { MemoryGridStandings } from '../services/api'

function Results() {
  const { code } = useParams<{ code: string }>()
  const navigate = useNavigate()
  const [game, setGame] = useState<GameSession | null>(null)
  const [standings, setStandings] = useState<MemoryGridStandings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (code) loadResults()
  }, [code])

  const loadResults = async () => {
    try {
      setGame(await getGame(code!))
      // AD-1 : le vainqueur du tournoi sort de la Manche 3 SEULE. Les manches
      // 1 et 2 sont purement qualificatives et n'entrent pas dans ce classement.
      setStandings(await getFinalStandings(code!))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Résultats indisponibles')
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

  const podium = standings?.player_scores ?? []

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="max-w-lg w-full space-y-6">
        <div className="text-center">
          <h1 className="text-4xl font-bold">🏆 Résultats</h1>
          <p className="text-slate-400 mt-2">Partie {game.code}</p>
          <p className="text-xs text-slate-500 mt-1">
            Classement de la Manche 3 — les manches 1 et 2 étaient qualificatives
          </p>
        </div>

        {podium.length === 0 ? (
          <div className="card text-center">
            <p className="text-slate-400">
              {error || "La Manche 3 n'a pas encore désigné de vainqueur."}
            </p>
          </div>
        ) : (
          <div className="card">
            {podium.map((player, index) => (
              <div
                key={player.player_id}
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
                    <p className="font-bold text-lg">{player.player_name}</p>
                    <p className="text-sm text-slate-400">
                      {player.own_theme_cells} propres • {player.stolen_cells} volées
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-2xl font-bold text-game-accent">{player.total_score}</p>
                  <p className="text-xs text-slate-400">points</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {standings?.is_tie && (
          <div className="card text-center border-game-accent">
            <p className="text-game-accent font-bold">Égalité — mort subite nécessaire</p>
          </div>
        )}

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

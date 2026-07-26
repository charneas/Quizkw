import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getGame } from '../services/api'
import type { GameSession } from '../types'

function TeamJoin() {
  const { code } = useParams<{ code: string }>()
  const navigate = useNavigate()
  const [game, setGame] = useState<GameSession | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (code) loadGame()
  }, [code])

  const loadGame = async () => {
    try {
      const gameData = await getGame(code!)
      setGame(gameData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Partie non trouvée')
    } finally {
      setLoading(false)
    }
  }

  const handleSelectTeam = (teamId: number) => {
    navigate(`/team/${code}/${teamId}`)
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
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="card text-center max-w-md">
          <h2 className="text-2xl font-bold text-game-danger mb-4">❌ Partie non trouvée</h2>
          <p className="text-slate-400">{error}</p>
          <button onClick={() => navigate('/')} className="btn-primary mt-4">Retour</button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="max-w-md w-full space-y-6">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-white mb-2">🎮 Rejoindre la partie</h1>
          <p className="text-slate-400">Choisissez votre équipe</p>
          <div className="mt-4 inline-block bg-game-card border border-slate-600 rounded-lg px-4 py-2">
            <span className="text-slate-400 text-sm">Code : </span>
            <span className="text-2xl font-mono font-bold text-game-accent tracking-widest">{game.code}</span>
          </div>
        </div>

        <div className="space-y-3">
          {game.teams.length === 0 ? (
            <p className="text-slate-500 text-center py-8">
              Aucune équipe créée... attendez que l'hôte configure la partie
            </p>
          ) : (
            game.teams.map((team, index) => (
              <button
                key={team.id}
                onClick={() => handleSelectTeam(team.id)}
                className="w-full p-5 bg-slate-800 hover:bg-slate-700 border-2 border-slate-700 hover:border-game-accent rounded-xl text-left transition-all group"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <span className="text-3xl">
                      {['🔴', '🔵', '🟢', '🟡', '🟣', '🟠'][index % 6]}
                    </span>
                    <div>
                      <p className="text-xl font-bold text-white group-hover:text-game-accent transition-colors">
                        {team.name}
                      </p>
                      <p className="text-sm text-slate-400">
                        {team.players.length} joueurs • Score : {team.score} pts
                      </p>
                    </div>
                  </div>
                  <span className="text-slate-500 group-hover:text-game-accent transition-colors text-2xl opacity-0 group-hover:opacity-100">
                    →
                  </span>
                </div>
              </button>
            ))
          )}
        </div>

        <button onClick={() => navigate('/')} className="btn-secondary w-full">
          ← Retour
        </button>
      </div>
    </div>
  )
}

export default TeamJoin
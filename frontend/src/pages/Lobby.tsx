import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getGame, createTeam, startGame } from '../services/api'
import type { GameSession } from '../types'
import DevHelper from '../components/DevHelper'

function Lobby() {
  const { code } = useParams<{ code: string }>()
  const navigate = useNavigate()
  const [game, setGame] = useState<GameSession | null>(null)
  const [teamName, setTeamName] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    if (code) {
      loadGame()
    }
  }, [code])

  const loadGame = async () => {
    try {
      const gameData = await getGame(code!)
      setGame(gameData)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Session non trouvée')
    } finally {
      setLoading(false)
    }
  }

  const handleCreateTeam = async () => {
    if (!teamName.trim() || !code) return
    setCreating(true)
    try {
      await createTeam(code, { name: teamName.trim() })
      setTeamName('')
      await loadGame()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors de la création')
    } finally {
      setCreating(false)
    }
  }

  const handleStartGame = async () => {
    if (!code) return
    try {
      await startGame(code)
      navigate(`/game/${code}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Impossible de démarrer')
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
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="card text-center max-w-md">
          <h2 className="text-2xl font-bold text-game-danger mb-4">❌ Session non trouvée</h2>
          <p className="text-slate-400 mb-4">{error}</p>
          <button onClick={() => navigate('/')} className="btn-primary">
            Retour à l'accueil
          </button>
        </div>
      </div>
    )
  }

  const maxTeams = Math.floor(game.total_players / game.players_per_team)

  return (
    <div className="min-h-screen p-4">
      <DevHelper code={code!} />
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-3xl font-bold text-white">Salle d'attente</h1>
          <div className="mt-2 inline-block bg-game-card border border-slate-600 rounded-lg px-4 py-2">
            <span className="text-slate-400 text-sm">Code : </span>
            <span className="text-2xl font-mono font-bold text-game-accent tracking-widest">
              {game.code}
            </span>
          </div>
          <p className="mt-2 text-slate-400">
            {game.teams.length}/{maxTeams} équipes • {game.players_per_team} joueurs par équipe
          </p>
        </div>

        {/* Liste des équipes */}
        <div className="card">
          <h2 className="text-xl font-semibold mb-4">👥 Équipes</h2>
          {game.teams.length === 0 ? (
            <p className="text-slate-500 text-center py-4">Aucune équipe pour le moment...</p>
          ) : (
            <div className="space-y-3">
              {game.teams.map((team, index) => (
                <div
                  key={team.id}
                  className="flex items-center justify-between bg-slate-800 rounded-lg p-3 border border-slate-700"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">
                      {['🔴', '🔵', '🟢', '🟡', '🟣', '🟠'][index % 6]}
                    </span>
                    <div>
                      <p className="font-semibold">{team.name}</p>
                      <p className="text-sm text-slate-400">
                        {team.players.length}/{game.players_per_team} joueurs
                      </p>
                    </div>
                  </div>
                  <span className="text-sm text-slate-500">
                    Score : {team.score}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Ajouter une équipe et des joueurs */}
        {game.teams.length < maxTeams && (
          <div className="card">
            <h2 className="text-xl font-semibold mb-4">➕ Ajouter une équipe</h2>
            <div className="flex gap-3 mb-4">
              <input
                type="text"
                placeholder="Nom de l'équipe"
                value={teamName}
                onChange={(e) => setTeamName(e.target.value)}
                className="input-field"
              />
              <button
                onClick={handleCreateTeam}
                disabled={!teamName.trim() || creating}
                className="btn-primary whitespace-nowrap disabled:opacity-50"
              >
                {creating ? '...' : 'Ajouter'}
              </button>
            </div>
            
            <p className="text-xs text-slate-400 mt-2">
              Note: Pour démarrer, utilisez le bouton rouge "DEV: Fast Track" ci-dessus. Il créera automatiquement les joueurs nécessaires pour chaque équipe.
            </p>
          </div>
        )}

        {/* Erreur */}
        {error && (
          <div className="text-game-danger text-sm text-center bg-red-900/20 rounded-lg p-3">
            {error}
          </div>
        )}

        {/* Bouton démarrer */}
        <div className="flex gap-3">
          <button onClick={() => navigate('/')} className="btn-secondary flex-1">
            ← Retour
          </button>
          <button
            onClick={handleStartGame}
            disabled={game.teams.length < 2}
            className="btn-success flex-1 text-lg disabled:opacity-50 disabled:cursor-not-allowed"
          >
            🎯 Démarrer le jeu
          </button>
        </div>
      </div>
    </div>
  )
}

export default Lobby

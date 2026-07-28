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

  // Rafraîchit la liste des équipes/joueurs et le statut de la partie pour
  // que les autres appareils voient les arrivées et le lancement par l'hôte
  // sans avoir à recharger la page manuellement.
  useEffect(() => {
    if (!code) return
    const interval = setInterval(loadGame, 3000)
    return () => clearInterval(interval)
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
    const trimmedName = teamName.trim()
    if (!trimmedName || !code) return
    const nameTaken = game?.teams.some((t) => t.name.toLowerCase() === trimmedName.toLowerCase())
    if (nameTaken) {
      setError("Ce nom d'équipe est déjà pris dans cette partie")
      return
    }
    setCreating(true)
    try {
      await createTeam(code, { name: trimmedName })
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
      await loadGame()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Impossible de démarrer')
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-2xl text-text-muted animate-pulse">Chargement...</div>
      </div>
    )
  }

  if (!game) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="card text-center max-w-md">
          <h2 className="text-2xl font-bold text-danger mb-4">❌ Session non trouvée</h2>
          <p className="text-text-muted mb-4">{error}</p>
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
      {import.meta.env.DEV && <DevHelper code={code!} />}
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-3xl font-display font-semibold text-text">Salle d'attente</h1>
          <div className="mt-2 inline-block bg-surface border border-border rounded-lg px-4 py-2">
            <span className="text-text-muted text-sm">Code : </span>
            <span className="text-2xl font-display font-semibold text-accent tracking-widest">
              {game.code}
            </span>
          </div>
          <p className="mt-2 text-text-muted">
            {game.teams.length}/{maxTeams} équipes • {game.players_per_team} joueurs par équipe
          </p>
        </div>

        {/* Liste des équipes */}
        <div className="card">
          <h2 className="text-xl font-semibold mb-4">👥 Équipes</h2>
          {game.teams.length === 0 ? (
            <p className="text-text-muted text-center py-4">Aucune équipe pour le moment...</p>
          ) : (
            <div className="space-y-3">
              {game.teams.map((team, index) => (
                <div
                  key={team.id}
                  className="flex items-center justify-between bg-surface-raised rounded-lg p-3 border border-border"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">
                      {['🔴', '🔵', '🟢', '🟡', '🟣', '🟠'][index % 6]}
                    </span>
                    <div>
                      <p className="font-semibold text-text">{team.name}</p>
                      <p className="text-sm text-text-muted">
                        {team.players.length}/{game.players_per_team} joueurs
                      </p>
                    </div>
                  </div>
                  {game.started ? (
                    <button
                      onClick={() => navigate(`/team/${code}/${team.id}`)}
                      className="btn-primary text-sm px-3 py-1 min-h-[44px]"
                    >
                      Rejoindre →
                    </button>
                  ) : (
                    <span className="text-sm text-text-muted">
                      Score : {team.score}
                    </span>
                  )}
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
                className="btn-primary whitespace-nowrap disabled:opacity-50 min-h-[44px]"
              >
                {creating ? '...' : 'Ajouter'}
              </button>
            </div>

            {import.meta.env.DEV && (
              <p className="text-xs text-text-muted mt-2">
                Note: Pour démarrer, utilisez le bouton rouge "DEV: Fast Track" ci-dessus. Il créera automatiquement les joueurs nécessaires pour chaque équipe.
              </p>
            )}
          </div>
        )}

        {/* Erreur */}
        {error && (
          <div className="text-danger text-sm text-center bg-danger/10 rounded-lg p-3">
            {error}
          </div>
        )}

        {/* Boutons d'action */}
        {game.started ? (
          <div className="space-y-3">
            <div className="card text-center bg-success/10 border-success">
              <p className="text-success font-semibold text-lg mb-2">🎯 Jeu démarré !</p>
              <p className="text-sm text-text-muted">Chaque équipe peut rejoindre en cliquant sur "Rejoindre" ci-dessus.</p>
            </div>
            <div className="flex gap-3">
              <button onClick={() => navigate('/')} className="btn-secondary flex-1 min-h-[44px]">
                ← Retour
              </button>
              <button
                onClick={() => navigate(`/game/${code}/host`)}
                className="btn-secondary flex-1 text-sm min-h-[44px]"
              >
                📺 Écran hôte (optionnel)
              </button>
            </div>
          </div>
        ) : (
          <div className="flex gap-3">
            <button onClick={() => navigate('/')} className="btn-secondary flex-1 min-h-[44px]">
              ← Retour
            </button>
            <button
              onClick={handleStartGame}
              disabled={game.teams.length < 2}
              className="btn-success flex-1 text-lg disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px]"
            >
              🎯 Démarrer le jeu
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default Lobby

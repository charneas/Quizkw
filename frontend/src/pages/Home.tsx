import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { createGame } from '../services/api'

function Home() {
  const navigate = useNavigate()
  const [joinCode, setJoinCode] = useState('')
  const [totalPlayers, setTotalPlayers] = useState(6)
  const [playersPerTeam, setPlayersPerTeam] = useState(2)
  const [isCreating, setIsCreating] = useState(false)
  const [error, setError] = useState('')
  const [showCreate, setShowCreate] = useState(false)

  const handleCreateGame = async () => {
    setIsCreating(true)
    setError('')
    try {
      const result = await createGame({
        total_players: totalPlayers,
        players_per_team: playersPerTeam,
      })
      navigate(`/lobby/${result.game.code}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors de la création')
    } finally {
      setIsCreating(false)
    }
  }

  const handleJoinGame = () => {
    if (joinCode.trim()) {
      navigate(`/lobby/${joinCode.trim().toUpperCase()}`)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="max-w-md w-full space-y-8">
        {/* Hero — seul endroit de l'app avec une texture/dégradé décoratif (DESIGN.md) */}
        <div className="text-center relative py-4">
          <div className="absolute inset-0 -z-10 bg-gradient-to-b from-brand-muted/50 via-brand-muted/10 to-transparent rounded-full blur-2xl" />
          <h1 className="mx-auto font-display font-extrabold text-5xl tracking-tight text-text drop-shadow-[0_0_24px_rgba(139,92,246,0.45)]">
            Quiz<span className="text-brand">Climb</span>
          </h1>
          <p className="mt-3 text-text-muted text-lg">
            Le jeu de quiz en équipe !
          </p>
        </div>

        {/* Rejoindre une partie */}
        <div className="card">
          <h2 className="text-xl font-semibold mb-4">🎮 Rejoindre une partie</h2>
          <div className="flex gap-3">
            <input
              type="text"
              placeholder="Code de la partie"
              value={joinCode}
              onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === 'Enter' && handleJoinGame()}
              className="input-field uppercase tracking-widest text-center text-lg"
              maxLength={6}
            />
            <button
              onClick={handleJoinGame}
              disabled={!joinCode.trim()}
              className="btn-primary whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Rejoindre
            </button>
          </div>
        </div>

        {/* Créer une partie */}
        <div className="card">
          <h2 className="text-xl font-semibold mb-4">✨ Créer une partie</h2>
          
          {!showCreate ? (
            <button
              onClick={() => setShowCreate(true)}
              className="btn-secondary w-full"
            >
              Nouvelle partie
            </button>
          ) : (
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-text-muted mb-1">
                  Nombre total de joueurs
                </label>
                <input
                  type="number"
                  min={4}
                  max={12}
                  value={totalPlayers}
                  onChange={(e) => setTotalPlayers(Number(e.target.value))}
                  className="input-field"
                />
              </div>

              <div>
                <label className="block text-sm text-text-muted mb-1">
                  Joueurs par équipe
                </label>
                <div className="flex gap-3">
                  <button
                    onClick={() => setPlayersPerTeam(2)}
                    className={`flex-1 min-h-[44px] py-2 px-4 rounded-lg border transition-colors ${
                      playersPerTeam === 2
                        ? 'bg-brand-600 border-brand text-text'
                        : 'bg-surface border-border text-text-muted hover:border-brand'
                    }`}
                  >
                    2 joueurs
                  </button>
                  <button
                    onClick={() => setPlayersPerTeam(3)}
                    className={`flex-1 min-h-[44px] py-2 px-4 rounded-lg border transition-colors ${
                      playersPerTeam === 3
                        ? 'bg-brand-600 border-brand text-text'
                        : 'bg-surface border-border text-text-muted hover:border-brand'
                    }`}
                  >
                    3 joueurs
                  </button>
                </div>
              </div>

              <div className="text-sm text-text-muted text-center">
                {Math.floor(totalPlayers / playersPerTeam)} équipes de {playersPerTeam} joueurs
              </div>

              {error && (
                <div className="text-danger text-sm text-center bg-danger/10 rounded-lg p-2">
                  {error}
                </div>
              )}

              <button
                onClick={handleCreateGame}
                disabled={isCreating}
                className="btn-primary w-full"
              >
                {isCreating ? '⏳ Création...' : '🚀 Créer la partie'}
              </button>
            </div>
          )}
        </div>

        <div className="text-center">
          <Link to="/proposer" className="text-text-muted text-sm hover:text-text underline">
            Proposer une question
          </Link>
        </div>
      </div>
    </div>
  )
}

export default Home

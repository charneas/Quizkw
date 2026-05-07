import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
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
        {/* Logo / Titre */}
        <div className="text-center">
          <h1 className="text-6xl font-bold bg-gradient-to-r from-primary-400 to-game-accent bg-clip-text text-transparent">
            Quizkw
          </h1>
          <p className="mt-3 text-slate-400 text-lg">
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
                <label className="block text-sm text-slate-400 mb-1">
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
                <label className="block text-sm text-slate-400 mb-1">
                  Joueurs par équipe
                </label>
                <div className="flex gap-3">
                  <button
                    onClick={() => setPlayersPerTeam(2)}
                    className={`flex-1 py-2 px-4 rounded-lg border transition-colors ${
                      playersPerTeam === 2
                        ? 'bg-primary-600 border-primary-500 text-white'
                        : 'bg-slate-800 border-slate-600 text-slate-300 hover:border-slate-400'
                    }`}
                  >
                    2 joueurs
                  </button>
                  <button
                    onClick={() => setPlayersPerTeam(3)}
                    className={`flex-1 py-2 px-4 rounded-lg border transition-colors ${
                      playersPerTeam === 3
                        ? 'bg-primary-600 border-primary-500 text-white'
                        : 'bg-slate-800 border-slate-600 text-slate-300 hover:border-slate-400'
                    }`}
                  >
                    3 joueurs
                  </button>
                </div>
              </div>

              <div className="text-sm text-slate-400 text-center">
                {Math.floor(totalPlayers / playersPerTeam)} équipes de {playersPerTeam} joueurs
              </div>

              {error && (
                <div className="text-game-danger text-sm text-center bg-red-900/20 rounded-lg p-2">
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
      </div>
    </div>
  )
}

export default Home

import { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { createGame, storeHostToken } from '../services/api'
import { pluralJoueurs } from '../utils/pluralize'
import { useDiscordAccount } from '../contexts/DiscordAccountContext'

const PLAYERS_PER_TEAM_OPTIONS = [
  { value: 1, label: '1 joueur' },
  { value: 2, label: '2 joueurs' },
  { value: 3, label: '3 joueurs' },
]

const QUESTION_COUNT_OPTIONS = [20, 25, 30, 35, 40, 45, 50]

const WHEEL_FREQUENCY_OPTIONS = [5, 10]

function Home() {
  const navigate = useNavigate()
  const [joinCode, setJoinCode] = useState('')
  const [totalPlayers, setTotalPlayers] = useState(6)
  const [playersPerTeam, setPlayersPerTeam] = useState(2)
  const [questionCount, setQuestionCount] = useState(20)
  const [wheelFrequency, setWheelFrequency] = useState(5)
  const [isCreating, setIsCreating] = useState(false)
  const [error, setError] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  // Story O.2.1 (revue de code) : le compte connecté vient désormais de
  // DiscordAccountContext, partagé avec AccountButton (App.tsx) — une seule
  // requête réseau, un seul état, plus de désynchronisation possible entre
  // les deux composants après un logout.
  const { account, isLoading: isAccountLoading } = useDiscordAccount()
  const isDiscordConnected = account !== null

  useEffect(() => {
    // Le callback OAuth redirige vers `/?discord=connected` (backend, inchangé
    // par cette story) — plus rien ne lit ce paramètre pour décider de l'état
    // connecté (porté par le contexte), mais il faut encore le retirer de la
    // barre d'adresse.
    if (new URLSearchParams(window.location.search).get('discord') === 'connected') {
      window.history.replaceState({}, '', window.location.pathname)
    }
  }, [])

  const handleDiscordLogin = () => {
    window.location.href = '/api/auth/discord/login'
  }

  const handleCreateGame = async () => {
    setIsCreating(true)
    setError('')
    try {
      const result = await createGame({
        total_players: totalPlayers,
        players_per_team: playersPerTeam,
        manche1_question_count: questionCount,
        wheel_frequency: wheelFrequency,
      })
      storeHostToken(result.game.code, result.host_token)
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
      {/* Revue de code : attendre la résolution initiale de GET
          /auth/discord/me avant d'afficher "Connexion" — sinon un
          utilisateur déjà connecté voit ce bouton clignoter le temps de
          l'aller-retour réseau (account vaut null jusque-là, indiscernable
          de "non connecté"). */}
      {!isAccountLoading && !isDiscordConnected && (
        <div className="fixed top-4 right-16 z-40 flex flex-col items-end gap-1 max-w-[200px]">
          <button
            onClick={handleDiscordLogin}
            className="min-h-[44px] px-4 rounded bg-[#5865F2] text-white font-medium hover:scale-105 transition-transform"
          >
            Connexion
          </button>
          <p className="text-xs text-text-muted text-right">
            Quizkw conserve ton identifiant, ton pseudo et ton avatar Discord — tu peux les supprimer à tout moment depuis ton Profil.
          </p>
        </div>
      )}
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
          {/* flex-col en dessous de sm : à 360px de large, le placeholder en
              tracking-widest + le bouton ne tenaient pas côte à côte et se
              tronquaient l'un l'autre. */}
          <div className="flex flex-col sm:flex-row gap-3">
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
                  {PLAYERS_PER_TEAM_OPTIONS.map((option) => (
                    <button
                      key={option.value}
                      onClick={() => setPlayersPerTeam(option.value)}
                      className={`flex-1 min-h-[44px] py-2 px-4 rounded-lg border transition-colors ${
                        playersPerTeam === option.value
                          ? 'bg-brand-600 border-brand text-white'
                          : 'bg-surface border-border text-text-muted hover:border-brand'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="text-sm text-text-muted text-center">
                {Math.floor(totalPlayers / playersPerTeam)} équipes de {playersPerTeam} {pluralJoueurs(playersPerTeam)}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-text-muted mb-1">
                    Questions (Manche 1)
                  </label>
                  <select
                    value={questionCount}
                    onChange={(e) => setQuestionCount(Number(e.target.value))}
                    className="input-field text-sm py-1.5"
                  >
                    {QUESTION_COUNT_OPTIONS.map((count) => (
                      <option key={count} value={count}>
                        {count} questions
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs text-text-muted mb-1">
                    Tours entre chaque roue
                  </label>
                  <select
                    value={wheelFrequency}
                    onChange={(e) => setWheelFrequency(Number(e.target.value))}
                    className="input-field text-sm py-1.5"
                  >
                    {WHEEL_FREQUENCY_OPTIONS.map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                </div>
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

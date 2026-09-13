import { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { createGame, createBlindtestGame, storeHostToken, joinPublicQueue } from '../services/api'
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
  const [blindtestCode, setBlindtestCode] = useState('')
  const [isCreatingBlindtest, setIsCreatingBlindtest] = useState(false)
  const [blindtestCreateError, setBlindtestCreateError] = useState('')
  const [totalPlayers, setTotalPlayers] = useState(6)
  const [playersPerTeam, setPlayersPerTeam] = useState(2)
  const [questionCount, setQuestionCount] = useState(20)
  const [wheelFrequency, setWheelFrequency] = useState(5)
  const [isCreating, setIsCreating] = useState(false)
  const [error, setError] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [soloFinale, setSoloFinale] = useState(false)
  const [publicPseudo, setPublicPseudo] = useState('')
  const [isJoiningPublic, setIsJoiningPublic] = useState(false)
  const [publicError, setPublicError] = useState('')
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
        total_players: soloFinale ? 4 : totalPlayers,
        players_per_team: soloFinale ? 1 : playersPerTeam,
        manche1_question_count: questionCount,
        wheel_frequency: wheelFrequency,
        is_solo_finale: soloFinale,
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

  const handleJoinBlindtest = () => {
    if (blindtestCode.trim()) {
      navigate(`/blindtest/${blindtestCode.trim().toUpperCase()}`)
    }
  }

  const handleCreateBlindtestGame = async () => {
    setIsCreatingBlindtest(true)
    setBlindtestCreateError('')
    try {
      const result = await createBlindtestGame()
      navigate(`/blindtest/${result.code}`)
    } catch (err) {
      setBlindtestCreateError(err instanceof Error ? err.message : 'Erreur lors de la création')
    } finally {
      setIsCreatingBlindtest(false)
    }
  }

  const handleJoinPublicQueue = async () => {
    const pseudo = publicPseudo.trim()
    if (!pseudo) return
    setIsJoiningPublic(true)
    setPublicError('')
    try {
      const result = await joinPublicQueue(pseudo)
      navigate(`/public-queue/${result.code}`)
    } catch (err) {
      setPublicError(err instanceof Error ? err.message : 'Erreur lors de la connexion à la file')
    } finally {
      setIsJoiningPublic(false)
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
        <div className="fixed top-4 right-16 z-40 flex flex-col items-end gap-1 max-w-[200px] group">
          <button
            onClick={handleDiscordLogin}
            aria-describedby="discord-data-retention-notice"
            className="min-h-[44px] px-4 rounded bg-[#5865F2] text-white font-medium hover:scale-105 transition-transform"
          >
            Connexion
          </button>
          {/* Toujours présent dans le DOM (annoncé par les lecteurs d'écran
              via aria-describedby), mais visible seulement au survol/focus
              du bouton — permanent, il alourdissait l'accueil pour un texte
              qui ne concerne que le geste de connexion (retour utilisateur). */}
          <p
            id="discord-data-retention-notice"
            className="text-xs text-text-muted text-right opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity"
          >
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

        {/* Blindtest (spec-blindtest-integration-ui, story 1) : rejoindre
            une partie blindtest par code — mirroir exact de la carte
            "Rejoindre une partie" ci-dessus, aucune copie explicative sur la
            création (manuelle pour l'instant, hors scope). */}
        {/* Story 6 (spec-blindtest-integration-ui) : `text-accent` (magenta
            Neon Pit Lane) sur le titre, seule touche de couleur distincte du
            quiz — usage restreint au texte, jamais en fond (DESIGN.md
            Do's/Don'ts). */}
        <div className="card">
          <h2 className="text-xl font-semibold mb-4 text-accent">🎵 Blindtest</h2>
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              type="text"
              placeholder="Code de la partie"
              value={blindtestCode}
              onChange={(e) => setBlindtestCode(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === 'Enter' && handleJoinBlindtest()}
              className="input-field uppercase tracking-widest text-center text-lg"
              maxLength={6}
            />
            <button
              onClick={handleJoinBlindtest}
              disabled={!blindtestCode.trim()}
              className="btn-primary whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Rejoindre
            </button>
          </div>
          {/* Story 2 (spec-blindtest-integration-ui) : créer une partie
              blindtest en self-serve, symétrique à handleCreateGame côté
              quiz — sans champs de configuration (aucun réglage à la
              création côté blindtest). */}
          <button
            onClick={handleCreateBlindtestGame}
            disabled={isCreatingBlindtest}
            className="btn-secondary w-full mt-3 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isCreatingBlindtest ? '⏳ Création...' : 'Créer une partie'}
          </button>
          {blindtestCreateError && (
            <div className="text-danger text-sm text-center bg-danger/10 rounded-lg p-2 mt-3">
              {blindtestCreateError}
            </div>
          )}
        </div>

        {/* Jouer avec des inconnus (spec-rooms-publiques) : file d'attente
            publique auto-remplie, aucun code requis pour rejoindre. */}
        <div className="card">
          <h2 className="text-xl font-semibold mb-4">🌍 Jouer avec des inconnus</h2>
          <p className="text-sm text-text-muted mb-3">
            Rejoins une file d'attente publique — dès que 4 joueurs sont réunis, la partie démarre automatiquement.
          </p>
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              type="text"
              placeholder="Ton pseudo"
              value={publicPseudo}
              onChange={(e) => setPublicPseudo(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleJoinPublicQueue()}
              className="input-field"
              maxLength={30}
            />
            <button
              onClick={handleJoinPublicQueue}
              disabled={!publicPseudo.trim() || isJoiningPublic}
              className="btn-primary whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px]"
            >
              {isJoiningPublic ? '⏳ Connexion...' : 'Jouer avec des inconnus'}
            </button>
          </div>
          {publicError && (
            <div className="text-danger text-sm text-center bg-danger/10 rounded-lg p-2 mt-3">
              {publicError}
            </div>
          )}
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
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={soloFinale}
                  onChange={(e) => setSoloFinale(e.target.checked)}
                  className="w-5 h-5 accent-brand"
                />
                <span className="text-sm text-text">🏁 Manche 3 directe</span>
              </label>

              <div
                className={`grid transition-[grid-template-rows,opacity] duration-300 ease-in-out ${
                  soloFinale ? 'grid-rows-[0fr] opacity-0' : 'grid-rows-[1fr] opacity-100'
                }`}
                aria-hidden={soloFinale}
              >
                <div className="overflow-hidden space-y-4">
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
                      tabIndex={soloFinale ? -1 : undefined}
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
                          tabIndex={soloFinale ? -1 : undefined}
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="text-sm text-text-muted text-center">
                    {Math.floor(totalPlayers / playersPerTeam)} équipes de {playersPerTeam} {pluralJoueurs(playersPerTeam)}
                  </div>
                </div>
              </div>

              <div
                className={`grid transition-[grid-template-rows,opacity] duration-300 ease-in-out ${
                  soloFinale ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'
                }`}
              >
                <div className="overflow-hidden">
                  <div className="text-sm text-text-muted text-center bg-brand-muted/20 rounded-lg p-2">
                    4 joueurs, chacun pour soi — direct sur le memory grid
                  </div>
                </div>
              </div>

              <div
                className={`grid transition-[grid-template-rows,opacity] duration-300 ease-in-out ${
                  soloFinale ? 'grid-rows-[0fr] opacity-0' : 'grid-rows-[1fr] opacity-100'
                }`}
                aria-hidden={soloFinale}
              >
                <div className="overflow-hidden grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-text-muted mb-1">
                      Questions (Manche 1)
                    </label>
                    <select
                      value={questionCount}
                      onChange={(e) => setQuestionCount(Number(e.target.value))}
                      className="input-field text-sm py-1.5"
                      tabIndex={soloFinale ? -1 : undefined}
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
                      tabIndex={soloFinale ? -1 : undefined}
                    >
                      {WHEEL_FREQUENCY_OPTIONS.map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </div>
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

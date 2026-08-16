import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  getRound2Themes,
  selectTheme,
  getRound2Question,
  submitRound2Answer,
  getRound2Leaderboard,
  advanceRound2Phase,
  getRound2Progress,
  getGame,
  getRound2QualifiedPlayers,
  getHostToken
} from '../services/api'
import type { Round2QualifiedPlayer } from '../services/api'
import type {
  Theme,
  PlayerRound2Stats,
  Round2QuestionResponse,
  Round2AnswerResponse,
  TournamentProgress,
  IntermediateLeaderboardResponse,
  GameSession,
  Player
} from '../types'
import PlayerSelection from '../components/PlayerSelection'
import TournamentProgressComponent from '../components/TournamentProgress'
import ThemeSelectorComponent from '../components/ThemeSelector'
import IntermediateLeaderboardComponent from '../components/IntermediateLeaderboard'
import SpectatorView from '../components/SpectatorView'
import type { RoundType } from '../types'

function getCurrentRoundPath(code: string, round?: RoundType) {
  switch (round) {
    case 'manche_1':
      return `/game/${code}`
    case 'manche_3':
      return `/game/${code}/memory-grid`
    case 'manche_2':
    default:
      return `/game/${code}/round2`
  }
}

function Round2() {
  const { code } = useParams<{ code: string }>()
  const navigate = useNavigate()
  
  const [game, setGame] = useState<GameSession | null>(null)
  const [currentPlayer, setCurrentPlayer] = useState<Player | null>(null)
  const [themes, setThemes] = useState<Theme[]>([])
  const [selectedTheme, setSelectedTheme] = useState<Theme | null>(null)
  const [playerStats, setPlayerStats] = useState<PlayerRound2Stats | null>(null)
  const [currentQuestion, setCurrentQuestion] = useState<Round2QuestionResponse | null>(null)
  const [answerResult, setAnswerResult] = useState<Round2AnswerResponse | null>(null)
  const [tournamentProgress, setTournamentProgress] = useState<TournamentProgress | null>(null)
  const [leaderboard, setLeaderboard] = useState<IntermediateLeaderboardResponse | null>(null)
  const [isWaitingForLeaderboard, setIsWaitingForLeaderboard] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [timeRemaining, setTimeRemaining] = useState<number | null>(null)
  // Joueurs réellement qualifiés depuis la Manche 1 — permet de se
  // reconnecter sous sa vraie identité plutôt que de créer un joueur libre
  // jamais relié à la qualification (bug utilisateur).
  const [qualifiedPlayers, setQualifiedPlayers] = useState<Round2QualifiedPlayer[]>([])
  // Question du joueur actif, visible en lecture seule par les spectateurs
  // (bug 2026-08-12 : le spectateur ne voyait que le nom/thème du joueur
  // actif, jamais la question qu'il est en train de résoudre).
  const [activePlayerQuestion, setActivePlayerQuestion] = useState<Round2QuestionResponse | null>(null)

  useEffect(() => {
    if (code) initializeRound2()
  }, [code])

  const initializeRound2 = async () => {
    try {
      setLoading(true)
      // Load game session
      const gameData = await getGame(code!)
      setGame(gameData)

      // Get tournament progress
      const progress = await getRound2Progress(code!)
      setTournamentProgress(progress)

      // Get available themes
      const themesData = await getRound2Themes(code!)
      setThemes(themesData.themes)

      const qualified = await getRound2QualifiedPlayers(code!)
      setQualifiedPlayers(qualified)

      // BUG-501 (#33) : ré-identifier automatiquement le joueur depuis le
      // pseudo saisi une seule fois en Manche 1 (stocké par joinTeam via
      // storePlayerIdentity), au lieu de le renvoyer sur l'écran "qui
      // êtes-vous ?" à chaque entrée en Manche 2.
      // BUG-207 : restaurer l'état d'un joueur ayant déjà choisi un thème
      // (refresh/reconnect en pleine manche) plutôt que de le laisser sur
      // ThemeSelector, qui échoue en backend avec "already selected a theme"
      // et bloque la page sans retour possible vers la question en cours.
      const savedPlayerRaw = localStorage.getItem(`quizkw_player_${code}`)
      if (savedPlayerRaw) {
        try {
          const savedPlayer = JSON.parse(savedPlayerRaw)
          const existing = qualified.find(p => p.id === savedPlayer.id)
          const savedStats = existing?.round2_stats
          if (existing) {
            // Le joueur est bien parmi les qualifiés de cette partie : on
            // peut le réidentifier sans repasser par PlayerSelection, qu'il
            // ait déjà choisi un thème ou non.
            setCurrentPlayer(savedPlayer)
          }
          // BUG-401 (#32) : un joueur éliminé (coupure 16→8 ou 8→4) ne doit
          // plus jamais rappeler getRound2Question — l'endpoint renvoie 400
          // ("le joueur ne participe plus à ce round") et laissait l'écran
          // figé sur un message d'erreur générique. La bascule spectateur
          // (rendu JSX, dérivé de `isEliminated`) prend le relai à la place.
          if (savedStats?.theme && savedStats.qualification_status !== 'eliminated') {
            setSelectedTheme(savedStats.theme)
            const hydratedStats: PlayerRound2Stats = {
              id: 0,
              player_id: savedPlayer.id,
              game_session_id: gameData.id,
              theme_id: savedStats.theme_id ?? undefined,
              score: savedStats.score,
              questions_answered: savedStats.questions_answered,
              correct_answers: savedStats.correct_answers,
              current_question_index: savedStats.current_question_index,
              qualification_status: savedStats.qualification_status,
            }
            setPlayerStats(hydratedStats)
            if (savedStats.questions_answered < 10) {
              // Ne recharger la question que si c'est vraiment le tour de ce
              // joueur — sinon un spectateur qui rafraîchit la page
              // déclencherait getRound2Question et se prendrait un 400 "pas
              // votre tour" au lieu de retomber sur le mode spectateur.
              if (progress.current_turn_player_id === savedPlayer.id) {
                await loadNextQuestion(hydratedStats, savedPlayer.id)
              }
            } else {
              setIsWaitingForLeaderboard(true)
              await checkIfAllPlayersFinished()
            }
          }
        } catch (e) {
          // Hydratation best-effort : en cas d'échec on retombe sur le flux normal.
        }
      }

      setLoading(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur au chargement de la Manche 2')
      setLoading(false)
    }
  }

  const handlePlayerSelection = (player: Player) => {
    setCurrentPlayer(player)
    // Store player in localStorage for reconnection
    localStorage.setItem(`quizkw_player_${code}`, JSON.stringify(player))
  }

  const handleThemeSelection = async (theme: Theme) => {
    if (!currentPlayer) {
      setError("Veuillez d'abord sélectionner un joueur")
      return
    }

    try {
      const response = await selectTheme(code!, { player_id: currentPlayer.id, theme_id: theme.id })
      setSelectedTheme(response.theme)
      setPlayerStats(response.player_stats)
      setError('')
      
      // Load first question
      await loadNextQuestion(response.player_stats, currentPlayer.id)
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Une erreur est survenue lors de la sélection du thème.');
      }
      // Le thème peut avoir été pris par un autre joueur entre le chargement
      // de la liste et ce clic (BUG-210) — on rafraîchit pour ne pas laisser
      // l'utilisateur cliquer à nouveau sur une option devenue invalide.
      try {
        const themesData = await getRound2Themes(code!)
        setThemes(themesData.themes)
      } catch {
        // Le message d'erreur ci-dessus reste affiché même si ce refresh échoue.
      }
    }
  }

  const loadNextQuestion = async (stats: PlayerRound2Stats, playerId: number) => {
    if (!stats) return

    try {
      const question = await getRound2Question(code!, playerId)
      setCurrentQuestion(question)
      setAnswerResult(null)
      setTimeRemaining(question.time_limit)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur au chargement de la question')
    }
  }

  // Timer countdown
  useEffect(() => {
    if (timeRemaining === null || timeRemaining <= 0 || answerResult) return

    const timer = setInterval(() => {
      setTimeRemaining(prev => (prev && prev > 0) ? prev - 1 : 0)
    }, 1000)

    return () => clearInterval(timer)
  }, [timeRemaining, answerResult])

  // Temps écoulé sans réponse : soumission automatique d'une réponse vide
  // (comptée fausse côté serveur) pour ne pas rester bloqué sur la question
  // indéfiniment. Ne se déclenche qu'une fois (timeRemaining reste à 0 après).
  useEffect(() => {
    if (timeRemaining !== 0 || answerResult || !isMyTurn || !currentQuestion) return
    handleAnswerSubmit('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeRemaining])

  // Le classement intermédiaire (PlayerRound2Stats) n'a que player_id, pas de
  // nom — dérivé de qualifiedPlayers (déjà chargé) plutôt que d'ajouter un
  // appel réseau ou un champ backend supplémentaire.
  const playerNamesById = Object.fromEntries(qualifiedPlayers.map((p) => [p.id, p.name]))

  // BUG-401 (#32) : dérivé de qualifiedPlayers (déjà chargé, aucun appel
  // réseau supplémentaire) — couvre aussi bien la restauration automatique
  // que la sélection manuelle via PlayerSelection (handlePlayerSelection).
  const currentPlayerQualification = qualifiedPlayers.find(
    (p) => p.id === currentPlayer?.id
  )?.round2_stats?.qualification_status
  const isEliminated = currentPlayerQualification === 'eliminated'

  // Manche 2 en tour par rôle : c'est mon tour si le serveur me désigne
  // comme current_turn_player_id pendant la phase à 16 joueurs.
  const isMyTurn = !!currentPlayer && tournamentProgress?.current_turn_player_id === currentPlayer.id

  // Manche 2 à deux thèmes (2026-08-12) : questions_answered est cumulatif
  // sur les 20 questions (2 thèmes de 10) alors que current_question_index
  // repart à 0 à chaque thème — on en déduit le round affiché (1 ou 2) sans
  // champ dédié côté backend.
  const roundNumber = (playerStats?.questions_answered ?? 0) >= 10 ? 2 : 1

  // Manche 2 en tour par rôle : les spectateurs (ce n'est pas leur tour)
  // pollent la progression pour détecter le changement de tour sans action
  // de leur part.
  useEffect(() => {
    if (!code || !currentPlayer || isEliminated) return
    if (tournamentProgress?.phase !== '16_players') return
    if (tournamentProgress?.current_turn_player_id === currentPlayer.id) return

    const interval = setInterval(async () => {
      try {
        const progress = await getRound2Progress(code)
        setTournamentProgress(progress)
      } catch {
        // Best-effort : on retentera au prochain intervalle.
      }
    }, 4000)

    return () => clearInterval(interval)
  }, [code, currentPlayer, isEliminated, tournamentProgress?.phase, tournamentProgress?.current_turn_player_id])

  // Spectateurs : récupérer (en lecture seule) la question du joueur actif
  // pour l'afficher pendant qu'il répond. getRound2Question n'a pas d'effet
  // de bord et n'est pas restreint au joueur dont c'est le tour.
  useEffect(() => {
    const activePlayerId = tournamentProgress?.current_turn_player_id
    if (!code || !currentPlayer || isEliminated) return
    if (tournamentProgress?.phase !== '16_players') return
    if (!activePlayerId || activePlayerId === currentPlayer.id) {
      setActivePlayerQuestion(null)
      return
    }

    let cancelled = false
    const fetchActiveQuestion = async () => {
      try {
        const question = await getRound2Question(code, activePlayerId)
        if (!cancelled) setActivePlayerQuestion(question)
      } catch {
        // Le joueur actif n'a pas encore choisi de thème ou vient de
        // terminer sa question : on masque simplement le bloc plutôt que
        // d'afficher une erreur.
        if (!cancelled) setActivePlayerQuestion(null)
      }
    }

    fetchActiveQuestion()
    const interval = setInterval(fetchActiveQuestion, 4000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [code, currentPlayer, isEliminated, tournamentProgress?.phase, tournamentProgress?.current_turn_player_id])

  // BUG (2026-08-12) : une fois le classement intermédiaire affiché
  // ("8_qualified"), plus aucun polling ne tournait — checkIfAllPlayersFinished
  // ne se relance qu'en phase "16_players". Un joueur non-host restait donc
  // bloqué sur cet écran même après que l'host ait désigné les finalistes
  // (phase "4_finalists" côté serveur), tant qu'il ne rafraîchissait pas la
  // page manuellement.
  useEffect(() => {
    if (!code || !currentPlayer || isEliminated) return
    if (tournamentProgress?.phase !== '8_qualified') return

    const interval = setInterval(async () => {
      try {
        const progress = await getRound2Progress(code)
        setTournamentProgress(progress)
      } catch {
        // Best-effort : on retentera au prochain intervalle.
      }
    }, 4000)

    return () => clearInterval(interval)
  }, [code, currentPlayer, isEliminated, tournamentProgress?.phase])

  const handleAnswerSubmit = async (answer: string) => {
    if (!currentQuestion || !playerStats || !currentPlayer) return
    
    try {
      const result = await submitRound2Answer(code!, {
        player_id: currentPlayer.id,
        question_id: currentQuestion.question.id,
        player_answer: answer
      })
      setAnswerResult(result)
      
      // Update player stats locally
      setPlayerStats(prev => prev ? {
        ...prev,
        score: result.player_score,
        questions_answered: prev.questions_answered + 1,
        correct_answers: result.is_correct ? prev.correct_answers + 1 : prev.correct_answers,
        current_question_index: prev.current_question_index + 1
      } : prev)

      // Update tournament progress
      const updatedProgress = await getRound2Progress(code!)
      setTournamentProgress(updatedProgress)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur lors de l'envoi de la réponse")
    }
  }

  const handleNextQuestion = async () => {
    const finishedRound1Only = !answerResult?.next_question_available && answerResult?.qualification_status === 'playing'
    const finishedBothRounds = !answerResult?.next_question_available && answerResult?.qualification_status !== 'playing'
    setAnswerResult(null)
    if (answerResult?.next_question_available) {
      await loadNextQuestion(playerStats!, currentPlayer!.id)
    } else if (finishedRound1Only) {
      // Manche 2 à deux thèmes (2026-08-12) : round 1 terminé mais le round 2
      // (nouveau thème) reste à jouer — pas encore la fin du round complet
      // (BUG-205 : reset currentQuestion pour ne pas réafficher "Question Flow").
      setCurrentQuestion(null)
      setSelectedTheme(null)
      setPlayerStats(prev => prev ? { ...prev, theme_id: undefined, current_question_index: 0 } : prev)
      try {
        const themesData = await getRound2Themes(code!)
        setThemes(themesData.themes)
      } catch {
        // Best-effort : le ThemeSelector se rechargera de toute façon à la
        // prochaine ouverture si cet appel échoue.
      }
    } else if (finishedBothRounds) {
      // Player has finished all questions (BUG-205 : sans ce reset,
      // currentQuestion garde la dernière question et le bloc "Question Flow"
      // se réaffiche dès que answerResult repasse à null ci-dessus).
      setCurrentQuestion(null)
      setIsWaitingForLeaderboard(true)
      await checkIfAllPlayersFinished()
    }
  }

  const checkIfAllPlayersFinished = async () => {
    try {
      const progress = await getRound2Progress(code!)
      setTournamentProgress(progress)
      
      if (progress.phase === '16_players') {
        // Still waiting for other players
        setTimeout(async () => {
          await checkIfAllPlayersFinished()
        }, 5000)
      } else if (progress.phase === '8_qualified') {
        // Intermediate leaderboard is ready
        await loadLeaderboard()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors de la vérification de la progression')
    }
  }

  const loadLeaderboard = async () => {
    try {
      const leaderboardData = await getRound2Leaderboard(code!)
      setLeaderboard(leaderboardData)
      setIsWaitingForLeaderboard(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur au chargement du classement')
    }
  }

  const handleAdvancePhase = async () => {
    try {
      await advanceRound2Phase(code!)
      
      // Update tournament progress
      const updatedProgress = await getRound2Progress(code!)
      setTournamentProgress(updatedProgress)
      
      // Load updated leaderboard
      await loadLeaderboard()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors du passage à la phase suivante')
    }
  }

  const getCurrentPhaseText = () => {
    if (!tournamentProgress) return ''
    
    switch (tournamentProgress.phase) {
      case '16_players':
        return 'Phase à 16 joueurs — choisissez un thème et répondez aux questions'
      case '8_qualified':
        return 'Phase à 8 qualifiés — classement intermédiaire'
      case '4_finalists':
        return '4 finalistes — prêts pour la Manche 3'
      default:
        return ''
    }
  }

  // Check for saved player on mount
  useEffect(() => {
    if (code) {
      const savedPlayer = localStorage.getItem(`quizkw_player_${code}`)
      if (savedPlayer) {
        try {
          const player = JSON.parse(savedPlayer)
          setCurrentPlayer(player)
        } catch (e) {
          // Invalid saved player, ignore
        }
      }
    }
  }, [code])

  // Question chronométrée en cours : quitter maintenant coupe la réponse en
  // train d'être tapée sans aucun avertissement, d'où la confirmation.
  const isAnsweringQuestion = !isEliminated && !!selectedTheme && !!currentQuestion && !answerResult
  const handleReturnToGame = () => {
    if (isAnsweringQuestion && !window.confirm('Une question est en cours — quitter maintenant coupera votre réponse. Continuer ?')) {
      return
    }
    // `game.current_round` ne bascule sur manche_3 qu'au démarrage effectif
    // de la grille mémoire par l'hôte (cf. main_memory_grid_legacy.py) — il
    // reste sur manche_2 pendant toute la phase "4 finalistes". Sans ce
    // garde, le bouton renvoyait vers cette même page (no-op).
    if (tournamentProgress?.phase === '4_finalists') {
      navigate(`/game/${code}/memory-grid`)
      return
    }
    navigate(getCurrentRoundPath(code!, game?.current_round))
  }

  return (
    <div className="min-h-screen bg-bg p-4 md:p-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <header className="mb-8">
          <h1 className="text-4xl font-display font-semibold text-text mb-2">Manche 2 : Tournoi 16→8→4</h1>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-text-muted">Code de la partie : {code}</p>
              <p className="text-text-muted">{getCurrentPhaseText()}</p>
              {currentPlayer && (
                <p className="text-text-muted">Joueur : <span className="text-text">{currentPlayer.name}</span></p>
              )}
            </div>
            <button
              className="btn-secondary disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={!game}
              onClick={handleReturnToGame}
            >
              ← Retour au jeu
            </button>
          </div>
        </header>

        {/* Tournament Progress */}
        {tournamentProgress && (
          <TournamentProgressComponent 
            progress={tournamentProgress} 
            currentPlayerId={currentPlayer?.id}
          />
        )}

        {/* Loading */}
        {loading && (
          <div className="bg-surface rounded-lg p-8 text-center">
            <div className="animate-spin h-8 w-8 border-4 border-text border-t-transparent rounded-full mx-auto mb-4"></div>
            <p className="text-text">Chargement de la Manche 2...</p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-danger/90 border border-danger rounded-lg p-4 mb-4 animate-fade-in">
            <div className="flex items-center">
              <span className="text-2xl mr-3">⚠️</span>
              <div>
                <p className="text-text font-semibold mb-1">Erreur</p>
                <p className="text-text">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Player Selection */}
        {!loading && !error && !currentPlayer && (
          <PlayerSelection
            gameCode={code!}
            onSelectPlayer={handlePlayerSelection}
            existingPlayers={qualifiedPlayers}
          />
        )}

        {/* Spectateur (BUG-401 / #32) : joueur éliminé (coupure 16→8 ou
            8→4) — prioritaire sur les blocs thème/question ci-dessous, qui
            ne doivent plus jamais s'afficher ni appeler l'API une fois ce
            statut atteint. */}
        {!loading && !error && currentPlayer && isEliminated && tournamentProgress?.phase !== '4_finalists' && (
          <SpectatorView>
            {tournamentProgress && (
              <TournamentProgressComponent progress={tournamentProgress} currentPlayerId={currentPlayer.id} />
            )}
            <div className="bg-surface rounded-lg p-6">
              <h3 className="text-lg font-semibold text-text mb-3">Joueurs en cours</h3>
              <div className="space-y-2">
                {qualifiedPlayers
                  .filter((p) => p.round2_stats && p.round2_stats.qualification_status !== 'eliminated')
                  .map((p) => (
                    <div key={p.id} className="flex items-center justify-between text-sm">
                      <span className="text-text">
                        {p.name}
                        {p.round2_stats?.theme && (
                          <span className="text-text-muted"> — {p.round2_stats.theme.name}</span>
                        )}
                      </span>
                      <span className="text-text-muted">{p.round2_stats?.score ?? 0} pts</span>
                    </div>
                  ))}
              </div>
            </div>
          </SpectatorView>
        )}

        {/* Spectateur (tour par rôle) : le joueur est qualifié et pas
            éliminé mais ce n'est pas son tour — il regarde le tour du
            joueur actif sans pouvoir agir. */}
        {!loading && !error && currentPlayer && !isEliminated && !isMyTurn &&
          tournamentProgress?.phase === '16_players' && (
          <SpectatorView
            message={
              tournamentProgress.current_turn_player_name
                ? `En attente du tour de ${tournamentProgress.current_turn_player_name}...`
                : 'En attente du prochain tour...'
            }
          >
            {activePlayerQuestion && (
              <div className="bg-surface rounded-lg p-6">
                <h3 className="text-lg font-semibold text-text mb-3">
                  Question de {tournamentProgress.current_turn_player_name ?? 'ce joueur'}
                  {' '}({activePlayerQuestion.question_number}/10, difficulté {activePlayerQuestion.difficulty}/10)
                </h3>
                <div className="bg-surface-raised rounded p-4 mb-4">
                  <p className="text-text text-lg">{activePlayerQuestion.question.text}</p>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {activePlayerQuestion.options.map((option, index) => (
                    <div
                      key={index}
                      className="bg-surface-raised text-text-muted p-4 rounded-lg text-center"
                    >
                      {option}
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="bg-surface rounded-lg p-6">
              <h3 className="text-lg font-semibold text-text mb-3">Joueurs en cours</h3>
              <div className="space-y-2">
                {qualifiedPlayers
                  .filter((p) => p.round2_stats && p.round2_stats.qualification_status !== 'eliminated')
                  .map((p) => (
                    <div key={p.id} className="flex items-center justify-between text-sm">
                      <span className="text-text">
                        {p.name}
                        {p.round2_stats?.theme && (
                          <span className="text-text-muted"> — {p.round2_stats.theme.name}</span>
                        )}
                      </span>
                      <span className="text-text-muted">{p.round2_stats?.score ?? 0} pts</span>
                    </div>
                  ))}
              </div>
            </div>
          </SpectatorView>
        )}

        {/* Theme Selection */}
        {!loading && !error && currentPlayer && !isEliminated && isMyTurn && themes.length > 0 && !selectedTheme && (
          <ThemeSelectorComponent
            themes={themes}
            onSelectTheme={handleThemeSelection}
            gameCode={code!}
          />
        )}

        {/* Question Flow */}
        {!isEliminated && isMyTurn && selectedTheme && currentQuestion && !answerResult && (
          <div className="bg-surface rounded-lg p-6 mb-6">
            <div className="mb-4">
              <h2 className="text-2xl font-display font-semibold text-text mb-2">
                Question {currentQuestion.question_number} (difficulté : {currentQuestion.difficulty}/10)
              </h2>
              <p className="text-text-muted mb-2">
                Thème {roundNumber}/2 : {selectedTheme.name}
              </p>
              <div className="bg-surface-raised rounded p-4 mb-4">
                <p className="text-text text-lg">{currentQuestion.question.text}</p>
              </div>
            </div>

            {/* Timer Progress Bar */}
            {timeRemaining !== null && (
              <div className="mb-4">
                <div className="flex justify-between items-center mb-2">
                  <span className={`text-sm font-bold ${timeRemaining <= 5 ? 'text-danger animate-timer-pulse' : 'text-text-muted'}`}>
                    ⏱ {timeRemaining}s restantes
                  </span>
                  <span className="text-sm text-text-muted">
                    difficulté {currentQuestion.difficulty}/10
                  </span>
                </div>
                <div className="h-2 bg-border rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-1000 ease-linear ${
                      timeRemaining <= 5 ? 'bg-danger' : timeRemaining <= 10 ? 'bg-brand-600' : 'bg-brand'
                    }`}
                    style={{ width: `${(timeRemaining / currentQuestion.time_limit) * 100}%` }}
                  />
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {currentQuestion.options.map((option, index) => (
                <button
                  key={index}
                  className="bg-brand-600 hover:bg-brand-hover text-white p-4 rounded-lg text-center transition-transform hover:scale-105"
                  onClick={() => handleAnswerSubmit(option)}
                >
                  {option}
                </button>
              ))}
            </div>

            <div className="mt-4 text-text-muted">
              <p>Score actuel : {playerStats?.score}</p>
              <p>Questions répondues (thème {roundNumber}/2) : {playerStats?.current_question_index}/10</p>
            </div>
          </div>
        )}

        {/* Answer Result */}
        {answerResult && (
          <div className="bg-surface rounded-lg p-6 mb-6 animate-fade-in">
            <div className={`p-4 rounded-lg mb-4 transition-all duration-300 ${
              answerResult.is_correct
                ? 'bg-success/20 animate-success-pulse'
                : 'bg-danger/20 animate-error-shake'
            }`}>
              <h3 className="text-xl font-bold text-text">
                {answerResult.is_correct ? '✅ Bonne réponse !' : '❌ Mauvaise réponse'}
              </h3>
              <p className="text-text">Points gagnés : {answerResult.points_awarded}</p>
              <p className="text-text mt-2">Réponse correcte : {answerResult.correct_answer}</p>
            </div>

            <div className="bg-surface-raised rounded p-4 mb-4">
              <p className="text-text">Nouveau score : {answerResult.player_score}</p>
              <p className="text-text-muted">
                Questions répondues (thème {roundNumber}/2) : {playerStats?.current_question_index}/10
              </p>
            </div>

            <div className="flex justify-center">
              <button
                className={answerResult.next_question_available ? 'btn-primary' : 'btn-success'}
                onClick={handleNextQuestion}
              >
                {answerResult.next_question_available
                  ? 'Question suivante'
                  : answerResult.qualification_status === 'playing'
                    ? 'Thème suivant →'
                    : 'Terminer'}
              </button>
            </div>
          </div>
        )}

        {/* Waiting for Leaderboard */}
        {isWaitingForLeaderboard && (
          <div className="bg-surface rounded-lg p-8 text-center">
            <div className="animate-spin h-8 w-8 border-4 border-text border-t-transparent rounded-full mx-auto mb-4"></div>
            <p className="text-text mb-2">En attente que tous les joueurs terminent...</p>
            <p className="text-text-muted">
              {tournamentProgress?.players_remaining}/{tournamentProgress?.players_total} joueurs restants
            </p>
          </div>
        )}

        {/* Intermediate Leaderboard */}
        {leaderboard && tournamentProgress?.phase === '8_qualified' && (
          <IntermediateLeaderboardComponent
            leaderboard={leaderboard}
            tournamentProgress={tournamentProgress}
            onAdvance={handleAdvancePhase}
            // BUG-206 : le bouton était affiché à tous les joueurs mais
            // l'endpoint /round2/{code}/advance est host-only ; sans token
            // (stocké uniquement sur le navigateur qui a créé la partie), le
            // clic échouait silencieusement avec un 403. On ne montre le
            // bouton qu'au détenteur du token.
            canAdvance={!!getHostToken(code!)}
            playerNames={playerNamesById}
          />
        )}

        {/* Finalists Phase — AD-8 : le statut par joueur vient du serveur
            (tournamentProgress.top_players), pas seulement de la phase
            globale. Sans ce garde, un joueur éliminé verrait aussi cet écran
            dès que la phase globale passe à "4_finalists" et pourrait
            naviguer vers la grille mémoire (AC #3). */}
        {tournamentProgress?.phase === '4_finalists' && currentPlayer && (() => {
          const myStanding = tournamentProgress.top_players.find(
            (p) => p.player_id === currentPlayer.id
          )
          const isFinalist = myStanding?.status === 'finalist'

          if (isFinalist) {
            return (
              <div className="bg-surface rounded-lg p-8 text-center">
                <h2 className="text-3xl font-display font-semibold text-text mb-4">🎉 Vous êtes finaliste !</h2>
                <p className="text-text-muted mb-6">
                  Félicitations ! Vous êtes qualifié pour la Manche 3 (Grille Mémoire).
                </p>
                <button
                  className="btn-success"
                  onClick={() => navigate(`/game/${code}/memory-grid`)}
                >
                  Continuer vers la Manche 3 (Grille Mémoire)
                </button>
              </div>
            )
          }

          return (
            <div className="bg-surface rounded-lg p-8 text-center">
              <h2 className="text-3xl font-display font-semibold text-text mb-4">Round 2 terminé</h2>
              <p className="text-text-muted">
                Les 4 finalistes ont été désignés pour la Manche 3. Votre parcours dans ce
                tournoi s'arrête ici — merci d'avoir joué !
              </p>
            </div>
          )
        })()}
      </div>
    </div>
  )
}

export default Round2
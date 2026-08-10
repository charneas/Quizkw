import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getGame, getRandomQuestion, spinWheel, advanceRound2Phase, getCurrentQuestion, setCurrentQuestion as setCurrentQuestionApi, getAnswersStatus, getRandomPingPongTheme, startPingPongDuel, getPingPongDuelState, getPingPongDuelResults, getHostToken, cancelPingPongDuel } from '../services/api'
import type { GameSession, QuestionResponse, WheelSpinResponse, Team } from '../types'
import Scoreboard from '../components/Scoreboard'
import TeamComposition from '../components/TeamComposition'
import WheelModal from '../components/WheelModal'
import WaitingForTeams from '../components/WaitingForTeams'
import PingPongQuestion from '../components/PingPongQuestion'
import PingPongResults from '../components/PingPongResults'
import PingPongTeamSelector from '../components/PingPongTeamSelector'

function HostGame() {
  const { code } = useParams<{ code: string }>()
  const navigate = useNavigate()

  const [game, setGame] = useState<GameSession | null>(null)
  const [currentQuestion, setCurrentQuestion] = useState<QuestionResponse | null>(null)
  const [answerResult, setAnswerResult] = useState<any>(null)
  const [wheelResult, setWheelResult] = useState<WheelSpinResponse | null>(null)
  const [currentTeamIndex, setCurrentTeamIndex] = useState(0)
  const [turnCount, setTurnCount] = useState(0)
  const [showWheel, setShowWheel] = useState(false)
  const [wheelTeamQueue, setWheelTeamQueue] = useState<number[]>([])
  const [wheelTeamIdx, setWheelTeamIdx] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [waitingForTeams, setWaitingForTeams] = useState(false)
  const [answersStatus, setAnswersStatus] = useState<any>(null)
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Ping-Pong Duel states
  const [showPingPong, setShowPingPong] = useState(false)
  const [pingPongTheme, setPingPongTheme] = useState<any>(null)
  const [pingPongDuel, setPingPongDuel] = useState<any>(null)
  const [, setPingPongResult] = useState<any>(null)
  const [showPingPongResults, setShowPingPongResults] = useState(false)
  const [pingPongResults, setPingPongResults] = useState<any>(null)
  const [showTeamSelector, setShowTeamSelector] = useState(false)
  const [cancellingDuel, setCancellingDuel] = useState(false)

  useEffect(() => {
    if (code) loadGame()
  }, [code])

  useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) clearInterval(pollingIntervalRef.current)
    }
  }, [])

  // BUG-114 : rafraîchit la composition des équipes (join tardif) sans
  // attendre une action de jeu qui recharge déjà `game` par ailleurs.
  useEffect(() => {
    if (!code) return
    const interval = setInterval(async () => {
      try {
        const freshGame = await getGame(code)
        setGame(freshGame)
      } catch {
        // Ignoré : un prochain tick réessaiera.
      }
    }, 5000)
    return () => clearInterval(interval)
  }, [code])

  const loadGame = async () => {
    if (!getHostToken(code!)) {
      setError("Cet écran est réservé à l'hôte qui a créé la partie.")
      setLoading(false)
      return
    }
    try {
      const gameData = await getGame(code!)
      setGame(gameData)
      await loadQuestion()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur')
    } finally {
      setLoading(false)
    }
  }

  // Charge une NOUVELLE question aléatoire et la définit comme question courante
  // À utiliser quand l'hôte veut forcer le tour suivant (indépendamment du statut des réponses)
  const forceNewQuestion = async () => {
    try {
      // Cacher WaitingForTeams IMMÉDIATEMENT pour éviter la boucle :
      // si waitingForTeams=true avec answeredCount===totalTeams, WaitingForTeams rappellerait
      // handleNextTurn en boucle pendant que forceNewQuestion est en cours
      setWaitingForTeams(false)
      setAnswersStatus(null)
      setAnswerResult(null)   // Réactiver le bouton "Valider" pour la nouvelle question
      const question = await getRandomQuestion()
      await setCurrentQuestionApi(code!, question.question.id)
      setCurrentQuestion(question)
      setWaitingForTeams(true)
      startPolling()
      const status = await getAnswersStatus(code!)
      setAnswersStatus(status)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Aucune question disponible')
      throw err
    }
  }

  // Charge la question courante si elle existe, sinon en force une nouvelle
  // À utiliser uniquement au chargement initial
  const loadQuestion = async () => {
    try {
      const status = await getAnswersStatus(code!)
      setAnswersStatus(status)

      if (status.all_answered || !status.question_id) {
        await forceNewQuestion()
      } else {
        const question = await getCurrentQuestion(code!)
        setCurrentQuestion(question)
        setWaitingForTeams(true)
        startPolling()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Aucune question disponible')
    }
  }

  const startPolling = () => {
    if (pollingIntervalRef.current) clearInterval(pollingIntervalRef.current)
    pollingIntervalRef.current = setInterval(async () => {
      try {
        const status = await getAnswersStatus(code!)
        setAnswersStatus(status)
        if (status.all_answered) {
          clearInterval(pollingIntervalRef.current!)
          pollingIntervalRef.current = null
        }
      } catch (err) {
        console.error('Erreur polling:', err)
      }
    }, 2000)
  }

  const handleAllAnswered = async () => {
    // Démonter WaitingForTeams IMMÉDIATEMENT pour éviter la boucle de déclenchement
    setWaitingForTeams(false)
    setAnswersStatus(null)
    // Valider les réponses de la question courante
    // Ne PAS auto-avancer : l'hôte clique "Tour suivant" quand il veut
    // (évite que le host valide la mauvaise question si il clique "Valider" après l'auto-avance)
    await handleValidateAnswers()
  }

  const handleNextTurn = useCallback(async () => {
    if (!game) return

    const newTurnCount = turnCount + 1
    setTurnCount(newTurnCount)

    // Roue tous les 5 tours — chaque équipe tourne une fois
    if (newTurnCount % 5 === 0) {
      const teamIndices = game.teams.map((_, i) => i)
      setWheelTeamQueue(teamIndices)
      setWheelTeamIdx(0)
      setWheelResult(null)
      setShowWheel(true)
      return
    }

    // BUG-105 (revue de code J.003) : si forceNewQuestion échoue (ex. un duel
    // ping-pong actif bloque le lancement, story J.003), ne pas avancer
    // l'index d'équipe — sinon le tour serait désynchronisé de la question
    // réellement affichée.
    try {
      await forceNewQuestion()
      setCurrentTeamIndex((prev) => (prev + 1) % game.teams.length)
    } catch {
      // forceNewQuestion a déjà affiché l'erreur (setError).
    }
  }, [game, turnCount])

  const handleSpinWheel = async () => {
    if (!game) return
    // Spin pour l'équipe courante dans la queue de la roue
    const teamIdx = wheelTeamQueue.length > 0 ? wheelTeamQueue[wheelTeamIdx] : currentTeamIndex
    const team = game.teams[teamIdx]

    try {
      const result = await spinWheel(team.id)
      setWheelResult(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur roue')
    }
  }

  const handleCloseWheel = async () => {
    if (!game) return

    // Si on est dans un cycle per-team et qu'il reste des équipes
    if (wheelTeamQueue.length > 0 && wheelTeamIdx < wheelTeamQueue.length - 1) {
      // Passer à l'équipe suivante dans la queue
      setWheelTeamIdx(prev => prev + 1)
      setWheelResult(null)
      return
    }

    // Toutes les équipes ont tourné (ou pas de queue) — fermer la roue
    setShowWheel(false)
    setWheelTeamQueue([])
    setWheelTeamIdx(0)
    const result = wheelResult
    setWheelResult(null)

    if (result?.effect_type === 'ping_pong') {
      setShowTeamSelector(true)
    } else {
      setCurrentTeamIndex((prev) => (prev + 1) % game.teams.length)
      await loadQuestion()
    }
  }

  // === Ping-Pong Duel (Host) ===

  const handleTeamSelect = async (team2: Team) => {
    if (!game) return
    const team1 = game.teams[currentTeamIndex]
    setShowTeamSelector(false)

    try {
      const theme = await getRandomPingPongTheme()
      const duel = await startPingPongDuel({
        game_session_id: game.id,
        theme_id: theme.id,
        team1_id: team1.id,
        team2_id: team2.id,
      })

      setPingPongDuel(duel)
      setPingPongTheme(theme)
      setShowPingPong(true)
      startDuelPolling(duel.duel_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur ping-pong')
    }
  }

  const handleCancelTeamSelect = async () => {
    setShowTeamSelector(false)
    if (game) {
      setCurrentTeamIndex((prev) => (prev + 1) % game.teams.length)
      await loadQuestion()
    }
  }

  const handlePingPongSubmit = async (answer: string) => {
    if (!game || !pingPongDuel) return

    try {
      const result = await fetch('/api/ping-pong/duel/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          duel_id: pingPongDuel.duel_id,
          team_id: pingPongDuel.current_turn_team_id,
          answer: answer,
        }),
      }).then(r => r.json())

      setPingPongResult(result)

      if (!result.duel_continues) {
        const results = await getPingPongDuelResults(pingPongDuel.duel_id)
        setPingPongResults(results)
        setShowPingPong(false)
        setShowPingPongResults(true)
        const freshGame = await getGame(code!)
        setGame(freshGame)
      } else {
        const state = await getPingPongDuelState(pingPongDuel.duel_id)
        setPingPongDuel(state)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur ping-pong')
    }
  }

  const handlePingPongPass = async () => {
    await handlePingPongSubmit('__PASS__')
  }

  // Polling pendant le duel (les équipes répondent, l'hôte observe)
  const startDuelPolling = (duelId: number) => {
    if (pollingIntervalRef.current) clearInterval(pollingIntervalRef.current)
    pollingIntervalRef.current = setInterval(async () => {
      try {
        const state = await getPingPongDuelState(duelId)
        setPingPongDuel(state)
        if (state.is_completed) {
          clearInterval(pollingIntervalRef.current!)
          pollingIntervalRef.current = null
          if (state.is_cancelled) {
            // BUG-101g : un duel annulé n'a pas de vainqueur, pas d'écran de résultats.
            await handlePingPongContinue()
            return
          }
          const results = await getPingPongDuelResults(duelId)
          setPingPongResults(results)
          setShowPingPong(false)
          setShowPingPongResults(true)
          const freshGame = await getGame(code!)
          setGame(freshGame)
        }
      } catch (err) {
        console.error('Erreur polling duel:', err)
      }
    }, 2000)
  }

  const handleCancelDuel = async () => {
    if (!pingPongDuel || cancellingDuel) return
    const duelId = pingPongDuel.duel_id
    setCancellingDuel(true)
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
    try {
      await cancelPingPongDuel(code!, duelId)
      await handlePingPongContinue()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossible d'annuler ce duel")
      // L'annulation a échoué (ex. le duel vient de se terminer normalement
      // entre-temps) : reprendre le polling au lieu de laisser l'écran figé,
      // il détectera l'état réel (terminé/annulé) au prochain tick.
      startDuelPolling(duelId)
    } finally {
      setCancellingDuel(false)
    }
  }

  const handlePingPongContinue = async () => {
    setShowPingPongResults(false)
    setPingPongTheme(null)
    setPingPongDuel(null)
    setPingPongResult(null)
    setPingPongResults(null)

    if (game) {
      setCurrentTeamIndex((prev) => (prev + 1) % game.teams.length)
      await loadQuestion()
    }
  }

  // === Validate answers (host validates all team answers) ===
  const handleValidateAnswers = async () => {
    if (!game) return
    try {
      const token = getHostToken(code!)
      const result = await fetch(`/api/games/${code}/validate-answers`, {
        method: 'POST',
        headers: token ? { 'X-Host-Token': token } : {},
      }).then(r => r.json())
      setAnswerResult(result)
      const freshGame = await getGame(code!)
      setGame(freshGame)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur validation')
    }
  }

  // === Advance to next phase ===
  const handleAdvanceToPhase2 = async () => {
    try {
      await advanceRound2Phase(code!)
      navigate(`/game/${code}/round2`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur transition')
    }
  }

  const handleAdvanceToPhase3 = async () => {
    navigate(`/game/${code}/memory-grid`)
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-2xl text-text-muted animate-pulse">Chargement du jeu...</div>
      </div>
    )
  }

  if (!game) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="card text-center">
          <h2 className="text-2xl text-danger mb-4">Erreur</h2>
          <p className="text-text-muted">{error}</p>
          <button onClick={() => navigate('/')} className="btn-primary mt-4">Retour</button>
        </div>
      </div>
    )
  }

  const currentTeam = game.teams[currentTeamIndex]
  // BUG-108 : l'hôte doit voir la question pendant que les équipes répondent,
  // pas seulement une fois qu'elles ont toutes fini — waitingForTeams ne doit
  // pas masquer la question, les deux blocs sont complémentaires.
  const showQuestion = !!currentQuestion
  // BUG-109 (#11) : en Manche 1, toutes les équipes répondent simultanément
  // (pas de tour à tour) — currentTeamIndex ne sert qu'à désigner une équipe
  // par défaut pour la roue, ce n'est PAS l'équipe "dont c'est le tour de
  // répondre". Le statut par équipe (répondu / en attente), déjà exposé par
  // answers-status, remplace l'ancien affichage "C'est au tour de X" qui
  // laissait croire à un ordre de passage inexistant.
  const answeredTeamIds: number[] = answersStatus?.answered_teams ?? []
  const teamsAnswerStatus = game.teams.map((t) => ({
    ...t,
    has_answered: answeredTeamIds.includes(t.id),
  }))

  return (
    <div className="min-h-screen p-4">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">Manche 1 — Hôte</h1>
            <p className="text-text-muted text-sm">
              Tour {turnCount + 1} • Code: <span className="font-display font-semibold text-brand">{game.code}</span>
            </p>
          </div>
          <div className="flex gap-2">
            <button onClick={handleAdvanceToPhase2} className="btn-secondary text-sm">
              Manche 2 →
            </button>
            <button onClick={handleAdvanceToPhase3} className="btn-primary text-sm">
              🧠 Manche 3 →
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Scoreboard */}
          <div className="lg:col-span-1 space-y-6">
            <Scoreboard teams={game.teams} currentTeamIndex={currentTeamIndex} />
            <TeamComposition teams={game.teams} />
          </div>

          {/* Zone de contrôle */}
          <div className="lg:col-span-2 space-y-4">
            {/* Question affichée pour référence (les équipes répondent via leur écran) */}
            {showQuestion && currentQuestion && (
              <div className="card">
                <h3 className="text-lg font-semibold mb-2">{currentQuestion.question.text}</h3>
                <p className="text-xs text-text-muted mb-3">
                  {currentQuestion.question.category} • {currentQuestion.question.points} pts
                </p>
                <p className="text-sm text-text-muted italic">
                  Les équipes répondent sur leur propre écran...
                </p>
              </div>
            )}

            {/* Progression par équipe (#11) : qui a répondu, qui est attendu —
                toutes les équipes répondent en parallèle, il n'y a pas d'ordre
                de passage à afficher. */}
            {showQuestion && (
              <div className="card">
                <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wide mb-3">
                  Progression des équipes
                </h3>
                <div className="space-y-2">
                  {teamsAnswerStatus.map((team) => (
                    <div key={team.id} className="flex items-center justify-between">
                      <span className="text-sm">{team.name}</span>
                      <span className={team.has_answered ? 'text-success' : 'text-text-muted'}>
                        {team.has_answered ? '✓ Répondu' : '⏳ En attente'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* État des réponses */}
            {answersStatus && waitingForTeams && answersStatus.answered_teams && (
              <WaitingForTeams
                currentTeam={currentTeam}
                totalTeams={answersStatus.total_teams ?? 0}
                answeredCount={answersStatus.answered_teams?.length ?? 0}
                onAllAnswered={handleAllAnswered}
              />
            )}

            {/* Résultat de la validation */}
            {answerResult && answerResult.teams_updated && (
              <div className="card border-success">
                <h3 className="text-lg font-bold text-success mb-3">✅ Réponses validées !</h3>
                <p className="text-sm text-text-muted mb-2">
                  Réponse correcte : <span className="text-text font-semibold">{answerResult.correct_answer}</span>
                </p>
                <div className="space-y-1 mb-4">
                {answerResult.teams_updated.map((t: any, idx: number) => (
                    <div key={`${t.team_id}_${idx}`} className="flex justify-between text-sm">
                      <span>{t.team_name}</span>
                      <span className={t.is_correct ? 'text-success' : 'text-danger'}>
                        {t.is_correct ? `+${t.points_earned} pts` : '✗'}
                      </span>
                    </div>
                  ))}
                </div>
                <button
                  onClick={handleNextTurn}
                  disabled={showPingPong || showTeamSelector || showPingPongResults}
                  className="btn-primary disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Tour suivant →
                </button>
              </div>
            )}

            {/* Contrôles rapides */}
            <div className="flex gap-2">
              <button
                onClick={handleValidateAnswers}
                disabled={!!answerResult}
                className="btn-success flex-1 text-sm disabled:opacity-40 disabled:cursor-not-allowed"
                title={answerResult ? 'Déjà validé — cliquez Tour suivant pour continuer' : ''}
              >
                ✅ Valider les réponses
              </button>
              <button
                onClick={handleNextTurn}
                disabled={showPingPong || showTeamSelector || showPingPongResults}
                className="btn-secondary flex-1 text-sm disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Tour suivant →
              </button>
              <button
                onClick={forceNewQuestion}
                disabled={showPingPong || showTeamSelector || showPingPongResults}
                className="btn-secondary flex-1 text-sm disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Nouvelle question
              </button>
            </div>
          </div>
        </div>

        {/* Modal Roue — tourne une fois par équipe */}
        {showWheel && (
          <WheelModal
            onSpin={handleSpinWheel}
            result={wheelResult}
            onClose={handleCloseWheel}
            teamName={wheelTeamQueue.length > 0 ? game.teams[wheelTeamQueue[wheelTeamIdx]]?.name : currentTeam.name}
            teamProgress={wheelTeamQueue.length > 0 ? `${wheelTeamIdx + 1}/${wheelTeamQueue.length}` : undefined}
            isLastTeam={wheelTeamQueue.length === 0 || wheelTeamIdx >= wheelTeamQueue.length - 1}
          />
        )}

        {/* Team Selector (quand la roue donne ping_pong) */}
        {showTeamSelector && (
          <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
            <div className="max-w-md w-full">
              <PingPongTeamSelector
                currentTeam={currentTeam}
                availableTeams={game.teams.filter(t => t.id !== currentTeam.id)}
                onSelect={handleTeamSelect}
                onCancel={handleCancelTeamSelect}
              />
            </div>
          </div>
        )}

        {/* Duel Ping-Pong */}
        {showPingPong && pingPongTheme && pingPongDuel && (
          <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
            <div className="max-w-2xl w-full max-h-[90vh] overflow-y-auto">
              <PingPongQuestion
                theme={pingPongDuel.theme || pingPongTheme}
                team1={findTeamById(game.teams, pingPongDuel.team1.id)}
                team2={findTeamById(game.teams, pingPongDuel.team2.id)}
                currentTurnTeamId={pingPongDuel.current_turn_team_id}
                answersUsed={pingPongDuel.answers_used || []}
                turnNumber={pingPongDuel.turn_number || 1}
                isCurrentTeam={false}
                onSubmit={handlePingPongSubmit}
                onPass={handlePingPongPass}
                disabled={pingPongDuel.is_completed}
              />
              <button
                onClick={handleCancelDuel}
                disabled={cancellingDuel}
                className="btn-secondary w-full mt-3 disabled:opacity-50"
              >
                {cancellingDuel ? 'Annulation...' : 'Annuler ce duel (équipe bloquée)'}
              </button>
            </div>
          </div>
        )}

        {/* Résultats du duel */}
        {showPingPongResults && pingPongResults && (
          <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
            <div className="max-w-2xl w-full">
              <PingPongResults
                theme={pingPongResults.theme}
                team1={{
                  id: pingPongResults.team1.id,
                  name: pingPongResults.team1.name,
                  turns: pingPongResults.team1.turns,
                  correctAnswers: pingPongResults.team1.correct_answers,
                }}
                team2={{
                  id: pingPongResults.team2.id,
                  name: pingPongResults.team2.name,
                  turns: pingPongResults.team2.turns,
                  correctAnswers: pingPongResults.team2.correct_answers,
                }}
                winnerTeamId={pingPongResults.winner_team_id}
                winnerTeamName={pingPongResults.winner_team_name}
                totalTurns={pingPongResults.total_turns}
                answersUsed={pingPongResults.answers_used}
                onContinue={handlePingPongContinue}
              />
            </div>
          </div>
        )}

        {/* Erreur */}
        {error && (
          <div className="fixed bottom-4 right-4 z-[60] bg-danger/90 text-text px-4 py-2 rounded-lg text-sm">
            {error}
            <button onClick={() => setError('')} className="ml-2 hover:opacity-70">✕</button>
          </div>
        )}
      </div>
    </div>
  )
}

function findTeamById(teams: Team[], teamId: number): Team {
  return teams.find(t => t.id === teamId)!
}

export default HostGame
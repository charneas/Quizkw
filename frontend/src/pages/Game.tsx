import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getGame, getRandomQuestion, submitAnswer, useToken, spinWheel, advanceRound2Phase, getCurrentQuestion, setCurrentQuestion as setCurrentQuestionApi, getAnswersStatus, getRandomPingPongTheme, startPingPongDuel, submitPingPongDuelAnswer, getPingPongDuelState, getPingPongDuelResults, getTeamTokens } from '../services/api'
import type { GameSession, QuestionResponse, AnswerResponse, WheelSpinResponse, TokenType, Team } from '../types'
import Scoreboard from '../components/Scoreboard'
import QuestionCard from '../components/QuestionCard'
import TokenPanel from '../components/TokenPanel'
import WheelModal from '../components/WheelModal'
import WaitingForTeams from '../components/WaitingForTeams'
import PingPongQuestion from '../components/PingPongQuestion'
import PingPongResults from '../components/PingPongResults'
import PingPongTeamSelector from '../components/PingPongTeamSelector'
import DevHelper from '../components/DevHelper'

function Game() {
  const { code } = useParams<{ code: string }>()
  const navigate = useNavigate()
  
  const [game, setGame] = useState<GameSession | null>(null)
  const [currentQuestion, setCurrentQuestion] = useState<QuestionResponse | null>(null)
  const [answerResult, setAnswerResult] = useState<AnswerResponse | null>(null)
  const [wheelResult, setWheelResult] = useState<WheelSpinResponse | null>(null)
  const [isBonusActive, setIsBonusActive] = useState(false)
  const [currentTeamIndex, setCurrentTeamIndex] = useState(0)
  const [turnCount, setTurnCount] = useState(0)
  const [showWheel, setShowWheel] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [waitingForTeams, setWaitingForTeams] = useState(false)
  const [answersStatus, setAnswersStatus] = useState<{
    question_id: number | null
    total_teams: number
    answered_teams: number[]
    remaining_teams: number[]
    all_answered: boolean
  } | null>(null)
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [activeTeamTokens, setActiveTeamTokens] = useState<any[]>([])
  
  // Ping-Pong Duel states
  const [showPingPong, setShowPingPong] = useState(false)
  const [pingPongTheme, setPingPongTheme] = useState<any>(null)
  const [pingPongDuel, setPingPongDuel] = useState<any>(null)
  const [, setPingPongResult] = useState<any>(null)
  const [showPingPongResults, setShowPingPongResults] = useState(false)
  const [pingPongResults, setPingPongResults] = useState<any>(null)
  const [showTeamSelector, setShowTeamSelector] = useState(false)
  const [confirmingAdvance, setConfirmingAdvance] = useState(false)
  const [penaltyFeedback, setPenaltyFeedback] = useState('')
  const [feedbackMessage, setFeedbackMessage] = useState<{ type: 'swap' | 'penalty' | 'bonus', text: string } | null>(null)

  useEffect(() => {
    if (code) loadGame()
  }, [code])

  useEffect(() => {
    if (game && game.teams && game.teams[currentTeamIndex]) {
      loadTeamTokens(game.teams[currentTeamIndex].id)
    }
  }, [currentTeamIndex, game])

  useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
      }
    }
  }, [])

  const loadGame = async () => {
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

  const loadTeamTokens = async (teamId: number) => {
    try {
      const tokens = await getTeamTokens(teamId)
      setActiveTeamTokens(Array.isArray(tokens) ? tokens : [])
    } catch (err) {
      console.error("Erreur lors de la récupération des jetons:", err)
      setActiveTeamTokens([])
    }
  }

  const loadQuestion = async () => {
    // 🔄 Réinitialise les bonus pour la nouvelle question
    setIsBonusActive(false)

    try {
      const status = await getAnswersStatus(code!)
      setAnswersStatus(status)
      
      if (status.all_answered || !status.question_id) {
        const question = await getRandomQuestion()
        await setCurrentQuestionApi(code!, question.question.id)
        setCurrentQuestion(question)
        setWaitingForTeams(false)
        const newStatus = await getAnswersStatus(code!)
        setAnswersStatus(newStatus)
      } else {
        const question = await getCurrentQuestion(code!)
        setCurrentQuestion(question)
        
        if (game && status.answered_teams.includes(game.teams[currentTeamIndex].id)) {
          setWaitingForTeams(true)
          startPolling()
        } else {
          setWaitingForTeams(false)
        }
      }
      setAnswerResult(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Aucune question disponible')
    }
  }

  const startPolling = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
    }
    pollingIntervalRef.current = setInterval(async () => {
      try {
        const status = await getAnswersStatus(code!)
        setAnswersStatus(status)
        
        if (status.all_answered) {
          stopPolling()
        }
      } catch (err) {
        console.error('Erreur polling:', err)
      }
    }, 2000)
  }

  const stopPolling = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
  }

  const handleAllAnswered = async () => {
    stopPolling()
    setWaitingForTeams(false)
    await handleNextTurn()
  }

  const handleAnswer = async (answer: string) => {
    if (!currentQuestion || !game) return
    const currentTeam = game.teams[currentTeamIndex]
    
    try {
      const result = await submitAnswer({
        question_id: currentQuestion.question.id,
        team_id: currentTeam.id,
        player_answer: answer,
      })

      // ⭐ Si le BONUS est actif, on double les points gagnés !
      const finalPoints = isBonusActive ? result.points_earned * 2 : result.points_earned
      const updatedResult = { ...result, points_earned: finalPoints }

      setAnswerResult(updatedResult)
      
      setGame(prev => {
        if (!prev) return prev
        const updatedTeams = [...prev.teams]
        
        // Calcul du nouveau score avec le bonus éventuel
        const pointDifference = finalPoints - result.points_earned
        const newScore = result.team_score + pointDifference

        updatedTeams[currentTeamIndex] = {
          ...updatedTeams[currentTeamIndex],
          score: newScore,
        }
        return { ...prev, teams: updatedTeams }
      })

      const status = await getAnswersStatus(code!)
      setAnswersStatus(status)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur')
    }
  }

  // === Turn & Wheel ===

  const handleNextTurn = useCallback(async () => {
    if (!game) return
    
    const newTurnCount = turnCount + 1
    setTurnCount(newTurnCount)
    
    // Roue tous les `game.wheel_frequency` tours
    if (newTurnCount % game.wheel_frequency === 0) {
      setShowWheel(true)
      return
    }
    
    setCurrentTeamIndex((prev) => (prev + 1) % game.teams.length)
    await loadQuestion()
  }, [game, turnCount])

  const handleSpinWheel = async () => {
    if (!game) return
    const currentTeam = game.teams[currentTeamIndex]
    
    try {
      const result = await spinWheel(currentTeam.id)
      setWheelResult(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur roue')
    }
  }

  const handleCloseWheel = async () => {
    setShowWheel(false)
    const result = wheelResult
    setWheelResult(null)

    if (!game) return

    if (result?.effect_type === 'ping_pong') {
      setShowTeamSelector(true)
    } else {
      setCurrentTeamIndex((prev) => (prev + 1) % game.teams.length)
      await loadQuestion()
    }
  }

  // === Ping-Pong Duel ===

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
      const result = await submitPingPongDuelAnswer({
        duel_id: pingPongDuel.duel_id,
        team_id: pingPongDuel.current_turn_team_id,
        answer: answer,
      })

      setPingPongResult(result)

      if (!result.duel_continues) {
        const results = await getPingPongDuelResults(pingPongDuel.duel_id)
        setPingPongResults(results)
        setShowPingPong(false)
        setShowPingPongResults(true)

        const freshGame = await getGame(code!)
        setGame(freshGame)
      } else {
        // Rafraîchir l'état du duel (tour suivant)
        const state = await getPingPongDuelState(pingPongDuel.duel_id)
        setPingPongDuel(state)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur ping-pong')
    }
  }

  const handlePingPongPass = async () => {
    if (!game || !pingPongDuel) return

    try {
      const result = await submitPingPongDuelAnswer({
        duel_id: pingPongDuel.duel_id,
        team_id: pingPongDuel.current_turn_team_id,
        answer: '__PASS__',
      })

      setPingPongResult(result)

      if (!result.duel_continues) {
        const results = await getPingPongDuelResults(pingPongDuel.duel_id)
        setPingPongResults(results)
        setShowPingPong(false)
        setShowPingPongResults(true)

        const freshGame = await getGame(code!)
        setGame(freshGame)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur ping-pong')
    }
  }

  const handlePingPongContinue = async () => {
    setShowPingPongResults(false)
    setPingPongTheme(null)
    setPingPongResult(null)
    setPingPongResults(null)
    setPingPongDuel(null)
    
    if (game) {
      setCurrentTeamIndex((prev) => (prev + 1) % game.teams.length)
      await loadQuestion()
    }
  }

  // === Jetons ===

  const handleUseToken = async (tokenType: TokenType, targetTeamId?: number) => {
    if (!game) return
    const currentTeam = game.teams[currentTeamIndex]
    const normalizedType = tokenType.toUpperCase()

    try {
      console.log(`🎮 Utilisation du jeton : ${normalizedType}`)

      // 1. Consomme le jeton en BDD
      const tokenResult = await useToken({ team_id: currentTeam.id, token_type: normalizedType, target_team_id: targetTeamId })

      // 2. Déclenche l'effet du jeton + notification visuelle
      if (normalizedType === 'SWAP') {
        await loadQuestion()
        setFeedbackMessage({
          type: 'swap',
          text: `🔀 SWAP ! La question a été changée par ${currentTeam.name} !`
        })
      } else if (normalizedType === 'PENALTY' || normalizedType === 'PÉNALITÉ') {
        // ⚡ Retire des points aux équipes adverses (appliqué côté backend)
        await loadGame()

        const penalizedTeams: { team_id: number; new_score: number }[] = tokenResult?.penalized_teams || []
        const names = penalizedTeams.length > 0
          ? penalizedTeams.map((p) => game.teams.find((t) => t.id === p.team_id)?.name || `Équipe #${p.team_id}`).join(', ')
          : 'l\'équipe adverse'

        setFeedbackMessage({
          type: 'penalty',
          text: `⚡ Pénalité appliquée : -2 points pour ${names} !`
        })
      } else if (normalizedType === 'BONUS') {
        // ⭐ Active le multiplicateur x2
        setIsBonusActive(true)
        setFeedbackMessage({
          type: 'bonus',
          text: `⭐ BONUS ACTIVÉ ! La prochaine bonne réponse de ${currentTeam.name} rapportera x2 points !`
        })
      }

      // Masque le message après 5 secondes
      setTimeout(() => setFeedbackMessage(null), 5000)
      
      // 3. Rafraîchit les jetons
      await loadTeamTokens(currentTeam.id)

    } catch (err) {
      console.error(`Erreur jeton ${normalizedType} :`, err)
      await loadTeamTokens(currentTeam.id).catch(() => null)
    }
  }

  const handleAdvanceToPhase2 = async () => {
    setConfirmingAdvance(false)
    try {
      await advanceRound2Phase(code!)
      navigate(`/game/${code}/round2`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors de la transition vers la manche 2')
    }
  }

  // === Render ===

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

  const currentTeam = game?.teams?.[currentTeamIndex]

  return (
    <div className="min-h-screen p-4">
      {import.meta.env.DEV && <DevHelper code={code!} />}
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">Manche 1</h1>
            <p className="text-text-muted text-sm">Tour {turnCount + 1} • Code: {game.code}</p>
          </div>
          <button
            onClick={() => setConfirmingAdvance(true)}
            disabled={!answersStatus || !answersStatus.all_answered}
            className="btn-secondary text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            title={
              !answersStatus || !answersStatus.all_answered
                ? 'Toutes les équipes doivent avoir répondu à la question en cours'
                : undefined
            }
          >
            Passer en Manche 2 →
          </button>
        </div>

        {confirmingAdvance && (
          <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
            <div className="card max-w-sm w-full text-center">
              <div className="text-4xl mb-3">➡️</div>
              <h3 className="text-lg font-semibold text-text mb-2">Passer en Manche 2 ?</h3>
              <p className="text-sm text-text-muted mb-6">
                Cette action fait passer toutes les équipes à la Manche 2. Confirmez-vous ?
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => setConfirmingAdvance(false)}
                  className="btn-secondary flex-1 min-h-[44px]"
                >
                  Annuler
                </button>
                <button
                  onClick={handleAdvanceToPhase2}
                  className="btn-primary flex-1 min-h-[44px]"
                >
                  Confirmer
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1">
            <Scoreboard teams={game.teams} />
          </div>

          <div className="lg:col-span-2 space-y-4">
            {/* ⚡ BANNIÈRE DE FEEDBACK DES JETONS ⚡ */}
            {feedbackMessage && (
              <div className={`p-4 rounded-xl text-white font-bold text-center shadow-2xl transition-all border-2 ${
                feedbackMessage.type === 'swap' ? 'bg-blue-600 border-blue-400' :
                feedbackMessage.type === 'penalty' ? 'bg-red-600 border-red-400' : 'bg-amber-500 border-amber-300 text-slate-900'
              }`}>
                <div className="flex items-center justify-between">
                  <span className="flex-1 text-base">{feedbackMessage.text}</span>
                  <button 
                    onClick={() => setFeedbackMessage(null)} 
                    className="ml-2 font-bold px-2 py-1 hover:opacity-75 rounded"
                  >
                    ✕
                  </button>
                </div>
              </div>
            )}

            {currentTeam && (
              <div className="card text-center">
                <p className="text-sm text-slate-400">C'est au tour de</p>
                <p className="text-2xl font-bold text-game-accent">{currentTeam.name}</p>
              </div>
            )}

            {currentQuestion && !answerResult && !waitingForTeams && (
              <QuestionCard
                question={currentQuestion}
                onAnswer={handleAnswer}
                isBonusActive={isBonusActive}
              />
            )}

            {waitingForTeams && answersStatus && currentTeam && (
              <WaitingForTeams
                currentTeam={currentTeam}
                totalTeams={answersStatus.total_teams}
                answeredCount={answersStatus.answered_teams.length}
                onAllAnswered={handleAllAnswered}
              />
            )}

            {answerResult && (
              <div className={`card text-center ${answerResult.is_correct ? 'border-success' : 'border-danger'}`}>
                <div className="text-4xl mb-3">
                  {answerResult.is_correct ? '✅' : '❌'}
                </div>
                <h3 className={`text-xl font-bold ${answerResult.is_correct ? 'text-success' : 'text-danger'}`}>
                  {answerResult.is_correct ? 'Bonne réponse !' : 'Mauvaise réponse !'}
                </h3>
                {!answerResult.is_correct && (
                  <p className="text-text-muted mt-2">
                    Réponse correcte : <span className="text-text font-semibold">{answerResult.correct_answer}</span>
                  </p>
                )}
                <p className="text-text-muted mt-2">
                  Points gagnés : <span className="text-brand font-bold">+{answerResult.points_earned}</span>
                </p>
                <button onClick={handleNextTurn} className="btn-primary mt-4">
                  Tour suivant →
                </button>
              </div>
            )}

            <TokenPanel
              tokens={activeTeamTokens}
              otherTeams={game.teams
                .filter((t) => t.id !== game.teams[currentTeamIndex]?.id)
                .map((t) => ({ team_id: t.id, team_name: t.name }))}
              onUseToken={handleUseToken}
            />
          </div>
        </div>

        {error && (
          <div className="fixed bottom-4 right-4 z-[60] bg-danger/90 text-text px-4 py-2 rounded-lg text-sm">
            {error}
            <button onClick={() => setError('')} className="ml-2 hover:opacity-70">✕</button>
          </div>
        )}

        {penaltyFeedback && (
          <div className="fixed bottom-4 left-4 z-[60] bg-red-700/90 text-text px-4 py-2 rounded-lg text-sm">
            {penaltyFeedback}
            <button onClick={() => setPenaltyFeedback('')} className="ml-2 hover:opacity-70">✕</button>
          </div>
        )}

        {showWheel && (
          <WheelModal
            onSpin={handleSpinWheel}
            result={wheelResult}
            onClose={handleCloseWheel}
          />
        )}

        {/* Modal Team Selector (quand la roue donne ping_pong) */}
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

        {/* Modal Ping-Pong Duel */}
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
            </div>
          </div>
        )}

        {showPingPongResults && pingPongResults && currentTeam && (
          <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
            <div className="max-w-4xl w-full max-h-[90vh] overflow-y-auto">
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
      </div>
    </div>
  )
}

// Helper to find a Team by its ID
function findTeamById(teams: Team[], teamId: number): Team {
  return teams.find(t => t.id === teamId)!
}

export default Game
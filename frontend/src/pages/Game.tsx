import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getGame, getRandomQuestion, submitAnswer, useToken, spinWheel, advanceRound2Phase, getCurrentQuestion, setCurrentQuestion, getAnswersStatus, getTeamTokens, getRandomPingPongTheme, submitPingPongAnswer, getPingPongResults } from '../services/api'
import type { GameSession, QuestionResponse, AnswerResponse, WheelSpinResponse, TokenType } from '../types'
import Scoreboard from '../components/Scoreboard'
import QuestionCard from '../components/QuestionCard'
import TokenPanel from '../components/TokenPanel'
import WheelModal from '../components/WheelModal'
import WaitingForTeams from '../components/WaitingForTeams'
import PingPongQuestion from '../components/PingPongQuestion'
import PingPongResults from '../components/PingPongResults'
import DevHelper from '../components/DevHelper'

function Game() {
  const { code } = useParams<{ code: string }>()
  const navigate = useNavigate()
  
  const [game, setGame] = useState<GameSession | null>(null)
  const [currentQuestion, setCurrentQuestion] = useState<QuestionResponse | null>(null)
  const [answerResult, setAnswerResult] = useState<AnswerResponse | null>(null)
  const [wheelResult, setWheelResult] = useState<WheelSpinResponse | null>(null)
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
  const pollingIntervalRef = useRef<number | null>(null)
  
  // Ping-Pong states
  const [showPingPong, setShowPingPong] = useState(false)
  const [pingPongTheme, setPingPongTheme] = useState<any>(null)
  const [pingPongResult, setPingPongResult] = useState<any>(null)
  const [showPingPongResults, setShowPingPongResults] = useState(false)
  const [pingPongResults, setPingPongResults] = useState<any>(null)

  useEffect(() => {
    if (code) loadGame()
  }, [code])

  // Cleanup polling on unmount
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

  const loadQuestion = async () => {
    try {
      // Synchronisation: récupérer la question courante pour toutes les équipes
      const status = await getAnswersStatus(code!)
      setAnswersStatus(status)
      
      if (status.all_answered || !status.question_id) {
        // Si toutes les équipes ont déjà répondu ou pas de question courante, définir une nouvelle question
        const question = await getRandomQuestion()
        await setCurrentQuestion(code!, question.question.id)
        setCurrentQuestion(question)
        setWaitingForTeams(false)
        // Réinitialiser le statut pour la nouvelle question
        const newStatus = await getAnswersStatus(code!)
        setAnswersStatus(newStatus)
      } else {
        // Récupérer la question courante synchronisée
        const question = await getCurrentQuestion(code!)
        setCurrentQuestion(question)
        
        // Vérifier si l'équipe courante a déjà répondu
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
    // Arrêter le polling existant
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
    }

    // Démarrer un nouveau polling toutes les 2 secondes
    pollingIntervalRef.current = setInterval(async () => {
      try {
        const status = await getAnswersStatus(code!)
        setAnswersStatus(status)
        
        if (status.all_answered) {
          // Toutes les équipes ont répondu, arrêter le polling
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
    // Charger automatiquement la prochaine question
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
      setAnswerResult(result)
      
      // Mettre à jour le score local
      setGame(prev => {
        if (!prev) return prev
        const updatedTeams = [...prev.teams]
        updatedTeams[currentTeamIndex] = {
          ...updatedTeams[currentTeamIndex],
          score: result.team_score,
        }
        return { ...prev, teams: updatedTeams }
      })

      // Mettre à jour le statut des réponses
      const status = await getAnswersStatus(code!)
      setAnswersStatus(status)
      
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur')
    }
  }

  const handleNextTurn = useCallback(async () => {
    if (!game) return
    
    const newTurnCount = turnCount + 1
    setTurnCount(newTurnCount)
    
    // Ping-Pong tous les 5 tours
    if (newTurnCount % 5 === 0) {
      await startPingPong()
      return
    }
    
    // Passer à l'équipe suivante
    setCurrentTeamIndex((prev) => (prev + 1) % game.teams.length)
    await loadQuestion()
  }, [game, turnCount])

  const startPingPong = async () => {
    try {
      const theme = await getRandomPingPongTheme()
      setPingPongTheme(theme)
      setShowPingPong(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur ping-pong')
    }
  }

  const handlePingPongSubmit = async (answers: string[]) => {
    if (!game || !pingPongTheme) return
    const currentTeam = game.teams[currentTeamIndex]

    try {
      const result = await submitPingPongAnswer({
        game_session_id: game.id,
        theme_id: pingPongTheme.id,
        team_id: currentTeam.id,
        answers_given: answers
      })

      setPingPongResult(result)
      
      // Update score locally
      setGame(prev => {
        if (!prev) return prev
        const updatedTeams = [...prev.teams]
        updatedTeams[currentTeamIndex] = {
          ...updatedTeams[currentTeamIndex],
          score: result.team_score,
        }
        return { ...prev, teams: updatedTeams }
      })

      // Check if all teams have answered
      const results = await getPingPongResults(code!, pingPongTheme.id)
      if (results.all_teams_answered) {
        setPingPongResults(results)
        setShowPingPong(false)
        setShowPingPongResults(true)
      } else {
        // Move to next team
        setCurrentTeamIndex((prev) => (prev + 1) % game.teams.length)
        // Keep showing ping-pong for next team
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
    
    // Continue to next turn
    if (game) {
      setCurrentTeamIndex((prev) => (prev + 1) % game.teams.length)
      await loadQuestion()
    }
  }

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
    setWheelResult(null)
    if (game) {
      setCurrentTeamIndex((prev) => (prev + 1) % game.teams.length)
      await loadQuestion()
    }
  }

  const handleUseToken = async (tokenType: TokenType) => {
    if (!game) return
    const currentTeam = game.teams[currentTeamIndex]
    
    try {
      await useToken({ team_id: currentTeam.id, token_type: tokenType })
      
      if (tokenType === 'swap') {
        await loadQuestion()
      }
      
      // Rafraîchir les données du jeu
      await loadGame()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur jeton')
    }
  }

  const handleAdvanceToPhase2 = async () => {
    try {
      await advanceRound2Phase(code!)
      navigate(`/game/${code}/round2`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors de la transition vers la manche 2')
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-2xl text-slate-400 animate-pulse">Chargement du jeu...</div>
      </div>
    )
  }

  if (!game) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="card text-center">
          <h2 className="text-2xl text-game-danger mb-4">Erreur</h2>
          <p className="text-slate-400">{error}</p>
          <button onClick={() => navigate('/')} className="btn-primary mt-4">Retour</button>
        </div>
      </div>
    )
  }

  const currentTeam = game.teams[currentTeamIndex]

  return (
    <div className="min-h-screen p-4">
      <DevHelper code={code!} />
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">Manche 1</h1>
            <p className="text-slate-400 text-sm">Tour {turnCount + 1} • Code: {game.code}</p>
          </div>
          <button
            onClick={handleAdvanceToPhase2}
            className="btn-secondary text-sm"
          >
            Passer en Manche 2 →
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Colonne gauche: Scoreboard */}
          <div className="lg:col-span-1">
            <Scoreboard teams={game.teams} currentTeamIndex={currentTeamIndex} />
          </div>

          {/* Colonne centrale: Question */}
          <div className="lg:col-span-2 space-y-4">
            {/* Indicateur équipe active */}
            <div className="card text-center">
              <p className="text-sm text-slate-400">C'est au tour de</p>
              <p className="text-2xl font-bold text-game-accent">{currentTeam.name}</p>
            </div>

            {/* Question */}
            {currentQuestion && !answerResult && !waitingForTeams && (
              <QuestionCard
                question={currentQuestion}
                onAnswer={handleAnswer}
              />
            )}

            {/* Écran d'attente pour les autres équipes */}
            {waitingForTeams && answersStatus && (
              <WaitingForTeams
                gameCode={code!}
                currentTeam={currentTeam}
                totalTeams={answersStatus.total_teams}
                answeredCount={answersStatus.answered_teams.length}
                onAllAnswered={handleAllAnswered}
              />
            )}

            {/* Résultat de la réponse */}
            {answerResult && (
              <div className={`card text-center ${answerResult.is_correct ? 'border-game-success' : 'border-game-danger'}`}>
                <div className="text-4xl mb-3">
                  {answerResult.is_correct ? '✅' : '❌'}
                </div>
                <h3 className={`text-xl font-bold ${answerResult.is_correct ? 'text-game-success' : 'text-game-danger'}`}>
                  {answerResult.is_correct ? 'Bonne réponse !' : 'Mauvaise réponse !'}
                </h3>
                {!answerResult.is_correct && (
                  <p className="text-slate-400 mt-2">
                    Réponse correcte : <span className="text-white font-semibold">{answerResult.correct_answer}</span>
                  </p>
                )}
                <p className="text-slate-400 mt-2">
                  Points gagnés : <span className="text-game-accent font-bold">+{answerResult.points_earned}</span>
                </p>
                <button onClick={handleNextTurn} className="btn-primary mt-4">
                  Tour suivant →
                </button>
              </div>
            )}

            {/* Jetons */}
            <TokenPanel
              teamId={currentTeam.id}
              onUseToken={handleUseToken}
            />
          </div>
        </div>

        {/* Erreur */}
        {error && (
          <div className="fixed bottom-4 right-4 bg-red-900/90 text-white px-4 py-2 rounded-lg text-sm">
            {error}
            <button onClick={() => setError('')} className="ml-2 text-red-300 hover:text-white">✕</button>
          </div>
        )}

        {/* Modal Roue */}
        {showWheel && (
          <WheelModal
            onSpin={handleSpinWheel}
            result={wheelResult}
            onClose={handleCloseWheel}
          />
        )}

        {/* Modal Ping-Pong */}
        {showPingPong && pingPongTheme && (
          <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
            <div className="max-w-2xl w-full max-h-[90vh] overflow-y-auto">
              <PingPongQuestion
                theme={pingPongTheme}
                currentTeam={currentTeam}
                onSubmit={handlePingPongSubmit}
                timeLimit={60}
              />
            </div>
          </div>
        )}

        {/* Modal Ping-Pong Results */}
        {showPingPongResults && pingPongResults && (
          <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
            <div className="max-w-4xl w-full max-h-[90vh] overflow-y-auto">
              <PingPongResults
                theme={pingPongResults.theme}
                teamResults={pingPongResults.team_results}
                winnerTeamId={pingPongResults.winner_team_id}
                currentTeam={currentTeam}
                onContinue={handlePingPongContinue}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default Game

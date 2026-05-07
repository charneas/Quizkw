import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getGame, getRandomQuestion, submitAnswer, useToken, spinWheel } from '../services/api'
import type { GameSession, QuestionResponse, AnswerResponse, WheelSpinResponse, TokenType } from '../types'
import Scoreboard from '../components/Scoreboard'
import QuestionCard from '../components/QuestionCard'
import TokenPanel from '../components/TokenPanel'
import WheelModal from '../components/WheelModal'

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

  useEffect(() => {
    if (code) loadGame()
  }, [code])

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
      const question = await getRandomQuestion()
      setCurrentQuestion(question)
      setAnswerResult(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Aucune question disponible')
    }
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
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur')
    }
  }

  const handleNextTurn = useCallback(async () => {
    if (!game) return
    
    const newTurnCount = turnCount + 1
    setTurnCount(newTurnCount)
    
    // Roue tous les 5 tours
    if (newTurnCount % 5 === 0) {
      setShowWheel(true)
      return
    }
    
    // Passer à l'équipe suivante
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

  const handleAdvanceToPhase3 = () => {
    navigate(`/game/${code}/memory-grid`)
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
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">Manche 1</h1>
            <p className="text-slate-400 text-sm">Tour {turnCount + 1} • Code: {game.code}</p>
          </div>
          <button
            onClick={handleAdvanceToPhase3}
            className="btn-secondary text-sm"
          >
            Passer en Manche 3 →
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
            {currentQuestion && !answerResult && (
              <QuestionCard
                question={currentQuestion}
                onAnswer={handleAnswer}
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
      </div>
    </div>
  )
}

export default Game

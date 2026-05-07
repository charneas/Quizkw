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
  getGame
} from '../services/api'
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

function Round2() {
  const { code } = useParams<{ code: string }>()
  const navigate = useNavigate()
  
  const [, setGame] = useState<GameSession | null>(null)
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

      setLoading(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error loading Round 2')
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
      setError('Please select a player first')
      return
    }

    try {
      const response = await selectTheme(code!, { theme_id: theme.id })
      setSelectedTheme(response.theme)
      setPlayerStats(response.player_stats)
      setError('')
      
      // Load first question
      await loadNextQuestion()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error selecting theme')
    }
  }

  const loadNextQuestion = async () => {
    if (!playerStats || !currentPlayer) return
    
    try {
      const question = await getRound2Question(code!, currentPlayer.id)
      setCurrentQuestion(question)
      setAnswerResult(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error loading question')
    }
  }

  const handleAnswerSubmit = async (answer: string) => {
    if (!currentQuestion || !playerStats || !currentPlayer) return
    
    try {
      const result = await submitRound2Answer(code!, {
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
      setError(err instanceof Error ? err.message : 'Error submitting answer')
    }
  }

  const handleNextQuestion = async () => {
    setAnswerResult(null)
    if (answerResult?.next_question_available) {
      await loadNextQuestion()
    } else {
      // Player has finished all questions
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
      setError(err instanceof Error ? err.message : 'Error checking progress')
    }
  }

  const loadLeaderboard = async () => {
    try {
      const leaderboardData = await getRound2Leaderboard(code!)
      setLeaderboard(leaderboardData)
      setIsWaitingForLeaderboard(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error loading leaderboard')
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
      setError(err instanceof Error ? err.message : 'Error advancing phase')
    }
  }

  const getCurrentPhaseText = () => {
    if (!tournamentProgress) return ''
    
    switch (tournamentProgress.phase) {
      case '16_players':
        return '16 Players Phase - Select Theme and Answer Questions'
      case '8_qualified':
        return '8 Qualified Phase - Intermediate Leaderboard'
      case '4_finalists':
        return '4 Finalists Phase - Ready for Round 3'
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

  return (
    <div className="min-h-screen bg-gradient-to-b from-blue-900 to-purple-900 p-4 md:p-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <header className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">Round 2: 16→8→4 Tournament</h1>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-gray-300">Game Code: {code}</p>
              <p className="text-gray-300">{getCurrentPhaseText()}</p>
              {currentPlayer && (
                <p className="text-gray-300">Player: <span className="text-white">{currentPlayer.name}</span></p>
              )}
            </div>
            <button
              className="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded-lg"
              onClick={() => navigate(`/game/${code}`)}
            >
              Back to Game
            </button>
          </div>
        </header>

        {/* Tournament Progress */}
        {tournamentProgress && (
          <TournamentProgressComponent progress={tournamentProgress} />
        )}

        {/* Loading */}
        {loading && (
          <div className="bg-gray-800 rounded-lg p-8 text-center">
            <div className="animate-spin h-8 w-8 border-4 border-white border-t-transparent rounded-full mx-auto mb-4"></div>
            <p className="text-white">Loading Round 2...</p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-900 rounded-lg p-4 mb-4">
            <p className="text-white">{error}</p>
          </div>
        )}

        {/* Player Selection */}
        {!loading && !error && !currentPlayer && (
          <PlayerSelection
            gameCode={code!}
            onSelectPlayer={handlePlayerSelection}
            existingPlayers={[]} // Could be populated from API in future
          />
        )}

        {/* Theme Selection */}
        {!loading && !error && currentPlayer && themes.length > 0 && !selectedTheme && (
          <ThemeSelectorComponent
            themes={themes}
            onSelectTheme={handleThemeSelection}
            gameCode={code!}
          />
        )}

        {/* Question Flow */}
        {selectedTheme && currentQuestion && !answerResult && (
          <div className="bg-gray-800 rounded-lg p-6 mb-6">
            <div className="mb-4">
              <h2 className="text-2xl font-bold text-white mb-2">
                Question {currentQuestion.question_number} (Difficulty: {currentQuestion.difficulty}/10)
              </h2>
              <p className="text-gray-400 mb-2">Theme: {selectedTheme.name}</p>
              <div className="bg-gray-700 rounded p-4 mb-4">
                <p className="text-white text-lg">{currentQuestion.question.text}</p>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {currentQuestion.options.map((option, index) => (
                <button
                  key={index}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white p-4 rounded-lg text-center"
                  onClick={() => handleAnswerSubmit(option)}
                >
                  {option}
                </button>
              ))}
            </div>

            <div className="mt-4 text-gray-300">
              <p>Time limit: {currentQuestion.time_limit} seconds</p>
              <p>Current score: {playerStats?.score}</p>
              <p>Questions answered: {playerStats?.questions_answered}/10</p>
            </div>
          </div>
        )}

        {/* Answer Result */}
        {answerResult && (
          <div className="bg-gray-800 rounded-lg p-6 mb-6">
            <div className={`p-4 rounded-lg mb-4 ${answerResult.is_correct ? 'bg-green-900' : 'bg-red-900'}`}>
              <h3 className="text-xl font-bold text-white">
                {answerResult.is_correct ? '✅ Correct!' : '❌ Incorrect'}
              </h3>
              <p className="text-white">Points awarded: {answerResult.points_awarded}</p>
              <p className="text-white mt-2">Correct answer: {answerResult.correct_answer}</p>
            </div>

            <div className="bg-gray-700 rounded p-4 mb-4">
              <p className="text-white">Your new score: {answerResult.player_score}</p>
              <p className="text-gray-300">
                Questions answered: {playerStats?.questions_answered}/10
              </p>
            </div>

            <div className="flex justify-center">
              <button
                className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg"
                onClick={handleNextQuestion}
              >
                {answerResult.next_question_available ? 'Next Question' : 'Finish'}
              </button>
            </div>
          </div>
        )}

        {/* Waiting for Leaderboard */}
        {isWaitingForLeaderboard && (
          <div className="bg-gray-800 rounded-lg p-8 text-center">
            <div className="animate-spin h-8 w-8 border-4 border-white border-t-transparent rounded-full mx-auto mb-4"></div>
            <p className="text-white mb-2">Waiting for all players to finish...</p>
            <p className="text-gray-300">
              {tournamentProgress?.players_remaining}/{tournamentProgress?.players_total} players remaining
            </p>
          </div>
        )}

        {/* Intermediate Leaderboard */}
        {leaderboard && tournamentProgress?.phase === '8_qualified' && (
          <IntermediateLeaderboardComponent
            leaderboard={leaderboard}
            tournamentProgress={tournamentProgress}
            onAdvance={handleAdvancePhase}
          />
        )}

        {/* Finalists Phase */}
        {tournamentProgress?.phase === '4_finalists' && (
          <div className="bg-gray-800 rounded-lg p-8 text-center">
            <h2 className="text-3xl font-bold text-white mb-4">🎉 You are a Finalist!</h2>
            <p className="text-gray-300 mb-6">
              Congratulations! You have qualified for Round 3 (Memory Grid).
            </p>
            <button
              className="bg-green-600 hover:bg-green-700 text-white px-6 py-3 rounded-lg"
              onClick={() => navigate(`/game/${code}/memory-grid`)}
            >
              Continue to Round 3 (Memory Grid)
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default Round2
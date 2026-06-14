import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getTeamState, submitAnswer, useToken, getPingPongDuelState, getPingPongDuelResults, submitPingPongDuelAnswer } from '../services/api'
import type { TokenType } from '../types'
import PingPongQuestion from '../components/PingPongQuestion'
import PingPongResults from '../components/PingPongResults'
import TokenPanel from '../components/TokenPanel'

interface TeamStateData {
  team_id: number
  team_name: string
  team_score: number
  game_phase: string
  is_my_turn: boolean
  has_answered: boolean
  current_question: {
    id: number
    text: string
    category: string
    difficulty: string
    points: number
    correct_answer: string | null
    options: string[]
  } | null
  active_duel: {
    duel_id: number
    theme: { id: number; title: string; description: string | null; correct_answers: string[]; min_answers_to_win: number }
    team1: { id: number; name: string }
    team2: { id: number; name: string }
    current_turn_team_id: number
    current_turn_team_name: string
    turn_number: number
    answers_used: string[]
    is_completed: boolean
    winner_team_id: number | null
    is_my_turn_in_duel: boolean
  } | null
  tokens: { id: number; token_type: string; is_used: boolean }[]
  other_teams: { team_id: number; team_name: string; has_answered: boolean }[]
}

function TeamScreen() {
  const { code, teamId } = useParams<{ code: string; teamId: string }>()
  const navigate = useNavigate()
  const teamIdNum = Number(teamId)

  const [state, setState] = useState<TeamStateData | null>(null)
  const [answer, setAnswer] = useState('')
  const [answerResult, setAnswerResult] = useState<{ is_correct: boolean; correct_answer: string; points_earned: number } | null>(null)
  const [duelResult, setDuelResult] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (code && teamIdNum) {
      loadState()
      startPolling()
    }
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  }, [code, teamIdNum])

  // Quand la question change (ou disparaît), effacer le résultat local de la question précédente
  useEffect(() => {
    setAnswerResult(null)
    setDuelResult(null)
  }, [state?.current_question?.id])

  const loadState = async () => {
    try {
      const data = await getTeamState(code!, teamIdNum)
      setState(data)
      setLoading(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur')
      setLoading(false)
    }
  }

  const startPolling = () => {
    pollingRef.current = setInterval(async () => {
      try {
        const data = await getTeamState(code!, teamIdNum)
        setState(data)
      } catch (err) {
        console.error('Polling error:', err)
      }
    }, 2000)
  }

  const handleSubmitAnswer = async () => {
    if (!state?.current_question || !answer.trim()) return

    try {
      const result = await submitAnswer({
        question_id: state.current_question.id,
        team_id: teamIdNum,
        player_answer: answer.trim(),
      })
      setAnswerResult(result)
      setAnswer('')
      await loadState()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors de la réponse')
    }
  }

  const handleDuelAnswer = async (duelAnswer: string) => {
    if (!state?.active_duel) return

    try {
      const result = await submitPingPongDuelAnswer({
        duel_id: state.active_duel.duel_id,
        team_id: teamIdNum,
        answer: duelAnswer,
      })

      setDuelResult(result)

      if (!result.duel_continues) {
        const results = await getPingPongDuelResults(state.active_duel.duel_id)
        setDuelResult({ ...result, final: results })
      } else {
        const freshDuelState = await getPingPongDuelState(state.active_duel.duel_id)
        setState(prev => prev ? {
          ...prev,
          active_duel: {
            ...freshDuelState,
            is_my_turn_in_duel: freshDuelState.current_turn_team_id === teamIdNum,
          }
        } : null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur duel')
    }
  }

  const handleDuelPass = async () => {
    await handleDuelAnswer('__PASS__')
  }

  const handleUseToken = async (tokenType: TokenType) => {
    try {
      await useToken({ team_id: teamIdNum, token_type: tokenType })
      await loadState()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur jeton')
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-2xl text-slate-400 animate-pulse">Connexion à la partie...</div>
      </div>
    )
  }

  if (!state) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="card text-center max-w-md">
          <h2 className="text-2xl font-bold text-game-danger mb-4">❌ Équipe non trouvée</h2>
          <p className="text-slate-400">{error}</p>
          <button onClick={() => navigate('/')} className="btn-primary mt-4">Retour</button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen p-4">
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-2xl font-bold text-white">{state.team_name}</h1>
          <p className="text-slate-400">
            Score : <span className="text-game-accent font-bold">{state.team_score} pts</span>
            {' • '}
            Manche : <span className="text-white font-semibold">{state.game_phase}</span>
          </p>
        </div>

        {/* Statut des autres équipes */}
        {state.other_teams.length > 0 && (
          <div className="card">
            <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">
              Progression des équipes
            </h3>
            <div className="space-y-2">
              {state.other_teams.map((team) => (
                <div key={team.team_id} className="flex items-center justify-between">
                  <span className="text-sm">{team.team_name}</span>
                  <span className={team.has_answered ? 'text-game-success' : 'text-slate-500'}>
                    {team.has_answered ? '✓ Répondu' : '⏳ En attente'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Question courante */}
        {state.current_question && !state.has_answered && (
          <div className="card">
            <h3 className="text-lg font-semibold mb-3">
              {state.current_question.text}
            </h3>
            <p className="text-xs text-slate-500 mb-4">
              {state.current_question.category} • {state.current_question.points} pts
            </p>

            <div className="space-y-2 mb-4">
              {state.current_question.options.map((option, index) => (
                <button
                  key={index}
                  onClick={() => setAnswer(option)}
                  className={`w-full text-left p-3 rounded-lg border transition-colors ${
                    answer === option
                      ? 'border-game-accent bg-game-accent/10 text-white'
                      : 'border-slate-600 bg-slate-800 text-slate-300 hover:border-slate-400'
                  }`}
                >
                  {option}
                </button>
              ))}
            </div>

            <div className="flex gap-3">
              <input
                type="text"
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSubmitAnswer()}
                placeholder="Ou tapez votre réponse..."
                className="input-field flex-1"
              />
              <button
                onClick={handleSubmitAnswer}
                disabled={!answer.trim()}
                className="btn-primary disabled:opacity-50"
              >
                Valider
              </button>
            </div>
          </div>
        )}

        {/* Réponse envoyée — en attente de validation par l'host */}
        {state.has_answered && !answerResult && (
          <div className="card text-center py-8 border-game-accent">
            <div className="text-6xl mb-4">📤</div>
            <p className="text-xl text-game-accent font-semibold">
              Réponse envoyée !
            </p>
            <p className="text-sm text-slate-400 mt-2">
              En attente de validation par l'hôte...
            </p>
          </div>
        )}

        {/* Résultat de la réponse (après validation host) */}
        {answerResult && (
          <div className={`card text-center ${answerResult.is_correct ? 'border-game-success' : 'border-game-danger'}`}>
            <div className="text-4xl mb-3">{answerResult.is_correct ? '✅' : '❌'}</div>
            <h3 className={`text-xl font-bold ${answerResult.is_correct ? 'text-game-success' : 'text-game-danger'}`}>
              {answerResult.is_correct ? 'Bonne réponse !' : 'Mauvaise réponse !'}
            </h3>
            {!answerResult.is_correct && (
              <p className="text-slate-400 mt-2">
                Réponse : <span className="text-white font-semibold">{answerResult.correct_answer}</span>
              </p>
            )}
            <p className="mt-2">
              +{answerResult.points_earned} points
            </p>
          </div>
        )}

        {/* En attente de son tour */}
        {!state.is_my_turn && !state.active_duel && !state.has_answered && (
          <div className="card text-center py-8">
            <div className="text-6xl mb-4 animate-pulse">⏳</div>
            <p className="text-xl text-slate-400">
              En attente de votre tour...
            </p>
            <p className="text-sm text-slate-500 mt-2">L'hôte contrôle le déroulé du jeu</p>
          </div>
        )}

        {/* Duel Ping-Pong */}
        {state.active_duel && (
          <div className="card">
            {duelResult ? (
              <PingPongResults
                theme={duelResult.final?.theme || state.active_duel.theme}
                team1={{
                  id: state.active_duel.team1.id,
                  name: state.active_duel.team1.name,
                  turns: duelResult.final?.team1.turns || 0,
                  correctAnswers: duelResult.final?.team1.correct_answers || [],
                }}
                team2={{
                  id: state.active_duel.team2.id,
                  name: state.active_duel.team2.name,
                  turns: duelResult.final?.team2.turns || 0,
                  correctAnswers: duelResult.final?.team2.correct_answers || [],
                }}
                winnerTeamId={duelResult.final?.winner_team_id || duelResult.winner_team_id}
                winnerTeamName={duelResult.final?.winner_team_name || duelResult.winner_team_name}
                totalTurns={duelResult.final?.total_turns || 1}
                answersUsed={duelResult.final?.answers_used || []}
                onContinue={async () => {
                  setDuelResult(null)
                  await loadState()
                }}
              />
            ) : (
              <PingPongQuestion
                theme={state.active_duel.theme}
                team1={{
                  id: state.active_duel.team1.id,
                  name: state.active_duel.team1.name,
                  game_session_id: 0,
                  score: 0,
                  players: [],
                }}
                team2={{
                  id: state.active_duel.team2.id,
                  name: state.active_duel.team2.name,
                  game_session_id: 0,
                  score: 0,
                  players: [],
                }}
                currentTurnTeamId={state.active_duel.current_turn_team_id}
                answersUsed={state.active_duel.answers_used || []}
                turnNumber={state.active_duel.turn_number || 1}
                isCurrentTeam={state.active_duel.is_my_turn_in_duel}
                onSubmit={handleDuelAnswer}
                onPass={handleDuelPass}
                disabled={!state.active_duel.is_my_turn_in_duel || state.active_duel.is_completed}
              />
            )}
          </div>
        )}

        {/* Jetons */}
        {state.tokens.length > 0 && (
          <TokenPanel teamId={teamIdNum} onUseToken={handleUseToken} />
        )}

        {/* Erreur */}
        {error && (
          <div className="fixed bottom-4 right-4 bg-red-900/90 text-white px-4 py-2 rounded-lg text-sm">
            {error}
            <button onClick={() => setError('')} className="ml-2 text-red-300 hover:text-white">✕</button>
          </div>
        )}
      </div>
    </div>
  )
}

export default TeamScreen
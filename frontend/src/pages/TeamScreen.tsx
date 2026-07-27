import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getTeamState, submitAnswer, useToken, getPingPongDuelState, getPingPongDuelResults, submitPingPongDuelAnswer, nextQuestion } from '../services/api'
import type { TokenType } from '../types'
import PingPongQuestion from '../components/PingPongQuestion'
import PingPongResults from '../components/PingPongResults'
import TokenPanel from '../components/TokenPanel'

interface TeamStateData {
  team_id: number
  team_name: string
  team_score: number
  game_started: boolean
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
  all_answered: boolean
  validation_result: {
    correct_answer: string
    teams: { team_name: string; is_correct: boolean; points_earned: number }[]
  } | null
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
  // E-001 AC1/AC4 : dès que le serveur signale (AD-8) que la partie a quitté
  // la Manche 1, on l'explique puis on redirige automatiquement vers l'écran
  // de Manche 2 — jusqu'ici la seule navigation existante était le clic de
  // l'hôte sur son propre écran, qui ne redirigeait personne d'autre.
  const [advancingToPhase, setAdvancingToPhase] = useState<string | null>(null)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const lastDuelRef = useRef<TeamStateData['active_duel']>(null)
  const duelResultRef = useRef<any>(null)
  // Ref plutôt que le state advancingToPhase lui-même : sinon le mettre à
  // jour redéclencherait cet effet (il est nécessairement dans les deps pour
  // le lire) et son nettoyage annulerait le timer qu'il vient de programmer.
  const hasStartedAdvanceRef = useRef(false)

  useEffect(() => {
    if (code && teamIdNum) {
      loadState()
      startPolling()
    }
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  }, [code, teamIdNum])

  useEffect(() => {
    if (!state || state.game_phase === 'manche_1' || hasStartedAdvanceRef.current) return

    hasStartedAdvanceRef.current = true
    setAdvancingToPhase(state.game_phase)
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
    const timer = setTimeout(() => navigate(`/game/${code}/round2`), 1800)
    return () => clearTimeout(timer)
  }, [state?.game_phase, code, navigate])

  // Sauvegarder les données du duel dans le ref tant qu'il est actif
  useEffect(() => {
    if (state?.active_duel) {
      lastDuelRef.current = state.active_duel
    }
  }, [state?.active_duel])

  // Synchroniser le ref avec l'état du duelResult
  useEffect(() => {
    duelResultRef.current = duelResult
  }, [duelResult])

  // Quand la question change (ou disparaît), effacer le résultat local de la question précédente
  // Mais ne PAS effacer duelResult (le duel est indépendant de la question courante)
  useEffect(() => {
    setAnswerResult(null)
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
        // Préserver active_duel si on affiche des résultats de duel
        // (le backend retourne null une fois le duel terminé, mais on veut garder l'UI)
        if (duelResultRef.current && !data.active_duel && lastDuelRef.current) {
          data.active_duel = lastDuelRef.current
        }
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

  const handleNextQuestion = async () => {
    if (!code) return
    try {
      await nextQuestion(code)
      setAnswerResult(null)
      await loadState()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors du changement de question')
    }
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
        <div className="text-2xl text-text-muted animate-pulse">Connexion à la partie...</div>
      </div>
    )
  }

  if (advancingToPhase) {
    // Le libellé reflète la phase réellement observée : un joueur peut charger
    // cet écran pour la première fois alors que la partie est déjà en Manche 3
    // (rechargement tardif, onglet ouvert après les deux transitions) — le
    // texte ne doit pas prétendre que la Manche 1 vient tout juste de finir
    // dans ce cas (trouvé en revue de code).
    const message =
      advancingToPhase === 'manche_3'
        ? "La partie est déjà en Manche 3. Direction la Manche 2 pour voir où vous en êtes dans le tournoi..."
        : 'Votre équipe a joué son rôle collectif dans la Manche 1. La suite se joue individuellement — direction la Manche 2 pour choisir votre thème...'

    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="card text-center max-w-md">
          <div className="text-5xl mb-4">🏁</div>
          <h2 className="text-2xl font-bold text-brand mb-2">Manche 1 terminée !</h2>
          <p className="text-text-muted">{message}</p>
        </div>
      </div>
    )
  }

  if (!state) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="card text-center max-w-md">
          <h2 className="text-2xl font-bold text-danger mb-4">❌ Équipe non trouvée</h2>
          <p className="text-text-muted">{error}</p>
          <button onClick={() => navigate('/')} className="btn-primary mt-4">Retour</button>
        </div>
      </div>
    )
  }

  if (!state.game_started) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="card text-center max-w-md">
          <div className="text-5xl mb-4 animate-pulse">⏳</div>
          <h2 className="text-2xl font-bold text-text mb-2">Salle d'attente</h2>
          <p className="text-text-muted">
            Vous avez rejoint <span className="text-brand font-semibold">{state.team_name}</span>.
            En attente que l'hôte lance la partie...
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen p-4">
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-2xl font-bold text-text">{state.team_name}</h1>
          <p className="text-text-muted">
            Score : <span className="text-brand font-bold">{state.team_score} pts</span>
            {' • '}
            Manche : <span className="text-text font-semibold">{state.game_phase}</span>
          </p>
        </div>

        {/* Statut des autres équipes */}
        {state.other_teams.length > 0 && (
          <div className="card">
            <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wide mb-3">
              Progression des équipes
            </h3>
            <div className="space-y-2">
              {state.other_teams.map((team) => (
                <div key={team.team_id} className="flex items-center justify-between">
                  <span className="text-sm">{team.team_name}</span>
                  <span className={team.has_answered ? 'text-success' : 'text-text-muted'}>
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
            <p className="text-xs text-text-muted mb-4">
              {state.current_question.category} • {state.current_question.points} pts
            </p>

            <div className="space-y-2 mb-4">
              {state.current_question.options.map((option, index) => (
                <button
                  key={index}
                  onClick={() => setAnswer(option)}
                  className={`w-full text-left p-3 rounded-lg border transition-colors ${
                    answer === option
                      ? 'border-brand bg-brand-muted/20 text-text'
                      : 'border-border bg-surface text-text-muted hover:border-brand'
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

        {/* Résultats validés (auto-validation quand toutes les équipes ont répondu) */}
        {state.validation_result && (
          <div className="card border-success">
            <h3 className="text-lg font-bold text-success mb-3">✅ Réponses validées !</h3>
            <p className="text-sm text-text-muted mb-2">
              Réponse correcte : <span className="text-text font-semibold">{state.validation_result.correct_answer}</span>
            </p>
            <div className="space-y-1 mb-4">
              {state.validation_result.teams.map((t, idx) => (
                <div key={idx} className="flex justify-between text-sm">
                  <span>{t.team_name}</span>
                  <span className={t.is_correct ? 'text-success' : 'text-danger'}>
                    {t.is_correct ? `+${t.points_earned} pts` : '✗'}
                  </span>
                </div>
              ))}
            </div>
            <button onClick={handleNextQuestion} className="btn-primary w-full">
              Tour suivant →
            </button>
          </div>
        )}

        {/* Réponse envoyée — en attente des autres équipes */}
        {state.has_answered && !state.validation_result && (
          <div className="card text-center py-8 border-brand">
            <div className="text-6xl mb-4">📤</div>
            <p className="text-xl text-brand font-semibold">
              Réponse envoyée !
            </p>
            {answerResult && (
              <p className={`text-sm mt-2 ${answerResult.is_correct ? 'text-success' : 'text-danger'}`}>
                {answerResult.is_correct ? '✅ Bonne réponse !' : '❌ Mauvaise réponse'}
              </p>
            )}
            <p className="text-sm text-text-muted mt-2">
              ⏳ En attente des autres équipes...
            </p>
          </div>
        )}

        {/* Pas de question en cours — possibilité d'en lancer une */}
        {!state.current_question && !state.has_answered && !state.validation_result && !state.active_duel && (
          <div className="card text-center py-8">
            <div className="text-6xl mb-4">🎯</div>
            <p className="text-xl text-text-muted mb-4">
              Pas de question en cours
            </p>
            <button onClick={handleNextQuestion} className="btn-primary">
              Lancer une question →
            </button>
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
                  lastDuelRef.current = null
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
          <TokenPanel tokens={state.tokens} onUseToken={handleUseToken} />
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

export default TeamScreen
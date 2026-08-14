import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getTeamState, submitAnswer, useToken, getPingPongDuelState, getPingPongDuelResults, submitPingPongDuelAnswer, nextQuestion, getRandomPingPongTheme, startPingPongDuel, getWheelHistory, renameTeam, getHostToken, validateAnswers } from '../services/api'
import type { WheelHistoryEntry } from '../services/api'
import WheelHistory from '../components/WheelHistory'
import WheelResultPopup from '../components/WheelResultPopup'
import type { TokenType, Team } from '../types'
import PingPongQuestion from '../components/PingPongQuestion'
import PingPongResults from '../components/PingPongResults'
import PingPongTeamSelector from '../components/PingPongTeamSelector'
import TokenPanel from '../components/TokenPanel'
import ConfirmModal from '../components/ConfirmModal'

interface DuelState {
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
  is_cancelled: boolean
  is_my_turn_in_duel: boolean
}

interface TeamStateData {
  team_id: number
  team_name: string
  team_score: number
  game_session_id: number
  game_started: boolean
  game_phase: string
  is_my_turn: boolean
  has_answered: boolean
  answer_locked: boolean
  current_question: {
    id: number
    text: string
    category: string
    difficulty: string
    points: number
    correct_answer: string | null
    options: string[]
    answer_locked: boolean
    current_team_answer: string | null
    image_url: string | null
  } | null
  active_duel: DuelState | null
  // BUG-104 / Story J.001 : duel d'une AUTRE équipe, en lecture seule,
  // renseigné uniquement quand active_duel est null pour cette équipe.
  spectator_duel: DuelState | null
  tokens: { id: number; token_type: string; is_used: boolean }[]
  other_teams: { team_id: number; team_name: string; team_score: number; has_answered: boolean }[]
  all_answered: boolean
  validation_result: {
    correct_answer: string
    teams: { team_name: string; is_correct: boolean; points_earned: number; player_answer?: string }[]
  } | null
  last_wheel_event: {
    id: number
    effect_type: string
    value: number | null
    target_team_id: number
    target_team_name: string
    message: string
  } | null
  last_token_used?: {
    id: number
    user_team_id: number
    user_team_name: string
    token_type: string
    target_team_id?: number
    target_team_name?: string
  } | null
}

// Duel ping-pong : un tour se joue vite (une seule réponse courte).
const PING_PONG_TURN_DURATION_SECONDS = 20

function TeamScreen() {
  const { code, teamId } = useParams<{ code: string; teamId: string }>()
  const navigate = useNavigate()
  const teamIdNum = Number(teamId)

  const [state, setState] = useState<TeamStateData | null>(null)
  const [answer, setAnswer] = useState('')
  const [duelResult, setDuelResult] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [feedbackMessage, setFeedbackMessage] = useState<{ type: 'swap' | 'penalty' | 'bonus', text: string } | null>(null)
  const [editingName, setEditingName] = useState(false)
  const [nameDraft, setNameDraft] = useState('')
  const [validating, setValidating] = useState(false)
  const [showValidateConfirm, setShowValidateConfirm] = useState(false)
  const isHost = !!code && !!getHostToken(code)
  const [renameError, setRenameError] = useState('')
  // BUG-106 (#8) : vue consolidée des tours de roue déjà joués.
  const [wheelHistory, setWheelHistory] = useState<WheelHistoryEntry[]>([])

  const [advancingToPhase, setAdvancingToPhase] = useState<string | null>(null)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const lastDuelRef = useRef<TeamStateData['active_duel']>(null)
  const duelResultRef = useRef<any>(null)
  const hasStartedAdvanceRef = useRef(false)
  const lastSeenTokenIdRef = useRef<number | null>(null)

  useEffect(() => {
    if (code && teamIdNum) {
      loadState()
      startPolling()
    }
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  }, [code, teamIdNum])

  // BUG-106 (#8) : historique de la roue, poll léger indépendant du poll
  // d'état d'équipe (2s) — pas besoin de la même fréquence.
  useEffect(() => {
    if (!code) return
    const fetchHistory = async () => {
      try {
        const { history } = await getWheelHistory(code)
        setWheelHistory(history)
      } catch {
        // Ignoré : un prochain tick réessaiera.
      }
    }
    fetchHistory()
    const interval = setInterval(fetchHistory, 5000)
    return () => clearInterval(interval)
  }, [code])

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

  useEffect(() => {
    if (state?.active_duel) {
      lastDuelRef.current = state.active_duel
    }
  }, [state?.active_duel])

  // Timer du duel ping-pong : plus long qu'en Manche 2 (temps de réflexion à
  // deux, réponses moins immédiates), mais expiration = perdu pour l'équipe
  // qui avait la main (auto-abandon), comme le bouton "Abandonner" manuel.
  // Redémarre à chaque nouveau tour (duel, numéro de tour ou équipe active).
  const [duelTimeRemaining, setDuelTimeRemaining] = useState<number | null>(null)

  useEffect(() => {
    if (!state?.active_duel || state.active_duel.is_completed) {
      setDuelTimeRemaining(null)
      return
    }
    setDuelTimeRemaining(PING_PONG_TURN_DURATION_SECONDS)
  }, [
    state?.active_duel?.duel_id,
    state?.active_duel?.turn_number,
    state?.active_duel?.current_turn_team_id,
    state?.active_duel?.is_completed,
  ])

  useEffect(() => {
    if (duelTimeRemaining === null) return
    if (duelTimeRemaining <= 0) {
      // Seule l'équipe dont c'est le tour déclenche l'abandon automatique —
      // évite un double appel si les deux écrans d'équipe touchent 0 en
      // même temps.
      if (state?.active_duel?.is_my_turn_in_duel && !duelResult) {
        handleDuelPass()
      }
      return
    }
    const timer = setTimeout(() => setDuelTimeRemaining((prev) => (prev !== null ? prev - 1 : null)), 1000)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [duelTimeRemaining])

  useEffect(() => {
    duelResultRef.current = duelResult
  }, [duelResult])

  // ÉCOUTE DES JETONS DÉCLENCHÉS PAR D'AUTRES ÉQUIPES (POLLING)
  useEffect(() => {
    const tokenEvent = state?.last_token_used
    if (!tokenEvent) return

    // Si le jeton est identique à celui déjà traité, on ne fait rien
    if (tokenEvent.id === lastSeenTokenIdRef.current) return

    // Initialisation lors du tout premier chargement
    if (lastSeenTokenIdRef.current === null) {
      lastSeenTokenIdRef.current = tokenEvent.id
      return
    }

    lastSeenTokenIdRef.current = tokenEvent.id

    const rawType = String(tokenEvent.token_type || '').toUpperCase()
    const userTeamId = Number(tokenEvent.user_team_id)
    const targetTeamId = Number(tokenEvent.target_team_id)
    const currentTeamId = Number(teamIdNum)

    // L'action locale est déjà gérée par handleUseToken au clic
    if (userTeamId === currentTeamId) return

    if (rawType.includes('SWAP')) {
      setFeedbackMessage({
        type: 'swap',
        text: `🔀 Changement de question ! L'équipe ${tokenEvent.user_team_name || 'adverse'} a utilisé un SWAP !`
      })
    } else if (rawType.includes('PENALT') || rawType.includes('PÉNALIT')) {
      if (targetTeamId === currentTeamId) {
        setFeedbackMessage({
          type: 'penalty',
          text: `⚡ PÉNALITÉ ! L'équipe ${tokenEvent.user_team_name} vous a infligé une pénalité !`
        })
      } else {
        setFeedbackMessage({
          type: 'penalty',
          text: `⚡ Pénalité ! L'équipe ${tokenEvent.user_team_name} a ciblé ${tokenEvent.target_team_name || 'une équipe'} !`
        })
      }
    }

    const isPenalty = rawType.includes('PENALT') || rawType.includes('PÉNALIT')
    const timer = setTimeout(() => setFeedbackMessage(null), isPenalty ? 8000 : 5000)
    return () => clearTimeout(timer)
  }, [state?.last_token_used?.id, teamIdNum])

  const [wheelEventToShow, setWheelEventToShow] = useState<TeamStateData['last_wheel_event']>(null)
  const [choosingPingPongOpponent, setChoosingPingPongOpponent] = useState(false)
  const seenWheelEventIdRef = useRef<number | null>(null)
  const wheelEventBaselineSetRef = useRef(false)

  useEffect(() => {
    const event = state?.last_wheel_event
    if (!wheelEventBaselineSetRef.current) {
      wheelEventBaselineSetRef.current = true
      seenWheelEventIdRef.current = event ? event.id : null
      return
    }
    if (event && event.id !== seenWheelEventIdRef.current) {
      seenWheelEventIdRef.current = event.id
      if (event.effect_type === 'ping_pong' && event.target_team_id === teamIdNum) {
        setChoosingPingPongOpponent(true)
      } else {
        setWheelEventToShow(event)
      }
    }
  }, [state?.last_wheel_event, teamIdNum])

  const handleChooseWheelPingPongOpponent = async (opponent: Team) => {
    if (!state) return
    try {
      const theme = await getRandomPingPongTheme()
      await startPingPongDuel({
        game_session_id: state.game_session_id,
        theme_id: theme.id,
        team1_id: teamIdNum,
        team2_id: opponent.id,
      })
      setChoosingPingPongOpponent(false)
      await loadState()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors du démarrage du duel')
    }
  }

  // Quand la question change (ou disparaît), effacer le résultat local de la question précédente
  // Mais ne PAS effacer duelResult (le duel est indépendant de la question courante)
  // BUG-110 : synchroniser le champ avec la réponse d'équipe soumise par un
  // coéquipier (polling), sans écraser une saisie en cours de frappe. On ne
  // suit que si le champ local n'a pas divergé depuis la dernière valeur
  // reçue du serveur (lastSyncedAnswerRef) — sinon l'utilisateur est en
  // train de taper sa propre correction, on ne l'écrase pas.
  const lastQuestionIdRef = useRef<number | null>(null)
  const lastSyncedAnswerRef = useRef('')
  useEffect(() => {
    if (!state?.current_question) return
    const q = state.current_question

    if (lastQuestionIdRef.current !== q.id) {
      // Nouvelle question : repartir d'un champ propre (vidé, ou pré-rempli
      // si un coéquipier a déjà répondu avant que ce joueur ne charge l'état).
      lastQuestionIdRef.current = q.id
      const initial = q.current_team_answer ?? ''
      lastSyncedAnswerRef.current = initial
      setAnswer(initial)
      return
    }

    if (q.answer_locked) return
    const teamAnswer = q.current_team_answer ?? ''
    if (answer === lastSyncedAnswerRef.current && teamAnswer !== answer) {
      setAnswer(teamAnswer)
    }
    lastSyncedAnswerRef.current = teamAnswer
  }, [state?.current_question?.id, state?.current_question?.current_team_answer, state?.current_question?.answer_locked])

  const handleRenameTeam = async () => {
    const trimmed = nameDraft.trim()
    if (!trimmed || !code) return
    setRenameError('')
    try {
      await renameTeam(code, teamIdNum, trimmed)
      setState((prev) => (prev ? { ...prev, team_name: trimmed } : prev))
      setEditingName(false)
    } catch (err: any) {
      setRenameError(err?.message || "Impossible de renommer l'equipe")
    }
  }

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
      const submitted = answer.trim()
      await submitAnswer({
        question_id: state.current_question.id,
        team_id: teamIdNum,
        player_answer: submitted,
      })
      // La réponse soumise reste affichée (modifiable) — pas de setAnswer(''),
      // sinon le prochain poll écraserait le champ avec la valeur qu'on vient
      // nous-mêmes d'envoyer (cf. lastSyncedAnswerRef dans l'effet de sync).
      lastSyncedAnswerRef.current = submitted
      await loadState()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors de la réponse')
    }
  }

  const handleValidateAnswers = async () => {
    if (!code) return
    setValidating(true)
    try {
      await validateAnswers(code)
      await loadState()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur validation')
    } finally {
      setValidating(false)
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

      if (!result.duel_continues) {
        // Le duel est terminé (mauvaise réponse ou doublon) : on affiche
        // l'écran de résultat final (PingPongResults).
        const results = await getPingPongDuelResults(state.active_duel.duel_id)
        setDuelResult({ ...result, final: results })
      } else {
        // Bonne réponse mais le duel continue : ne PAS monter PingPongResults
        // (qui affiche "X remporte le duel !") — seul un message de tour est
        // pertinent ici, la victoire n'est pas encore acquise.
        setFeedbackMessage({ type: 'bonus', text: result.message })
        setTimeout(() => setFeedbackMessage(null), 5000)
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
      await loadState()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors du changement de question')
    }
  }

  const handleUseToken = async (tokenType: TokenType, targetTeamId?: number) => {
    const type = String(tokenType).toUpperCase()

    // Feedback visuel instantané pour l'utilisateur qui a cliqué
    if (type.includes('BONUS') || type.includes('DOUBLE')) {
      setFeedbackMessage({
        type: 'bonus',
        text: `⭐ BONUS ACTIVÉ ! Votre prochaine bonne réponse rapportera x2 points !`
      })
    } else if (type.includes('SWAP')) {
      setFeedbackMessage({
        type: 'swap',
        text: `🔀 SWAP ! Vous avez demandé un changement de question !`
      })
    } else if (type.includes('PENALT') || type.includes('PÉNALIT')) {
      const targetTeam = state?.other_teams.find((t) => t.team_id === targetTeamId)?.team_name || 'l\'équipe adverse'
      setFeedbackMessage({
        type: 'penalty',
        text: `⚡ Pénalité appliquée pour ${targetTeam} !`
      })
    }

    setTimeout(() => setFeedbackMessage(null), 5000)

    try {
      await useToken({ team_id: teamIdNum, token_type: tokenType, target_team_id: targetTeamId })
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
          {editingName ? (
            <div className="flex flex-col items-center gap-2 mb-2">
              <div className="flex items-center gap-2">
                <input
                  autoFocus
                  value={nameDraft}
                  onChange={(e) => setNameDraft(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleRenameTeam(); if (e.key === 'Escape') setEditingName(false) }}
                  className="text-lg font-semibold text-text bg-surface-raised border border-border rounded-lg px-3 py-1 text-center"
                  maxLength={40}
                />
                <button onClick={handleRenameTeam} className="btn-primary min-h-[36px] px-3">OK</button>
                <button onClick={() => { setEditingName(false); setRenameError('') }} className="btn-secondary min-h-[36px] px-3">Annuler</button>
              </div>
              {renameError && <p className="text-danger text-sm">{renameError}</p>}
            </div>
          ) : (
            <p className="text-text-muted">
              Vous avez rejoint{' '}
              <span
                className="text-brand font-semibold cursor-pointer"
                onClick={() => { setNameDraft(state.team_name); setRenameError(''); setEditingName(true) }}
                title="Renommer l'equipe"
              >
                {state.team_name} ✏️
              </span>
              .
              En attente que l'hôte lance la partie...
            </p>
          )}
        </div>
      </div>
    )
  }

  const showRanking = state.other_teams.length > 0
  const showLeftColumn = showRanking || wheelHistory.length > 0

  return (
    <div className="min-h-screen p-4">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-6">
          {editingName ? (
            <div className="flex flex-col items-center gap-2">
              <div className="flex items-center gap-2">
                <input
                  autoFocus
                  value={nameDraft}
                  onChange={(e) => setNameDraft(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleRenameTeam(); if (e.key === 'Escape') setEditingName(false) }}
                  className="text-2xl font-bold text-text bg-surface-raised border border-border rounded-lg px-3 py-1 text-center"
                  maxLength={40}
                />
                <button onClick={handleRenameTeam} className="btn-primary min-h-[36px] px-3">OK</button>
                <button onClick={() => { setEditingName(false); setRenameError('') }} className="btn-secondary min-h-[36px] px-3">Annuler</button>
              </div>
              {renameError && <p className="text-danger text-sm">{renameError}</p>}
            </div>
          ) : (
            <h1
              className="text-2xl font-bold text-text cursor-pointer inline-flex items-center gap-2"
              onClick={() => { setNameDraft(state.team_name); setRenameError(''); setEditingName(true) }}
              title="Renommer l'equipe"
            >
              {state.team_name}
              <span className="text-sm text-text-muted">✏️</span>
            </h1>
          )}
          <p className="text-text-muted">
            Score : <span className="text-brand font-bold">{state.team_score} pts</span>
            {' • '}
            Manche : <span className="text-text font-semibold">{state.game_phase}</span>
          </p>
        </div>

        {feedbackMessage && (
          <div className={`fixed top-4 left-1/2 -translate-x-1/2 z-[70] w-[calc(100%-2rem)] max-w-xl p-4 rounded-xl text-white font-bold text-center shadow-2xl transition-all border-2 ${
            feedbackMessage.type === 'swap' ? 'bg-blue-600 border-blue-400' :
            feedbackMessage.type === 'penalty' ? 'bg-red-600 border-red-400' : 'bg-amber-500 border-amber-300 text-bg'
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

        <div className={showLeftColumn ? 'grid grid-cols-1 lg:grid-cols-3 gap-6' : 'max-w-3xl mx-auto space-y-6'}>
          {showLeftColumn && (
          <div className="lg:col-span-1 space-y-6">
            {/* Classement affiché en permanence dans la colonne latérale,
                y compris pendant une question/duel — feedback playtest
                du 2026-08-12 : le retirer pendant la Manche 1 privait les
                équipes de l'info de classement trop longtemps. */}
            {showRanking && (
              <div className="card">
                <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wide mb-3">
                  📊 Classement
                </h3>
                <div className="space-y-2">
                  {[
                    { team_id: state.team_id, team_name: state.team_name, team_score: state.team_score, has_answered: state.has_answered, isSelf: true },
                    ...state.other_teams.map((t) => ({ ...t, isSelf: false })),
                  ]
                    .sort((a, b) => b.team_score - a.team_score)
                    .map((team, rank) => (
                      <div
                        key={team.team_id}
                        className={`flex items-center justify-between p-2 rounded-lg ${team.isSelf ? 'bg-brand-muted/20 border border-brand' : 'bg-surface-raised'}`}
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-text-muted w-5">{rank + 1}.</span>
                          <span className="text-sm font-medium">
                            {team.team_name}{team.isSelf ? ' (vous)' : ''}
                          </span>
                          <span className={`text-xs ${team.has_answered ? 'text-success' : 'text-text-muted'}`}>
                            {team.has_answered ? '✓' : '⏳'}
                          </span>
                        </div>
                        <span className="font-bold text-brand">{team.team_score} pts</span>
                      </div>
                    ))}
                </div>
              </div>
            )}

            <WheelHistory history={wheelHistory} />
          </div>
          )}

          <div className={showLeftColumn ? 'lg:col-span-2 space-y-6' : 'space-y-6'}>

        {choosingPingPongOpponent && !state.active_duel && (
          <PingPongTeamSelector
            currentTeam={{
              id: state.team_id,
              name: state.team_name,
              game_session_id: state.game_session_id,
              score: state.team_score,
              players: [],
            }}
            availableTeams={state.other_teams.map((t) => ({
              id: t.team_id,
              name: t.team_name,
              game_session_id: state.game_session_id,
              score: t.team_score,
              players: [],
            }))}
            onSelect={handleChooseWheelPingPongOpponent}
            onCancel={() => setChoosingPingPongOpponent(false)}
          />
        )}

        {state.current_question && state.other_teams.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            {[
              { team_id: state.team_id, team_name: state.team_name, has_answered: state.has_answered, isSelf: true },
              ...state.other_teams.map((t) => ({ ...t, isSelf: false })),
            ].map((team) => (
              <span
                key={team.team_id}
                className={`text-xs px-2 py-1 rounded-full border ${team.has_answered ? 'text-success border-success' : 'text-text-muted border-border'}`}
              >
                {team.has_answered ? '✓' : '⏳'} {team.team_name}{team.isSelf ? ' (vous)' : ''}
              </span>
            ))}
          </div>
        )}

        {/* Question courante — le formulaire reste modifiable par n'importe quel
            coéquipier tant que l'host n'a pas validé (BUG-110) */}
        {state.current_question && !state.current_question.answer_locked && (
          <div className="card">
            {state.current_question.image_url && (
              <img
                src={state.current_question.image_url}
                alt="Illustration de la question"
                className="max-h-64 mx-auto rounded-lg mb-3 object-contain"
              />
            )}
            <h3 className="text-lg font-semibold mb-3">
              {state.current_question.text}
            </h3>
            <p className="text-xs text-text-muted mb-4">
              {state.current_question.category} • {state.current_question.points} pts
            </p>
            {state.current_question.current_team_answer && (
              <p className="text-xs text-brand mb-3">
                Réponse actuelle de l'équipe : <span className="font-semibold">{state.current_question.current_team_answer}</span> — modifiable jusqu'à validation
              </p>
            )}

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

            {isHost && (
              <div className="mt-4 pt-4 border-t border-border">
                <p className="text-xs text-text-muted mb-2">
                  Vous êtes l'hôte de cette partie — cette action verrouille définitivement les réponses de toutes les équipes et distribue les points.
                </p>
                <button
                  onClick={() => setShowValidateConfirm(true)}
                  disabled={validating}
                  className="btn-primary w-full disabled:opacity-50"
                >
                  {validating ? 'Validation...' : "Valider définitivement (hôte)"}
                </button>
              </div>
            )}
          </div>
        )}

        {showValidateConfirm && (
          <ConfirmModal
            title="Valider définitivement les réponses ?"
            message="Cette action verrouille les réponses de toutes les équipes et distribue les points. Elle est irréversible."
            confirmLabel="Valider définitivement"
            onConfirm={() => {
              setShowValidateConfirm(false)
              handleValidateAnswers()
            }}
            onCancel={() => setShowValidateConfirm(false)}
          />
        )}

        {state.validation_result && (
          <div className="card border-success">
            <h3 className="text-lg font-bold text-success mb-3">✅ Réponses validées !</h3>
            <p className="text-sm text-text-muted mb-2">
              Réponse correcte : <span className="text-text font-semibold">{state.validation_result.correct_answer}</span>
            </p>
            <div className="space-y-1 mb-4">
              {state.validation_result.teams.map((t, idx) => (
                <div key={idx} className="flex justify-between items-baseline text-sm gap-2">
                  <span className="flex-1">
                    {t.team_name}
                    {t.player_answer && (
                      <span className="text-text-muted italic"> — « {t.player_answer} »</span>
                    )}
                  </span>
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

        {/* Réponse validée par l'host — verrouillée */}
        {state.current_question?.answer_locked && !state.validation_result && (
          <div className="card text-center py-8 border-brand">
            <div className="text-6xl mb-4">📤</div>
            <p className="text-xl text-brand font-semibold">
              Réponse validée !
            </p>
            {state.current_question.correct_answer !== null && state.current_question.current_team_answer !== null && (
              (() => {
                const isCorrect = state.current_question.current_team_answer!.trim().toLowerCase()
                  === state.current_question.correct_answer!.trim().toLowerCase()
                return (
                  <p className={`text-sm mt-2 ${isCorrect ? 'text-success' : 'text-danger'}`}>
                    {isCorrect ? '✅ Bonne réponse !' : '❌ Mauvaise réponse'}
                  </p>
                )
              })()
            )}
            <p className="text-sm text-text-muted mt-2">
              ⏳ En attente des autres équipes...
            </p>
          </div>
        )}

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
                timeRemaining={duelTimeRemaining}
                turnDurationSeconds={PING_PONG_TURN_DURATION_SECONDS}
              />
            )}
          </div>
        )}

        {/* Duel Ping-Pong d'une autre équipe — vue spectateur en lecture
            seule (BUG-104 / Story J.001). Ne s'affiche que si cette équipe
            n'a pas elle-même de duel actif (spectator_duel est alors null
            côté backend). */}
        {!state.active_duel && state.spectator_duel && (
          <div className="card">
            {state.spectator_duel.is_completed ? (
              <div className="text-center py-6">
                <div className="text-4xl mb-3">🏓</div>
                <h3 className="text-lg font-semibold text-text mb-2">
                  {state.spectator_duel.is_cancelled ? 'Duel annulé' : 'Duel terminé'}
                </h3>
                <p className="text-text-muted">
                  {state.spectator_duel.is_cancelled
                    ? `Le duel ${state.spectator_duel.team1.name} vs ${state.spectator_duel.team2.name} a été annulé par l'hôte`
                    : `${
                        state.spectator_duel.winner_team_id === state.spectator_duel.team1.id
                          ? state.spectator_duel.team1.name
                          : state.spectator_duel.winner_team_id === state.spectator_duel.team2.id
                          ? state.spectator_duel.team2.name
                          : 'Aucune équipe'
                      } remporte le duel ${state.spectator_duel.team1.name} vs ${state.spectator_duel.team2.name}`}
                </p>
              </div>
            ) : (
              <PingPongQuestion
                theme={state.spectator_duel.theme}
                team1={{
                  id: state.spectator_duel.team1.id,
                  name: state.spectator_duel.team1.name,
                  game_session_id: 0,
                  score: 0,
                  players: [],
                }}
                team2={{
                  id: state.spectator_duel.team2.id,
                  name: state.spectator_duel.team2.name,
                  game_session_id: 0,
                  score: 0,
                  players: [],
                }}
                currentTurnTeamId={state.spectator_duel.current_turn_team_id}
                answersUsed={state.spectator_duel.answers_used || []}
                turnNumber={state.spectator_duel.turn_number || 1}
                isCurrentTeam={false}
                onSubmit={() => {}}
                onPass={() => {}}
                disabled={true}
              />
            )}
          </div>
        )}

            {/* Jetons */}
            {state.tokens.length > 0 && (
              <TokenPanel
                tokens={state.tokens}
                otherTeams={state.other_teams.map((t) => ({ team_id: t.team_id, team_name: t.team_name }))}
                onUseToken={handleUseToken}
              />
            )}
          </div>
        </div>

        {error && (
          <div className="fixed bottom-4 right-4 z-[60] bg-danger/90 text-text px-4 py-2 rounded-lg text-sm">
            {error}
            <button onClick={() => setError('')} className="ml-2 hover:opacity-70">✕</button>
          </div>
        )}

        {wheelEventToShow && (
          <WheelResultPopup
            key={wheelEventToShow.id}
            result={wheelEventToShow}
            onClose={() => setWheelEventToShow(null)}
          />
        )}
      </div>
    </div>
  )
}

export default TeamScreen
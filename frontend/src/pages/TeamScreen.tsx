import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getTeamState, submitAnswer, useToken, getPingPongDuelState, getPingPongDuelResults, submitPingPongDuelAnswer, nextQuestion, getRandomPingPongTheme, startPingPongDuel } from '../services/api'
import type { TokenType, Team } from '../types'
import PingPongQuestion from '../components/PingPongQuestion'
import PingPongResults from '../components/PingPongResults'
import PingPongTeamSelector from '../components/PingPongTeamSelector'
import TokenPanel from '../components/TokenPanel'

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
    teams: { team_name: string; is_correct: boolean; points_earned: number }[]
  } | null
  last_wheel_event: {
    id: number
    effect_type: string
    value: number | null
    target_team_id: number
    target_team_name: string
    message: string
  } | null
  last_token_event: {
    id: number
    token_type: string
    using_team_id: number
    using_team_name: string
    target_team_id: number | null
    target_team_name: string | null
    message: string
  } | null
}

function TeamScreen() {
  const { code, teamId } = useParams<{ code: string; teamId: string }>()
  const navigate = useNavigate()
  const teamIdNum = Number(teamId)

  const [state, setState] = useState<TeamStateData | null>(null)
  const [answer, setAnswer] = useState('')
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

  // La roue de fortune (tous les 5 tours) est déclenchée côté serveur et
  // diffusée à tous les écrans via last_wheel_event — on affiche un modal la
  // première fois qu'un nouvel id apparaît, sur CHAQUE appareil (pas
  // seulement celui qui a cliqué sur "Tour suivant").
  const [wheelEventToShow, setWheelEventToShow] = useState<TeamStateData['last_wheel_event']>(null)
  // Quand l'effet de roue est "ping_pong" et que c'est NOTRE équipe qui est
  // tombée dessus, on doit choisir l'adversaire nous-même (au lieu d'un
  // tirage au sort côté serveur) — voir PingPongTeamSelector plus bas.
  const [choosingPingPongOpponent, setChoosingPingPongOpponent] = useState(false)
  const seenWheelEventIdRef = useRef<number | null>(null)
  const wheelEventBaselineSetRef = useRef(false)

  useEffect(() => {
    const event = state?.last_wheel_event
    if (!wheelEventBaselineSetRef.current) {
      // Au premier chargement, on ne montre pas un événement déjà passé
      // (ex. reconnexion en cours de partie) — seuls les nouveaux comptent.
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

  // BUG-102 : un SWAP/PENALTY/BONUS n'avait aucun retour visuel — même
  // pattern de détection que la roue ci-dessus (baseline au premier
  // chargement pour ne pas rejouer un ancien événement à la reconnexion),
  // mais rendu en toast léger plutôt qu'en modal bloquant : ces effets sont
  // plus fréquents qu'un tour de roue et ne doivent pas interrompre le jeu.
  const [tokenEventToShow, setTokenEventToShow] = useState<TeamStateData['last_token_event']>(null)
  const seenTokenEventIdRef = useRef<number | null>(null)
  const tokenEventBaselineSetRef = useRef(false)
  const tokenEventTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const event = state?.last_token_event
    if (!tokenEventBaselineSetRef.current) {
      tokenEventBaselineSetRef.current = true
      seenTokenEventIdRef.current = event ? event.id : null
      return
    }
    if (event && event.id !== seenTokenEventIdRef.current) {
      seenTokenEventIdRef.current = event.id
      setTokenEventToShow(event)
      if (tokenEventTimerRef.current) clearTimeout(tokenEventTimerRef.current)
      tokenEventTimerRef.current = setTimeout(() => setTokenEventToShow(null), 5000)
    }
  }, [state?.last_token_event])

  useEffect(() => {
    return () => {
      if (tokenEventTimerRef.current) clearTimeout(tokenEventTimerRef.current)
    }
  }, [])

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
      await loadState()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors du changement de question')
    }
  }

  const handleUseToken = async (tokenType: TokenType, targetTeamId?: number) => {
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

        {/* Roue : choix de l'adversaire du duel ping-pong */}
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

        {/* Question courante — le formulaire reste modifiable par n'importe quel
            coéquipier tant que l'host n'a pas validé (BUG-110) */}
        {state.current_question && !state.current_question.answer_locked && (
          <div className="card">
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

        {/* Duel Ping-Pong d'une autre équipe — vue spectateur en lecture
            seule (BUG-104 / Story J.001). Ne s'affiche que si cette équipe
            n'a pas elle-même de duel actif (spectator_duel est alors null
            côté backend). */}
        {!state.active_duel && state.spectator_duel && (
          <div className="card">
            {state.spectator_duel.is_completed ? (
              <div className="text-center py-6">
                <div className="text-4xl mb-3">🏓</div>
                <h3 className="text-lg font-semibold text-text mb-2">Duel terminé</h3>
                <p className="text-text-muted">
                  {state.spectator_duel.winner_team_id === state.spectator_duel.team1.id
                    ? state.spectator_duel.team1.name
                    : state.spectator_duel.winner_team_id === state.spectator_duel.team2.id
                    ? state.spectator_duel.team2.name
                    : 'Aucune équipe'}{' '}
                  remporte le duel {state.spectator_duel.team1.name} vs {state.spectator_duel.team2.name}
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

        {/* Erreur */}
        {error && (
          <div className="fixed bottom-4 right-4 z-[60] bg-danger/90 text-text px-4 py-2 rounded-lg text-sm">
            {error}
            <button onClick={() => setError('')} className="ml-2 hover:opacity-70">✕</button>
          </div>
        )}

        {/* Effet de jeton (SWAP/PENALTY/BONUS) — toast léger auto-masqué */}
        {tokenEventToShow && (
          <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 px-4 w-full max-w-md animate-fade-in">
            <div className="card flex items-center justify-between gap-3 shadow-lg">
              <p className="text-sm text-text">{tokenEventToShow.message}</p>
              <button
                onClick={() => setTokenEventToShow(null)}
                className="text-text-muted hover:opacity-70 shrink-0"
              >
                ✕
              </button>
            </div>
          </div>
        )}

        {/* Roue de fortune (tous les 5 tours) */}
        {wheelEventToShow && (
          <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
            <div className="card max-w-sm w-full text-center">
              <div className="text-4xl mb-3">🎡</div>
              <h3 className="text-lg font-semibold text-text mb-2">Roue de fortune !</h3>
              <p className="text-sm text-text-muted mb-6">{wheelEventToShow.message}</p>
              <button
                onClick={() => setWheelEventToShow(null)}
                className="btn-primary w-full min-h-[44px]"
              >
                Continuer →
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default TeamScreen
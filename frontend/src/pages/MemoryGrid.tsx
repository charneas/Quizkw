import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  getGame,
  createMemoryGrid,
  startMemoryGridRound,
  getMemoryGridState,
  getMemoryGridStandings,
  getCurrentPlayerTurn,
  revealCell,
  answerCell,
  advanceToPhase3,
  skipTurn,
} from '../services/api'
import type { GameSession, MemoryGridState, GridCell } from '../types'

// C-003 AC2 : durée de tour, alignée sur le pattern déjà utilisé en Manche 2.
const TURN_DURATION_SECONDS = 30
// C-003 AC4 : synchronisation par polling (décision d'architecture du 2026-07-24,
// cf. epics-and-stories.md § C-003 AC4 — pas de WebSocket).
const POLL_INTERVAL_MS = 2000

// AD-0 : la Manche 3 est INDIVIDUELLE — 4 finalistes, pas des équipes.
// Chaque finaliste porte une couleur, dans l'ordre du classement de Manche 2.
const FINALIST_COLORS = [
  { bg: 'bg-blue-600/40', border: 'border-blue-400', text: 'text-blue-300' },
  { bg: 'bg-red-600/40', border: 'border-red-400', text: 'text-red-300' },
  { bg: 'bg-green-600/40', border: 'border-green-400', text: 'text-green-300' },
  { bg: 'bg-yellow-600/40', border: 'border-yellow-400', text: 'text-yellow-300' },
]

// 35 cellules fixes (grille 7x5, cf. create_memory_grid(rows=7, cols=5)).
const TOTAL_GRID_CELLS = 35

interface Standing {
  player_id: number
  player_name: string
  total_score: number
  // C-004 : déjà renvoyées par GET /memory-grid/{id}/winner, ignorées jusqu'ici.
  stolen_cells: number
  own_theme_cells: number
  unassigned_cells: number
}

function MemoryGrid() {
  const { code } = useParams<{ code: string }>()
  const navigate = useNavigate()

  const [game, setGame] = useState<GameSession | null>(null)
  const [gridState, setGridState] = useState<MemoryGridState | null>(null)
  const [gridId, setGridId] = useState<number | null>(null)
  const [roundId, setRoundId] = useState<number | null>(null)
  const [standings, setStandings] = useState<Standing[]>([])
  // AD-8 : le serveur possède l'ordre des tours — pas de compteur local.
  const [currentPlayerId, setCurrentPlayerId] = useState<number | null>(null)
  // C-003 : le tour observé, transmis à skip-turn pour un compare-and-set
  // (chaque client connecté fait tourner son propre timer et pourrait sinon
  // appeler skip-turn plusieurs fois pour le même timeout).
  const [currentTurn, setCurrentTurn] = useState<number | null>(null)
  const [selectedCell, setSelectedCell] = useState<GridCell | null>(null)
  const [answerText, setAnswerText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [answerFeedback, setAnswerFeedback] = useState<{
    points: number
    cellType: string
    isCorrect: boolean
    correctAnswer: string
  } | null>(null)
  const [loading, setLoading] = useState(true)
  const [initStep, setInitStep] = useState('')
  const [error, setError] = useState('')
  const [timeRemaining, setTimeRemaining] = useState<number | null>(null)
  // C-004 : effet visuel transitoire sur la cellule qui vient d'être jouée,
  // en plus de la modale de feedback existante. S'efface tout seul — ne doit
  // pas être dérivé de gridState pour ne pas se redéclencher à chaque poll.
  const [lastCaptured, setLastCaptured] = useState<{ cellId: number; isCorrect: boolean } | null>(null)
  // Évite qu'un timeout d'effacement périmé (capture précédente) n'efface la
  // capture suivante si deux réponses arrivent à moins de 1200ms d'intervalle.
  const lastCapturedCellRef = useRef<number | null>(null)
  // Le polling (2s) et les rafraîchissements déclenchés par une action peuvent
  // se chevaucher ; une réponse réseau en retard ne doit jamais écraser un
  // état plus récent déjà affiché — on ne garde que la réponse la plus récente émise.
  const refreshSeq = useRef(0)
  // React.StrictMode double-invoque les effets au montage en dev : sans ce
  // garde, initGrid() partirait deux fois en parallèle et créerait deux
  // grilles concurrentes (la vérification d'idempotence côté backend est
  // sujette à une course entre deux requêtes quasi simultanées).
  const initStarted = useRef(false)

  const totalCells = gridState?.cells.length || 0
  const matchedCells = gridState?.cells.filter((c) => c.status === 'matched').length || 0
  const progress = totalCells > 0 ? Math.round((matchedCells / totalCells) * 100) : 0
  const isCompleted = gridState?.memory_grid.is_completed || progress === 100

  useEffect(() => {
    if (code && !initStarted.current) {
      initStarted.current = true
      initGrid()
    }
  }, [code])

  // C-003 AC4 : polling 2s pour que tous les finalistes voient converger
  // l'état de la grille sans action manuelle. S'arrête une fois la partie
  // terminée (plus rien à synchroniser, écran de résultats affiché).
  useEffect(() => {
    if (!gridId || isCompleted) return
    const interval = setInterval(refreshState, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [gridId, isCompleted])

  // C-003 AC2/AC3 : le timer redémarre à chaque changement de joueur courant.
  useEffect(() => {
    if (currentPlayerId === null || isCompleted) {
      setTimeRemaining(null)
      return
    }
    setTimeRemaining(TURN_DURATION_SECONDS)
  }, [currentPlayerId])

  // C-003 AC4 : décompte du timer, un skip-turn déclenché une seule fois à 0.
  useEffect(() => {
    if (timeRemaining === null) return
    if (timeRemaining <= 0) {
      if (gridId && currentTurn !== null) {
        skipTurn(gridId, currentTurn)
          .then(refreshState)
          .catch(() => {
            // Échec réseau : le prochain poll resynchronisera l'état, mais on
            // retente une fois tout de suite pour ne pas rester bloqué à 0
            // jusqu'au prochain cycle de polling (jusqu'à 2s).
            setTimeout(() => {
              skipTurn(gridId, currentTurn).then(refreshState).catch(() => {
                setError("Impossible de passer le tour, nouvelle tentative au prochain rafraîchissement.")
              })
            }, 500)
          })
      }
      return
    }

    const timer = setTimeout(() => setTimeRemaining((prev) => (prev !== null ? prev - 1 : null)), 1000)
    return () => clearTimeout(timer)
  }, [timeRemaining, gridId])

  // Couleur d'un finaliste, d'après son rang au classement
  const colorFor = (playerId: number | null) => {
    if (playerId === null) return null
    const index = standings.findIndex((s) => s.player_id === playerId)
    if (index === -1) return null
    return FINALIST_COLORS[index % FINALIST_COLORS.length]
  }

  const nameFor = (playerId: number | null) =>
    standings.find((s) => s.player_id === playerId)?.player_name ?? `Joueur ${playerId}`

  // Repère daltonisme (deutéranopie) : initiale du finaliste, en plus de la couleur.
  // [...name] (pas charAt) pour ne pas découper un caractère hors du plan de base (emoji).
  const initialFor = (name: string) => ([...name.trim()][0] ?? '?').toUpperCase()

  const initGrid = async () => {
    try {
      setInitStep('Chargement du jeu...')
      const gameData = await getGame(code!)
      setGame(gameData)

      if (gameData.current_round !== 'manche_3') {
        setInitStep('Manche 2 terminée — les 4 finalistes accèdent à la Manche 3...')
        await advanceToPhase3(code!)
      }

      setInitStep('Préparation de la grille mémoire 7×5 pour les 4 finalistes...')
      const grid = await createMemoryGrid(code!)
      setGridId(grid.id)

      setInitStep('Chargement des cellules...')
      setGridState(await getMemoryGridState(grid.id))

      setInitStep('Démarrage du tournoi final...')
      const round = await startMemoryGridRound(code!)
      setRoundId(round.round_id)

      setInitStep('Détermination du premier tour...')
      await refreshPlayers(grid.id)

      setInitStep('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur initialisation grille')
    } finally {
      setLoading(false)
    }
  }

  const refreshPlayers = async (id: number) => {
    const [board, turn] = await Promise.all([
      getMemoryGridStandings(id),
      getCurrentPlayerTurn(id),
    ])
    setStandings(board.player_scores)
    setCurrentPlayerId(turn.current_player_id)
    setCurrentTurn(turn.current_turn)
  }

  const refreshState = async () => {
    if (!gridId) return
    // Chaque requête applique son propre résultat dès qu'il arrive (pas de
    // Promise.all groupé) pour ne pas retarder l'affichage de la grille
    // derrière les requêtes de classement/tour, qui sont moins urgentes.
    // Le garde de séquence évite seulement qu'une réponse issue d'un appel
    // plus ancien n'écrase un état plus récent.
    const seq = ++refreshSeq.current
    try {
      const state = await getMemoryGridState(gridId)
      if (seq === refreshSeq.current) setGridState(state)
    } catch (err) {
      console.error('Erreur refresh (state):', err)
    }
    try {
      const [board, turn] = await Promise.all([
        getMemoryGridStandings(gridId),
        getCurrentPlayerTurn(gridId),
      ])
      if (seq === refreshSeq.current) {
        setStandings(board.player_scores)
        setCurrentPlayerId(turn.current_player_id)
        setCurrentTurn(turn.current_turn)
      }
    } catch (err) {
      console.error('Erreur refresh (joueurs):', err)
    }
  }

  const handleCellClick = async (cell: GridCell) => {
    if (cell.status !== 'hidden' || !roundId || currentPlayerId === null) return

    try {
      await revealCell({
        round_id: roundId,
        player_id: currentPlayerId,
        cell_id: cell.id,
      })

      const updatedState = await getMemoryGridState(gridId!)
      setGridState(updatedState)
      setSelectedCell(updatedState.cells.find((c) => c.id === cell.id) || cell)
      setAnswerText('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur révélation cellule')
    }
  }

  // AD-3 : on soumet la RÉPONSE du joueur ; le serveur seul juge.
  const handleSubmitAnswer = async () => {
    if (!selectedCell || !roundId || currentPlayerId === null || submitting) return

    setSubmitting(true)
    try {
      const result = await answerCell({
        round_id: roundId,
        player_id: currentPlayerId,
        cell_id: selectedCell.id,
        player_answer: answerText,
      })

      setAnswerFeedback({
        points: result.points_awarded,
        cellType: result.cell_type,
        isCorrect: result.is_correct,
        correctAnswer: result.correct_answer,
      })
      // C-004 Scenario 1 : effet visuel sur la cellule elle-même, en plus de
      // la modale de feedback ci-dessus.
      setLastCaptured({ cellId: selectedCell.id, isCorrect: result.is_correct })
      lastCapturedCellRef.current = selectedCell.id

      // On attend que l'état rafraîchi (score, progression) soit appliqué
      // AVANT de fermer la modale de la cellule : sinon le plateau affiché
      // derrière peut brièvement montrer l'ancien score pendant la requête.
      await refreshState()
      setSelectedCell(null)
      setAnswerText('')

      setTimeout(() => setAnswerFeedback(null), 3000)
      const capturedCellId = selectedCell.id
      setTimeout(() => {
        // Ne pas effacer une capture plus récente si une deuxième réponse est
        // arrivée entre-temps (moins de 1200ms d'écart entre deux captures).
        if (lastCapturedCellRef.current === capturedCellId) setLastCaptured(null)
      }, 1200)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur réponse')
    } finally {
      setSubmitting(false)
    }
  }

  const handleEndGame = () => navigate(`/results/${code}`)

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="text-2xl text-text animate-pulse mb-2">🧠 Manche 3</div>
          <p className="text-text-muted">{initStep}</p>
        </div>
      </div>
    )
  }

  if (!game || !gridState) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="card text-center">
          <h2 className="text-2xl text-danger mb-4">Erreur</h2>
          <p className="text-text-muted mb-4">{error}</p>
          <button onClick={() => navigate(`/game/${code}/host`)} className="btn-primary">
            Retour au jeu
          </button>
        </div>
      </div>
    )
  }

  const cols = gridState.memory_grid.cols || gridState.memory_grid.grid_size || 5

  const getCellStyle = (cell: GridCell) => {
    // C-004 Scenario 1 : effet de capture, différencié bonne/mauvaise réponse.
    const captureEffect =
      lastCaptured?.cellId === cell.id
        ? lastCaptured.isCorrect
          ? 'animate-success-pulse'
          : 'animate-error-shake'
        : ''

    if (cell.status === 'matched') {
      const color = colorFor(cell.matched_by_player_id)
      return `${captureEffect} ${
        color
          ? `${color.bg} ${color.border} border-2 cursor-not-allowed`
          : 'bg-success/30 border-2 border-success cursor-not-allowed'
      }`
    }
    if (cell.status === 'revealed') {
      return 'bg-accent/30 border-2 border-accent animate-pulse cursor-not-allowed'
    }
    // BUG-304 : une cellule cachée ne doit rien révéler sur son propriétaire
    // (couleur ou bordure) avant d'être effectivement révélée par un joueur.
    return 'bg-surface-raised hover:bg-brand-muted cursor-pointer hover:scale-105 border-2 border-border'
  }

  const getCellContent = (cell: GridCell) => {
    if (cell.status === 'matched') {
      const name = nameFor(cell.matched_by_player_id)
      return name ? initialFor(name) : '✓'
    }
    if (cell.status === 'revealed') return '❓'
    return '?'
  }

  return (
    <div className="min-h-screen p-4">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold font-display">🧠 Manche 3 — Grille Mémoire</h1>
            <p className="text-text-muted text-sm">
              Code: <span className="font-mono font-bold text-accent">{game.code}</span>
              {' • '}Progression: {matchedCells}/{totalCells} ({progress}%)
              {' • '}4 finalistes
            </p>
          </div>
          <button onClick={handleEndGame} className="btn-danger text-sm">
            Terminer la partie
          </button>
        </div>

        <div className="w-full bg-border rounded-full h-2 mb-6">
          <div
            className="bg-accent h-2 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>

        {isCompleted ? (
          <div className="card text-center py-12">
            <div className="text-6xl mb-2 animate-bounce-once">🏆</div>
            <h2 className="text-4xl font-bold font-display text-accent mb-4 animate-fade-in">Partie terminée !</h2>
            <p className="text-text-muted mb-6">Toutes les cellules ont été découvertes.</p>
            <div className="max-w-lg mx-auto space-y-2">
              {standings.map((s, idx) => {
                const cellsControlled = (s.stolen_cells ?? 0) + (s.own_theme_cells ?? 0) + (s.unassigned_cells ?? 0)
                const controlPercent = Math.round((cellsControlled / TOTAL_GRID_CELLS) * 100)
                return (
                  <div key={s.player_id} className="card py-2 px-4 text-left">
                    <div className="flex justify-between items-center">
                      <span className={FINALIST_COLORS[idx % FINALIST_COLORS.length].text}>
                        {idx === 0 ? '🏆 ' : `${idx + 1}. `}
                        {s.player_name}
                      </span>
                      <span className="font-bold">{s.total_score} pts</span>
                    </div>
                    <p className="text-xs text-text-muted mt-1">
                      {cellsControlled}/{TOTAL_GRID_CELLS} cellules contrôlées ({controlPercent}%)
                      {' — '}
                      {s.own_theme_cells ?? 0} propres, {s.stolen_cells ?? 0} volées, {s.unassigned_cells ?? 0} neutres
                    </p>
                  </div>
                )
              })}
            </div>
            <button onClick={handleEndGame} className="btn-primary mt-6 text-lg px-8 py-3">
              Voir les résultats →
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            <div className="lg:col-span-1 space-y-4">
              {/* Classement des finalistes — AD-1 : score de Manche 3 seul */}
              <div className="card">
                <h3 className="text-sm font-semibold text-text-muted mb-2">Finalistes</h3>
                {standings.map((s, idx) => {
                  const color = FINALIST_COLORS[idx % FINALIST_COLORS.length]
                  const isTurn = s.player_id === currentPlayerId
                  return (
                    <div
                      key={s.player_id}
                      className={`flex items-center justify-between gap-2 text-sm mb-1 px-2 py-1 rounded ${
                        isTurn ? 'bg-accent/20 ring-1 ring-accent' : ''
                      }`}
                    >
                      <span className="flex items-center gap-2">
                        {/* Repère daltonisme (deutéranopie) : initiale en plus de la couleur, cf. EXPERIENCE.md Accessibility Floor */}
                        <div
                          aria-hidden="true"
                          className={`w-6 h-6 rounded flex items-center justify-center text-xs font-bold ${color.bg} border ${color.border} ${color.text}`}
                        >
                          {initialFor(s.player_name)}
                        </div>
                        <span className={color.text}>{s.player_name}</span>
                      </span>
                      <span className="font-bold">{s.total_score}</span>
                    </div>
                  )
                })}
              </div>
            </div>

            <div className="lg:col-span-3 space-y-4">
              <div className="card text-center">
                <p className="text-sm text-text-muted">C'est au tour de</p>
                <p className="text-2xl font-bold text-accent">
                  {nameFor(currentPlayerId)}
                </p>
                <p className="text-xs text-text-muted mt-1">
                  Cliquez sur une cellule cachée pour la révéler
                </p>
                {timeRemaining !== null && (
                  <div className="mt-3">
                    <p className={`text-sm font-bold ${timeRemaining <= 5 ? 'text-danger animate-timer-pulse' : 'text-text'}`}>
                      ⏱ {timeRemaining}s
                    </p>
                    <div className="h-2 bg-border rounded-full overflow-hidden mt-1">
                      <div
                        className={`h-full transition-all duration-1000 ease-linear ${
                          timeRemaining <= 5 ? 'bg-danger' : timeRemaining <= 10 ? 'bg-brand-600' : 'bg-success'
                        }`}
                        style={{ width: `${(timeRemaining / TURN_DURATION_SECONDS) * 100}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>

              {answerFeedback && (
                <div
                  className={`card text-center ${
                    answerFeedback.isCorrect ? 'border-success' : 'border-danger'
                  }`}
                >
                  {answerFeedback.isCorrect ? (
                    <>
                      <span className="text-3xl">✅</span>
                      <p className="text-xl font-bold text-success">
                        +{answerFeedback.points} points !
                      </p>
                      <p className="text-sm text-text-muted">
                        {answerFeedback.cellType === 'own' && '(Cellule propre — bonus +1)'}
                        {answerFeedback.cellType === 'stolen' && '(Cellule volée — bonus +1)'}
                      </p>
                    </>
                  ) : (
                    <>
                      <span className="text-3xl">❌</span>
                      <p className="text-xl font-bold text-danger">Mauvaise réponse</p>
                      <p className="text-sm text-text-muted">
                        Réponse attendue : {answerFeedback.correctAnswer}
                      </p>
                    </>
                  )}
                </div>
              )}

              <div
                className="grid gap-2"
                style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
              >
                {gridState.cells.map((cell) => (
                  <button
                    key={cell.id}
                    onClick={() => handleCellClick(cell)}
                    disabled={cell.status !== 'hidden' || !!selectedCell}
                    className={`
                      aspect-square rounded-lg font-bold text-sm transition-all duration-200
                      ${getCellStyle(cell)}
                      ${cell.status !== 'hidden' || selectedCell ? '' : 'active:scale-95'}
                    `}
                    title={
                      // BUG-303 : ne pas fuiter le propriétaire au survol avant révélation.
                      cell.status === 'matched' && cell.assigned_player_id
                        ? `Cellule de ${nameFor(cell.assigned_player_id)}`
                        : ''
                    }
                  >
                    {getCellContent(cell)}
                  </button>
                ))}
              </div>

              <div className="flex gap-2">
                <button onClick={refreshState} className="btn-secondary text-sm">
                  🔄 Rafraîchir
                </button>
              </div>
            </div>
          </div>
        )}

        {selectedCell && (
          <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
            <div className="card max-w-lg w-full text-center">
              <h3 className="text-xl font-bold mb-2">Cellule révélée !</h3>

              {selectedCell.question ? (
                <div className="mb-4">
                  <p className="text-lg text-text mb-2">{selectedCell.question.text}</p>
                  <p className="text-xs text-text-muted">
                    {selectedCell.question.category} • {selectedCell.question.points} pts
                  </p>
                </div>
              ) : (
                <p className="text-text-muted mb-4">Question chargée...</p>
              )}

              {selectedCell.assigned_player_id && (
                <p className="text-sm text-text-muted mb-4">
                  {selectedCell.assigned_player_id === currentPlayerId
                    ? '🏠 Votre cellule ! (+1 bonus si bonne réponse)'
                    : `⚔️ Cellule de ${nameFor(selectedCell.assigned_player_id)} (+1 bonus si volée)`}
                </p>
              )}

              <p className="text-text-muted mb-2">
                Réponse de{' '}
                <span className="text-accent font-bold">{nameFor(currentPlayerId)}</span>
              </p>
              <input
                type="text"
                value={answerText}
                onChange={(e) => setAnswerText(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSubmitAnswer()}
                placeholder="Saisir la réponse..."
                autoFocus
                className="input-field w-full mb-3 text-center"
              />
              <button
                onClick={handleSubmitAnswer}
                disabled={submitting}
                className="btn-primary w-full text-lg py-3"
              >
                {submitting ? 'Validation...' : 'Valider la réponse'}
              </button>
              <p className="text-xs text-text-muted mt-2">
                La correction est vérifiée par le serveur.
              </p>
            </div>
          </div>
        )}

        {error && (
          <div className="fixed bottom-4 right-4 bg-danger/90 text-bg px-4 py-2 rounded-lg text-sm max-w-md">
            {error}
            <button onClick={() => setError('')} className="ml-2 text-bg/70 hover:text-bg">
              ✕
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default MemoryGrid

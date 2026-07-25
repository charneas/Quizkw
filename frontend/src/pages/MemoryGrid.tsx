import { useState, useEffect } from 'react'
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
} from '../services/api'
import type { GameSession, MemoryGridState, GridCell } from '../types'

// AD-0 : la Manche 3 est INDIVIDUELLE — 4 finalistes, pas des équipes.
// Chaque finaliste porte une couleur, dans l'ordre du classement de Manche 2.
const FINALIST_COLORS = [
  { bg: 'bg-blue-600/40', border: 'border-blue-400', text: 'text-blue-300' },
  { bg: 'bg-red-600/40', border: 'border-red-400', text: 'text-red-300' },
  { bg: 'bg-green-600/40', border: 'border-green-400', text: 'text-green-300' },
  { bg: 'bg-yellow-600/40', border: 'border-yellow-400', text: 'text-yellow-300' },
]

interface Standing {
  player_id: number
  player_name: string
  total_score: number
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

  useEffect(() => {
    if (code) initGrid()
  }, [code])

  // Couleur d'un finaliste, d'après son rang au classement
  const colorFor = (playerId: number | null) => {
    if (playerId === null) return null
    const index = standings.findIndex((s) => s.player_id === playerId)
    if (index === -1) return null
    return FINALIST_COLORS[index % FINALIST_COLORS.length]
  }

  const nameFor = (playerId: number | null) =>
    standings.find((s) => s.player_id === playerId)?.player_name ?? `Joueur ${playerId}`

  const initGrid = async () => {
    try {
      setInitStep('Chargement du jeu...')
      const gameData = await getGame(code!)
      setGame(gameData)

      if (gameData.current_round !== 'manche_3') {
        setInitStep('Passage en Manche 3...')
        await advanceToPhase3(code!)
      }

      setInitStep('Création de la grille mémoire...')
      const grid = await createMemoryGrid(code!)
      setGridId(grid.id)

      setInitStep('Chargement des cellules...')
      setGridState(await getMemoryGridState(grid.id))

      setInitStep('Démarrage du round...')
      const round = await startMemoryGridRound(code!)
      setRoundId(round.round_id)

      setInitStep('Chargement des finalistes...')
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
  }

  const refreshState = async () => {
    if (!gridId) return
    try {
      setGridState(await getMemoryGridState(gridId))
      await refreshPlayers(gridId)
    } catch (err) {
      console.error('Erreur refresh:', err)
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

      setSelectedCell(null)
      setAnswerText('')
      await refreshState()

      setTimeout(() => setAnswerFeedback(null), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur réponse')
    } finally {
      setSubmitting(false)
    }
  }

  const handleEndGame = () => navigate(`/results/${code}`)

  const totalCells = gridState?.cells.length || 0
  const matchedCells = gridState?.cells.filter((c) => c.status === 'matched').length || 0
  const progress = totalCells > 0 ? Math.round((matchedCells / totalCells) * 100) : 0
  const isCompleted = gridState?.memory_grid.is_completed || progress === 100

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="text-2xl text-slate-400 animate-pulse mb-2">🧠 Manche 3</div>
          <p className="text-slate-500">{initStep}</p>
        </div>
      </div>
    )
  }

  if (!game || !gridState) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="card text-center">
          <h2 className="text-2xl text-game-danger mb-4">Erreur</h2>
          <p className="text-slate-400 mb-4">{error}</p>
          <button onClick={() => navigate(`/game/${code}/host`)} className="btn-primary">
            Retour au jeu
          </button>
        </div>
      </div>
    )
  }

  const cols = gridState.memory_grid.cols || gridState.memory_grid.grid_size || 5

  const getCellStyle = (cell: GridCell) => {
    if (cell.status === 'matched') {
      const color = colorFor(cell.matched_by_player_id)
      return color
        ? `${color.bg} ${color.border} border-2 cursor-not-allowed`
        : 'bg-game-success/30 border-2 border-game-success cursor-not-allowed'
    }
    if (cell.status === 'revealed') {
      return 'bg-game-accent/30 border-2 border-game-accent animate-pulse cursor-not-allowed'
    }
    const owner = colorFor(cell.assigned_player_id)
    if (owner) {
      return `bg-primary-700/80 hover:bg-primary-600 cursor-pointer hover:scale-105 border-2 ${owner.border} border-opacity-40`
    }
    return 'bg-primary-700 hover:bg-primary-600 cursor-pointer hover:scale-105 border-2 border-primary-500'
  }

  const getCellContent = (cell: GridCell) => {
    if (cell.status === 'matched') {
      return nameFor(cell.matched_by_player_id).charAt(0) || '✓'
    }
    if (cell.status === 'revealed') return '❓'
    return '?'
  }

  return (
    <div className="min-h-screen p-4">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold">🧠 Manche 3 — Grille Mémoire</h1>
            <p className="text-slate-400 text-sm">
              Code: <span className="font-mono font-bold text-game-accent">{game.code}</span>
              {' • '}Progression: {matchedCells}/{totalCells} ({progress}%)
              {' • '}4 finalistes
            </p>
          </div>
          <button onClick={handleEndGame} className="btn-danger text-sm">
            Terminer la partie
          </button>
        </div>

        <div className="w-full bg-primary-800 rounded-full h-2 mb-6">
          <div
            className="bg-game-accent h-2 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>

        {isCompleted ? (
          <div className="card text-center py-12">
            <h2 className="text-4xl font-bold text-game-accent mb-4">🎉 Partie terminée !</h2>
            <p className="text-slate-400 mb-6">Toutes les cellules ont été découvertes.</p>
            <div className="max-w-sm mx-auto space-y-2">
              {standings.map((s, idx) => (
                <div
                  key={s.player_id}
                  className="flex justify-between items-center card py-2 px-4"
                >
                  <span className={FINALIST_COLORS[idx % FINALIST_COLORS.length].text}>
                    {idx === 0 ? '🏆 ' : `${idx + 1}. `}
                    {s.player_name}
                  </span>
                  <span className="font-bold">{s.total_score} pts</span>
                </div>
              ))}
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
                <h3 className="text-sm font-semibold text-slate-400 mb-2">Finalistes</h3>
                {standings.map((s, idx) => {
                  const color = FINALIST_COLORS[idx % FINALIST_COLORS.length]
                  const isTurn = s.player_id === currentPlayerId
                  return (
                    <div
                      key={s.player_id}
                      className={`flex items-center justify-between gap-2 text-sm mb-1 px-2 py-1 rounded ${
                        isTurn ? 'bg-game-accent/20 ring-1 ring-game-accent' : ''
                      }`}
                    >
                      <span className="flex items-center gap-2">
                        <div className={`w-4 h-4 rounded ${color.bg} border ${color.border}`} />
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
                <p className="text-sm text-slate-400">C'est au tour de</p>
                <p className="text-2xl font-bold text-game-accent">
                  {nameFor(currentPlayerId)}
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  Cliquez sur une cellule cachée pour la révéler
                </p>
              </div>

              {answerFeedback && (
                <div
                  className={`card text-center ${
                    answerFeedback.isCorrect ? 'border-game-success' : 'border-game-danger'
                  }`}
                >
                  {answerFeedback.isCorrect ? (
                    <>
                      <span className="text-3xl">✅</span>
                      <p className="text-xl font-bold text-game-success">
                        +{answerFeedback.points} points !
                      </p>
                      <p className="text-sm text-slate-400">
                        {answerFeedback.cellType === 'own' && '(Cellule propre — bonus +1)'}
                        {answerFeedback.cellType === 'stolen' && '(Cellule volée — bonus +1)'}
                      </p>
                    </>
                  ) : (
                    <>
                      <span className="text-3xl">❌</span>
                      <p className="text-xl font-bold text-game-danger">Mauvaise réponse</p>
                      <p className="text-sm text-slate-400">
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
                      cell.assigned_player_id
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
                  <p className="text-lg text-white mb-2">{selectedCell.question.text}</p>
                  <p className="text-xs text-slate-500">
                    {selectedCell.question.category} • {selectedCell.question.points} pts
                  </p>
                </div>
              ) : (
                <p className="text-slate-400 mb-4">Question chargée...</p>
              )}

              {selectedCell.assigned_player_id && (
                <p className="text-sm text-slate-400 mb-4">
                  {selectedCell.assigned_player_id === currentPlayerId
                    ? '🏠 Votre cellule ! (+1 bonus si bonne réponse)'
                    : `⚔️ Cellule de ${nameFor(selectedCell.assigned_player_id)} (+1 bonus si volée)`}
                </p>
              )}

              <p className="text-slate-400 mb-2">
                Réponse de{' '}
                <span className="text-game-accent font-bold">{nameFor(currentPlayerId)}</span>
              </p>
              <input
                type="text"
                value={answerText}
                onChange={(e) => setAnswerText(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSubmitAnswer()}
                placeholder="Saisir la réponse..."
                autoFocus
                className="input w-full mb-3 text-center"
              />
              <button
                onClick={handleSubmitAnswer}
                disabled={submitting}
                className="btn-primary w-full text-lg py-3"
              >
                {submitting ? 'Validation...' : 'Valider la réponse'}
              </button>
              <p className="text-xs text-slate-500 mt-2">
                La correction est vérifiée par le serveur.
              </p>
            </div>
          </div>
        )}

        {error && (
          <div className="fixed bottom-4 right-4 bg-red-900/90 text-white px-4 py-2 rounded-lg text-sm max-w-md">
            {error}
            <button onClick={() => setError('')} className="ml-2 text-red-300 hover:text-white">
              ✕
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default MemoryGrid

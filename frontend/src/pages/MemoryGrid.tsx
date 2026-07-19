import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getGame, createMemoryGrid, startMemoryGridRound, getMemoryGridState, revealCell, answerCell, advanceToPhase3 } from '../services/api'
import type { GameSession, MemoryGridState, GridCell } from '../types'
import Scoreboard from '../components/Scoreboard'

// Color map for team-assigned cells
const TEAM_COLORS: Record<number, { bg: string; border: string; text: string }> = {}
const DEFAULT_TEAM_COLORS = [
  { bg: 'bg-blue-600/40', border: 'border-blue-400', text: 'text-blue-300' },
  { bg: 'bg-red-600/40', border: 'border-red-400', text: 'text-red-300' },
  { bg: 'bg-green-600/40', border: 'border-green-400', text: 'text-green-300' },
  { bg: 'bg-yellow-600/40', border: 'border-yellow-400', text: 'text-yellow-300' },
  { bg: 'bg-purple-600/40', border: 'border-purple-400', text: 'text-purple-300' },
  { bg: 'bg-pink-600/40', border: 'border-pink-400', text: 'text-pink-300' },
]

function MemoryGrid() {
  const { code } = useParams<{ code: string }>()
  const navigate = useNavigate()

  const [game, setGame] = useState<GameSession | null>(null)
  const [gridState, setGridState] = useState<MemoryGridState | null>(null)
  const [gridId, setGridId] = useState<number | null>(null)
  const [roundId, setRoundId] = useState<number | null>(null)
  const [currentTeamIndex, setCurrentTeamIndex] = useState(0)
  const [selectedCell, setSelectedCell] = useState<GridCell | null>(null)
  const [answerFeedback, setAnswerFeedback] = useState<{ points: number; cellType: string } | null>(null)
  const [loading, setLoading] = useState(true)
  const [initStep, setInitStep] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (code) initGrid()
  }, [code])

  // Build team color map when game loads
  useEffect(() => {
    if (game) {
      game.teams.forEach((team, idx) => {
        TEAM_COLORS[team.id] = DEFAULT_TEAM_COLORS[idx % DEFAULT_TEAM_COLORS.length]
      })
    }
  }, [game])

  const initGrid = async () => {
    try {
      setInitStep('Chargement du jeu...')
      const gameData = await getGame(code!)
      setGame(gameData)

      // Advance to phase 3 if not already there
      if (gameData.current_round !== 'manche_3') {
        setInitStep('Passage en Manche 3...')
        await advanceToPhase3(code!)
      }

      // Create the memory grid
      setInitStep('Création de la grille mémoire...')
      const grid = await createMemoryGrid(code!)
      setGridId(grid.id)

      // Fetch the full grid state with cells
      setInitStep('Chargement des cellules...')
      const state = await getMemoryGridState(grid.id)
      setGridState(state)

      // Start the round
      setInitStep('Démarrage du round...')
      const round = await startMemoryGridRound(code!)
      setRoundId(round.round_id)

      setInitStep('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur initialisation grille')
    } finally {
      setLoading(false)
    }
  }

  const refreshState = async () => {
    if (!gridId) return
    try {
      const state = await getMemoryGridState(gridId)
      setGridState(state)
      const gameData = await getGame(code!)
      setGame(gameData)
    } catch (err) {
      console.error('Erreur refresh:', err)
    }
  }

  const handleCellClick = async (cell: GridCell) => {
    if (cell.status !== 'hidden' || !roundId || !game) return

    const currentTeam = game.teams[currentTeamIndex]

    try {
      await revealCell({
        round_id: roundId,
        team_id: currentTeam.id,
        cell_id: cell.id,
      })

      // Refresh to get question text
      await refreshState()

      // Find the updated cell with question data
      const updatedState = await getMemoryGridState(gridId!)
      const updatedCell = updatedState.cells.find(c => c.id === cell.id)
      setGridState(updatedState)
      setSelectedCell(updatedCell || cell)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur révélation cellule')
    }
  }

  const handleAnswerCell = async (isCorrect: boolean) => {
    if (!selectedCell || !roundId || !game) return

    const currentTeam = game.teams[currentTeamIndex]

    try {
      const result = await answerCell({
        round_id: roundId,
        team_id: currentTeam.id,
        cell_id: selectedCell.id,
        is_correct: isCorrect,
      })

      // Show feedback
      setAnswerFeedback({
        points: result.points_awarded || 0,
        cellType: (result as any).cell_type || 'unassigned',
      })

      setSelectedCell(null)
      await refreshState()

      // Auto-hide feedback after 2s and advance turn
      setTimeout(() => {
        setAnswerFeedback(null)
        if (game) {
          setCurrentTeamIndex((prev) => (prev + 1) % game.teams.length)
        }
      }, 2000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur réponse')
    }
  }

  const handleSkipTurn = () => {
    if (!game) return
    setCurrentTeamIndex((prev) => (prev + 1) % game.teams.length)
  }

  const handleEndGame = () => {
    navigate(`/results/${code}`)
  }

  // Compute grid stats
  const totalCells = gridState?.cells.length || 0
  const matchedCells = gridState?.cells.filter(c => c.status === 'matched').length || 0
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

  const currentTeam = game.teams[currentTeamIndex]
  const cols = gridState.memory_grid.cols || gridState.memory_grid.grid_size || 5

  const getCellStyle = (cell: GridCell) => {
    if (cell.status === 'matched') {
      // Answered cell — color of the team that answered it
      const teamColor = cell.matched_by_team_id ? TEAM_COLORS[cell.matched_by_team_id] : null
      if (teamColor) {
        return `${teamColor.bg} ${teamColor.border} border-2 cursor-not-allowed`
      }
      return 'bg-game-success/30 border-2 border-game-success cursor-not-allowed'
    }
    if (cell.status === 'revealed') {
      return 'bg-game-accent/30 border-2 border-game-accent animate-pulse cursor-not-allowed'
    }
    // Hidden cell
    if (cell.assigned_team_id) {
      // Team-assigned cell (show subtle team color hint)
      const teamColor = TEAM_COLORS[cell.assigned_team_id]
      if (teamColor) {
        return `bg-primary-700/80 hover:bg-primary-600 cursor-pointer hover:scale-105 border-2 ${teamColor.border} border-opacity-40`
      }
    }
    return 'bg-primary-700 hover:bg-primary-600 cursor-pointer hover:scale-105 border-2 border-primary-500'
  }

  const getCellContent = (cell: GridCell) => {
    if (cell.status === 'matched') {
      const team = game.teams.find(t => t.id === cell.matched_by_team_id)
      return team ? team.name.charAt(0) : '✓'
    }
    if (cell.status === 'revealed') return '❓'
    return '?'
  }

  return (
    <div className="min-h-screen p-4">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold">🧠 Manche 3 — Grille Mémoire</h1>
            <p className="text-slate-400 text-sm">
              Code: <span className="font-mono font-bold text-game-accent">{game.code}</span>
              {' • '}Progression: {matchedCells}/{totalCells} ({progress}%)
            </p>
          </div>
          <button onClick={handleEndGame} className="btn-danger text-sm">
            Terminer la partie
          </button>
        </div>

        {/* Progress bar */}
        <div className="w-full bg-primary-800 rounded-full h-2 mb-6">
          <div
            className="bg-game-accent h-2 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>

        {isCompleted ? (
          /* Game Over */
          <div className="card text-center py-12">
            <h2 className="text-4xl font-bold text-game-accent mb-4">🎉 Partie terminée !</h2>
            <p className="text-slate-400 mb-6">Toutes les cellules ont été découvertes.</p>
            <Scoreboard teams={game.teams} currentTeamIndex={-1} />
            <button onClick={handleEndGame} className="btn-primary mt-6 text-lg px-8 py-3">
              Voir les résultats →
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            {/* Scoreboard */}
            <div className="lg:col-span-1 space-y-4">
              <Scoreboard teams={game.teams} currentTeamIndex={currentTeamIndex} />

              {/* Team legend */}
              <div className="card">
                <h3 className="text-sm font-semibold text-slate-400 mb-2">Légende couleurs</h3>
                {game.teams.map((team, idx) => {
                  const color = DEFAULT_TEAM_COLORS[idx % DEFAULT_TEAM_COLORS.length]
                  return (
                    <div key={team.id} className="flex items-center gap-2 text-sm mb-1">
                      <div className={`w-4 h-4 rounded ${color.bg} border ${color.border}`} />
                      <span className={color.text}>{team.name}</span>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Main area */}
            <div className="lg:col-span-3 space-y-4">
              {/* Current team indicator */}
              <div className="card text-center">
                <p className="text-sm text-slate-400">C'est au tour de</p>
                <p className="text-2xl font-bold text-game-accent">{currentTeam.name}</p>
                <p className="text-xs text-slate-500 mt-1">
                  Cliquez sur une cellule cachée pour la révéler
                </p>
              </div>

              {/* Answer feedback */}
              {answerFeedback && (
                <div className={`card text-center ${answerFeedback.points > 0 ? 'border-game-success' : 'border-game-danger'}`}>
                  {answerFeedback.points > 0 ? (
                    <>
                      <span className="text-3xl">✅</span>
                      <p className="text-xl font-bold text-game-success">+{answerFeedback.points} points !</p>
                      <p className="text-sm text-slate-400">
                        {answerFeedback.cellType === 'own' && '(Cellule propre — bonus +1)'}
                        {answerFeedback.cellType === 'stolen' && '(Cellule volée — bonus +1)'}
                      </p>
                    </>
                  ) : (
                    <>
                      <span className="text-3xl">❌</span>
                      <p className="text-xl font-bold text-game-danger">Mauvaise réponse</p>
                    </>
                  )}
                </div>
              )}

              {/* Grid */}
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
                    title={cell.assigned_team_id ? `Cellule de ${game.teams.find(t => t.id === cell.assigned_team_id)?.name}` : ''}
                  >
                    {getCellContent(cell)}
                  </button>
                ))}
              </div>

              {/* Quick controls */}
              <div className="flex gap-2">
                <button onClick={handleSkipTurn} className="btn-secondary flex-1 text-sm">
                  Passer le tour →
                </button>
                <button onClick={refreshState} className="btn-secondary text-sm">
                  🔄 Rafraîchir
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Cell reveal popup */}
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

              {selectedCell.assigned_team_id && (
                <p className="text-sm text-slate-400 mb-4">
                  {selectedCell.assigned_team_id === currentTeam.id
                    ? '🏠 C\'est votre cellule ! (+1 bonus si bonne réponse)'
                    : `⚔️ Cellule de ${game.teams.find(t => t.id === selectedCell.assigned_team_id)?.name} (+1 bonus si volée)`
                  }
                </p>
              )}

              <p className="text-slate-400 mb-4">
                L'équipe <span className="text-game-accent font-bold">{currentTeam.name}</span> a-t-elle répondu correctement ?
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => handleAnswerCell(false)}
                  className="btn-danger flex-1 text-lg py-3"
                >
                  ❌ Non
                </button>
                <button
                  onClick={() => handleAnswerCell(true)}
                  className="btn-success flex-1 text-lg py-3"
                >
                  ✅ Oui
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Error toast */}
        {error && (
          <div className="fixed bottom-4 right-4 bg-red-900/90 text-white px-4 py-2 rounded-lg text-sm max-w-md">
            {error}
            <button onClick={() => setError('')} className="ml-2 text-red-300 hover:text-white">✕</button>
          </div>
        )}
      </div>
    </div>
  )
}

export default MemoryGrid

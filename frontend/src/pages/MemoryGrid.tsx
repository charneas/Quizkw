import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getGame, createMemoryGrid, startMemoryGridRound, getMemoryGridState, revealCell, answerCell } from '../services/api'
import type { GameSession, MemoryGridState, GridCell } from '../types'
import Scoreboard from '../components/Scoreboard'

function MemoryGrid() {
  const { code } = useParams<{ code: string }>()
  const navigate = useNavigate()
  
  const [game, setGame] = useState<GameSession | null>(null)
  const [gridState, setGridState] = useState<MemoryGridState | null>(null)
  const [roundId, setRoundId] = useState<number | null>(null)
  const [currentTeamIndex, setCurrentTeamIndex] = useState(0)
  const [selectedCell, setSelectedCell] = useState<GridCell | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (code) initGrid()
  }, [code])

  const initGrid = async () => {
    try {
      const gameData = await getGame(code!)
      setGame(gameData)
      
      // Créer la grille
      const grid = await createMemoryGrid(code!)
      setGridState(grid)
      
      // Démarrer le premier round
      const round = await startMemoryGridRound(code!)
      setRoundId(round.round_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur initialisation grille')
    } finally {
      setLoading(false)
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
      
      setSelectedCell(cell)
      
      // Rafraîchir l'état de la grille
      if (gridState) {
        const updated = await getMemoryGridState(gridState.memory_grid.id)
        setGridState(updated)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur révélation cellule')
    }
  }

  const handleAnswerCell = async (isCorrect: boolean) => {
    if (!selectedCell || !roundId || !game) return
    
    const currentTeam = game.teams[currentTeamIndex]
    
    try {
      await answerCell({
        round_id: roundId,
        team_id: currentTeam.id,
        cell_id: selectedCell.id,
        is_correct: isCorrect,
      })
      
      setSelectedCell(null)
      
      // Rafraîchir
      if (gridState) {
        const updated = await getMemoryGridState(gridState.memory_grid.id)
        setGridState(updated)
      }
      
      const gameData = await getGame(code!)
      setGame(gameData)
      
      // Tour suivant
      setCurrentTeamIndex((prev) => (prev + 1) % game.teams.length)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur réponse')
    }
  }

  const handleEndGame = () => {
    navigate(`/results/${code}`)
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-2xl text-slate-400 animate-pulse">Création de la grille...</div>
      </div>
    )
  }

  if (!game || !gridState) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="card text-center">
          <h2 className="text-2xl text-game-danger mb-4">Erreur</h2>
          <p className="text-slate-400">{error}</p>
          <button onClick={() => navigate(`/game/${code}`)} className="btn-primary mt-4">Retour au jeu</button>
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
            <h1 className="text-2xl font-bold">🧠 Manche 3 - Grille Mémoire</h1>
            <p className="text-slate-400 text-sm">Code: {game.code}</p>
          </div>
          <button onClick={handleEndGame} className="btn-danger text-sm">
            Terminer la partie
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Scoreboard */}
          <div className="lg:col-span-1">
            <Scoreboard teams={game.teams} currentTeamIndex={currentTeamIndex} />
          </div>

          {/* Grille */}
          <div className="lg:col-span-3">
            {/* Indicateur équipe active */}
            <div className="card text-center mb-4">
              <p className="text-sm text-slate-400">C'est au tour de</p>
              <p className="text-xl font-bold text-game-accent">{currentTeam.name}</p>
            </div>

            {/* Grille 7x5 */}
            <div className="grid grid-cols-5 gap-2">
              {gridState.cells.map((cell) => (
                <button
                  key={cell.id}
                  onClick={() => handleCellClick(cell)}
                  disabled={cell.status !== 'hidden'}
                  className={`
                    aspect-square rounded-lg font-bold text-sm transition-all duration-200
                    ${cell.status === 'hidden' 
                      ? 'bg-primary-700 hover:bg-primary-600 cursor-pointer hover:scale-105 border-2 border-primary-500' 
                      : cell.status === 'matched'
                        ? 'bg-game-success/30 border-2 border-game-success cursor-not-allowed'
                        : 'bg-game-accent/30 border-2 border-game-accent cursor-not-allowed'
                    }
                  `}
                >
                  {cell.status === 'hidden' ? '?' : cell.status === 'matched' ? '✓' : '●'}
                </button>
              ))}
            </div>

            {/* Popup de réponse */}
            {selectedCell && (
              <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
                <div className="card max-w-md w-full text-center">
                  <h3 className="text-xl font-bold mb-4">Cellule révélée !</h3>
                  <p className="text-slate-400 mb-6">
                    L'équipe <span className="text-game-accent font-bold">{currentTeam.name}</span> a-t-elle répondu correctement ?
                  </p>
                  <div className="flex gap-3">
                    <button
                      onClick={() => handleAnswerCell(false)}
                      className="btn-danger flex-1"
                    >
                      ❌ Non
                    </button>
                    <button
                      onClick={() => handleAnswerCell(true)}
                      className="btn-success flex-1"
                    >
                      ✅ Oui
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

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

export default MemoryGrid

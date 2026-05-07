import { useState } from 'react'
import type { Player } from '../types'

const API_BASE = '/api'

interface PlayerSelectionProps {
  gameCode: string
  onSelectPlayer: (player: Player) => void
  existingPlayers?: Player[]
}

function PlayerSelection({ gameCode, onSelectPlayer, existingPlayers = [] }: PlayerSelectionProps) {
  const [playerName, setPlayerName] = useState('')
  const [isJoining, setIsJoining] = useState(false)
  const [error, setError] = useState('')

  const handleCreatePlayer = async () => {
    if (!playerName.trim()) {
      setError('Player name is required')
      return
    }

    setIsJoining(true)
    setError('')

    try {
      const response = await fetch(`${API_BASE}/games/${gameCode}/players/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: playerName.trim() }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Network error' }))
        throw new Error(errorData.detail || `Error ${response.status}`)
      }

      const newPlayer: Player = await response.json()
      onSelectPlayer(newPlayer)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create player')
    } finally {
      setIsJoining(false)
    }
  }

  const handleSelectExistingPlayer = (player: Player) => {
    onSelectPlayer(player)
  }

  return (
    <div className="bg-gray-800 rounded-lg p-6 max-w-md mx-auto">
      <h2 className="text-2xl font-bold text-white mb-4">Join Round 2 Tournament</h2>
      <p className="text-gray-300 mb-6">Enter your name to participate in the 16→8→4 tournament</p>

      {/* Error display */}
      {error && (
        <div className="bg-red-900 rounded p-3 mb-4">
          <p className="text-white">{error}</p>
        </div>
      )}

      {/* New player form */}
      <div className="mb-6">
        <label htmlFor="playerName" className="block text-gray-300 mb-2">
          Your Name
        </label>
        <input
          id="playerName"
          type="text"
          value={playerName}
          onChange={(e) => setPlayerName(e.target.value)}
          placeholder="Enter your name"
          className="w-full bg-gray-700 text-white px-4 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          disabled={isJoining}
        />
      </div>

      <button
        onClick={handleCreatePlayer}
        disabled={isJoining || !playerName.trim()}
        className={`w-full py-3 rounded-lg font-medium ${
          isJoining || !playerName.trim()
            ? 'bg-gray-600 cursor-not-allowed'
            : 'bg-blue-600 hover:bg-blue-700'
        } text-white transition-colors`}
      >
        {isJoining ? 'Joining...' : 'Join Tournament'}
      </button>

      {/* Existing players (for reconnection) */}
      {existingPlayers.length > 0 && (
        <div className="mt-8 pt-6 border-t border-gray-700">
          <h3 className="text-lg font-medium text-gray-300 mb-3">Reconnect as:</h3>
          <div className="space-y-2">
            {existingPlayers.map((player) => (
              <button
                key={player.id}
                onClick={() => handleSelectExistingPlayer(player)}
                className="w-full bg-gray-700 hover:bg-gray-600 text-white px-4 py-3 rounded-lg text-left"
              >
                <span className="font-medium">{player.name}</span>
                <span className="text-sm text-gray-400 ml-2">
                  {player.team_id ? `Team ${player.team_id}` : 'Individual'}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Game code display */}
      <div className="mt-6 text-center">
        <p className="text-gray-400">Game Code: <span className="text-white font-mono">{gameCode}</span></p>
      </div>
    </div>
  )
}

export default PlayerSelection
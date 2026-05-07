import type { TournamentProgress } from '../types'

interface TournamentProgressProps {
  progress: TournamentProgress
}

function TournamentProgressComponent({ progress }: TournamentProgressProps) {
  const getPhaseColor = (phase: string) => {
    switch (phase) {
      case '16_players':
        return 'bg-blue-600'
      case '8_qualified':
        return 'bg-yellow-600'
      case '4_finalists':
        return 'bg-green-600'
      default:
        return 'bg-gray-600'
    }
  }

  const getPhaseText = (phase: string) => {
    switch (phase) {
      case '16_players':
        return '16 Players'
      case '8_qualified':
        return '8 Qualified'
      case '4_finalists':
        return '4 Finalists'
      default:
        return phase
    }
  }

  const getProgressPercentage = () => {
    switch (progress.phase) {
      case '16_players':
        return 33
      case '8_qualified':
        return 66
      case '4_finalists':
        return 100
      default:
        return 0
    }
  }

  return (
    <div className="bg-gray-800 rounded-lg p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-white">Tournament Progress</h2>
        <span className={`px-3 py-1 rounded-full text-white ${getPhaseColor(progress.phase)}`}>
          {getPhaseText(progress.phase)}
        </span>
      </div>

      {/* Progress bar */}
      <div className="mb-6">
        <div className="flex justify-between text-sm text-gray-300 mb-2">
          <span>16 Players</span>
          <span>8 Qualified</span>
          <span>4 Finalists</span>
        </div>
        <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
          <div 
            className="h-full bg-gradient-to-r from-blue-500 via-yellow-500 to-green-500 transition-all duration-500"
            style={{ width: `${getProgressPercentage()}%` }}
          />
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-gray-700 rounded p-4">
          <p className="text-gray-300 text-sm">Total Players</p>
          <p className="text-2xl font-bold text-white">{progress.players_total}</p>
        </div>
        <div className="bg-gray-700 rounded p-4">
          <p className="text-gray-300 text-sm">Remaining</p>
          <p className="text-2xl font-bold text-white">{progress.players_remaining}</p>
        </div>
        <div className="bg-gray-700 rounded p-4">
          <p className="text-gray-300 text-sm">Eliminated</p>
          <p className="text-2xl font-bold text-white">{progress.players_eliminated}</p>
        </div>
        <div className="bg-gray-700 rounded p-4">
          <p className="text-gray-300 text-sm">Phase</p>
          <p className="text-2xl font-bold text-white">{getPhaseText(progress.phase)}</p>
        </div>
      </div>

      {/* Top players */}
      {progress.top_players.length > 0 && (
        <div className="mt-6">
          <h3 className="text-lg font-medium text-white mb-3">Top Players</h3>
          <div className="space-y-2">
            {progress.top_players.slice(0, 5).map((player, index) => (
              <div key={player.player_id} className="flex items-center justify-between bg-gray-700 rounded p-3">
                <div className="flex items-center">
                  <span className="text-gray-400 mr-3">#{index + 1}</span>
                  <span className="text-white">Player {player.player_id}</span>
                </div>
                <div className="flex items-center">
                  <span className="text-gray-300 mr-4">{player.score} pts</span>
                  <span className={`px-2 py-1 rounded text-xs ${
                    player.status === 'qualified' ? 'bg-green-900 text-green-100' :
                    player.status === 'finalist' ? 'bg-purple-900 text-purple-100' :
                    player.status === 'eliminated' ? 'bg-red-900 text-red-100' :
                    'bg-blue-900 text-blue-100'
                  }`}>
                    {player.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default TournamentProgressComponent
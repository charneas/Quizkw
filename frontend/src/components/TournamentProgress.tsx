import type { TournamentProgress } from '../types'

interface TournamentProgressProps {
  progress: TournamentProgress
  currentPlayerId?: number
}

function TournamentProgressComponent({ progress, currentPlayerId }: TournamentProgressProps) {
  const currentPlayerRank = currentPlayerId 
    ? progress.top_players.findIndex(p => p.player_id === currentPlayerId) + 1
    : null
  const getPhaseColor = (phase: string) => {
    switch (phase) {
      case '16_players':
        return 'bg-brand-600'
      case '8_qualified':
        return 'bg-brand-600'
      case '4_finalists':
        return 'bg-success'
      default:
        return 'bg-surface-raised'
    }
  }

  const getPhaseTextColor = (phase: string) => (phase === '4_finalists' ? 'text-bg' : 'text-text')
  // '16_players' (bg-brand-600) et '8_qualified' (brand-600 aussi) restent en text-text (5.06:1, cf. tailwind.config.js) ; seule '4_finalists' (bg-success) bascule en text-bg pour le même motif de contraste.

  const getPhaseText = (phase: string) => {
    const total = progress.players_total
    switch (phase) {
      case '16_players':
        return `${total} Players`
      case '8_qualified':
        return `${Math.ceil(total / 2)} Qualified`
      case '4_finalists':
        return `${Math.ceil(total / 4)} Finalists`
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
    <div className="bg-surface rounded-lg p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-display font-semibold text-text">Tournament Progress</h2>
          {currentPlayerRank && currentPlayerRank > 0 && (
            <p className="text-sm text-accent font-semibold mt-1">
              🏆 Your Position: #{currentPlayerRank}/{progress.players_total}
            </p>
          )}
        </div>
        <span className={`px-3 py-1 rounded-full ${getPhaseTextColor(progress.phase)} ${getPhaseColor(progress.phase)}`}>
          {getPhaseText(progress.phase)}
        </span>
      </div>

      {/* Progress bar */}
      <div className="mb-6">
        <div className="flex justify-between text-sm text-text-muted mb-2">
          <span>{getPhaseText('16_players')}</span>
          <span>{getPhaseText('8_qualified')}</span>
          <span>{getPhaseText('4_finalists')}</span>
        </div>
        <div className="h-2 bg-border rounded-full overflow-hidden">
          <div
            className="h-full bg-brand transition-all duration-500"
            style={{ width: `${getProgressPercentage()}%` }}
          />
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-surface-raised rounded p-4">
          <p className="text-text-muted text-sm">Total Players</p>
          <p className="text-2xl font-bold text-text">{progress.players_total}</p>
        </div>
        <div className="bg-surface-raised rounded p-4">
          <p className="text-text-muted text-sm">Remaining</p>
          <p className="text-2xl font-bold text-text">{progress.players_remaining}</p>
        </div>
        <div className="bg-surface-raised rounded p-4">
          <p className="text-text-muted text-sm">Eliminated</p>
          <p className="text-2xl font-bold text-text">{progress.players_eliminated}</p>
        </div>
        <div className="bg-surface-raised rounded p-4">
          <p className="text-text-muted text-sm">Phase</p>
          <p className="text-2xl font-bold text-text">{getPhaseText(progress.phase)}</p>
        </div>
      </div>

      {/* Top players */}
      {progress.top_players.length > 0 && (
        <div className="mt-6">
          <h3 className="text-lg font-medium text-text mb-3">Top Players</h3>
          <div className="space-y-2">
            {progress.top_players.slice(0, 5).map((player, index) => (
              <div key={player.player_id} className="flex items-center justify-between bg-surface-raised rounded p-3">
                <div className="flex items-center">
                  <span className="text-text-muted mr-3">#{index + 1}</span>
                  <span className="text-text">{player.player_name}</span>
                </div>
                <div className="flex items-center">
                  <span className="text-text-muted mr-4">{player.score} pts</span>
                  <span className={`px-2 py-1 rounded text-xs ${
                    player.status === 'qualified' ? 'bg-success text-bg' :
                    player.status === 'finalist' ? 'bg-brand-muted text-text' :
                    player.status === 'eliminated' ? 'bg-danger text-text' :
                    'bg-brand-600 text-text'
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
import type { IntermediateLeaderboardResponse, TournamentProgress } from '../types'

interface IntermediateLeaderboardProps {
  leaderboard: IntermediateLeaderboardResponse
  tournamentProgress: TournamentProgress
  onAdvance: () => void
  canAdvance: boolean
}

function IntermediateLeaderboardComponent({ leaderboard, tournamentProgress, onAdvance, canAdvance }: IntermediateLeaderboardProps) {
  return (
    <div className="bg-surface rounded-lg p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-display font-semibold text-text">Intermediate Leaderboard</h2>
          <p className="text-text-muted">Top 8 qualified for next phase</p>
        </div>
        <div className="text-right">
          <p className="text-text-muted">Cutoff Score: <span className="text-text font-bold">{leaderboard.cutoff_score}</span></p>
          <p className="text-text-muted text-sm">Players below this score are eliminated</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Qualified Players */}
        <div>
          <h3 className="text-xl font-bold text-success mb-4">✅ Qualified ({leaderboard.qualified_players.length})</h3>
          <div className="space-y-3">
            {leaderboard.qualified_players.map((player, index) => (
              <div key={player.id} className="bg-surface-raised rounded p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <span className="text-text-muted mr-3">#{index + 1}</span>
                    <div>
                      <p className="text-text font-medium">Player {player.player_id}</p>
                      <p className="text-text-muted text-sm">
                        Score: {player.score} | Correct: {player.correct_answers}/{player.questions_answered}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="bg-success text-bg px-3 py-1 rounded-full text-sm">
                      Qualified
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Eliminated Players */}
        <div>
          <h3 className="text-xl font-bold text-danger mb-4">❌ Eliminated ({leaderboard.eliminated_players.length})</h3>
          <div className="space-y-3">
            {leaderboard.eliminated_players.map((player, index) => (
              <div key={player.id} className="bg-surface-raised rounded p-4 opacity-70">
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <span className="text-text-muted mr-3">#{leaderboard.qualified_players.length + index + 1}</span>
                    <div>
                      <p className="text-text font-medium">Player {player.player_id}</p>
                      <p className="text-text-muted text-sm">
                        Score: {player.score} | Correct: {player.correct_answers}/{player.questions_answered}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="bg-danger text-bg px-3 py-1 rounded-full text-sm">
                      Eliminated
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Tournament Stats */}
      <div className="mt-8 pt-6 border-t border-border">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-surface-raised rounded p-4">
            <p className="text-text-muted text-sm">Total Players</p>
            <p className="text-2xl font-bold text-text">{tournamentProgress.players_total}</p>
          </div>
          <div className="bg-surface-raised rounded p-4">
            <p className="text-text-muted text-sm">Qualified</p>
            <p className="text-2xl font-bold text-success">{leaderboard.qualified_players.length}</p>
          </div>
          <div className="bg-surface-raised rounded p-4">
            <p className="text-text-muted text-sm">Eliminated</p>
            <p className="text-2xl font-bold text-danger">{leaderboard.eliminated_players.length}</p>
          </div>
          <div className="bg-surface-raised rounded p-4">
            <p className="text-text-muted text-sm">Next Phase</p>
            <p className="text-2xl font-bold text-brand">8→4</p>
          </div>
        </div>

        {/* Action Button — visible seulement au détenteur du host token (BUG-206) */}
        <div className="text-center">
          {canAdvance ? (
            <button
              onClick={onAdvance}
              className="btn-primary text-lg"
            >
              Advance to 8→4 Phase
            </button>
          ) : (
            <p className="text-text-muted">Waiting for the host to advance to the next phase...</p>
          )}
          <p className="text-text-muted mt-2">
            Top 8 will compete for 4 finalist spots in the next phase
          </p>
        </div>
      </div>
    </div>
  )
}

export default IntermediateLeaderboardComponent
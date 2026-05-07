import type { IntermediateLeaderboardResponse, TournamentProgress } from '../types'

interface IntermediateLeaderboardProps {
  leaderboard: IntermediateLeaderboardResponse
  tournamentProgress: TournamentProgress
  onAdvance: () => void
}

function IntermediateLeaderboardComponent({ leaderboard, tournamentProgress, onAdvance }: IntermediateLeaderboardProps) {
  return (
    <div className="bg-gray-800 rounded-lg p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-white">Intermediate Leaderboard</h2>
          <p className="text-gray-300">Top 8 qualified for next phase</p>
        </div>
        <div className="text-right">
          <p className="text-gray-300">Cutoff Score: <span className="text-white font-bold">{leaderboard.cutoff_score}</span></p>
          <p className="text-gray-300 text-sm">Players below this score are eliminated</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Qualified Players */}
        <div>
          <h3 className="text-xl font-bold text-green-400 mb-4">✅ Qualified ({leaderboard.qualified_players.length})</h3>
          <div className="space-y-3">
            {leaderboard.qualified_players.map((player, index) => (
              <div key={player.id} className="bg-gray-700 rounded p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <span className="text-gray-400 mr-3">#{index + 1}</span>
                    <div>
                      <p className="text-white font-medium">Player {player.player_id}</p>
                      <p className="text-gray-400 text-sm">
                        Score: {player.score} | Correct: {player.correct_answers}/{player.questions_answered}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="bg-green-900 text-green-100 px-3 py-1 rounded-full text-sm">
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
          <h3 className="text-xl font-bold text-red-400 mb-4">❌ Eliminated ({leaderboard.eliminated_players.length})</h3>
          <div className="space-y-3">
            {leaderboard.eliminated_players.map((player, index) => (
              <div key={player.id} className="bg-gray-700 rounded p-4 opacity-70">
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <span className="text-gray-400 mr-3">#{leaderboard.qualified_players.length + index + 1}</span>
                    <div>
                      <p className="text-white font-medium">Player {player.player_id}</p>
                      <p className="text-gray-400 text-sm">
                        Score: {player.score} | Correct: {player.correct_answers}/{player.questions_answered}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="bg-red-900 text-red-100 px-3 py-1 rounded-full text-sm">
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
      <div className="mt-8 pt-6 border-t border-gray-700">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-gray-700 rounded p-4">
            <p className="text-gray-300 text-sm">Total Players</p>
            <p className="text-2xl font-bold text-white">{tournamentProgress.players_total}</p>
          </div>
          <div className="bg-gray-700 rounded p-4">
            <p className="text-gray-300 text-sm">Qualified</p>
            <p className="text-2xl font-bold text-green-400">{leaderboard.qualified_players.length}</p>
          </div>
          <div className="bg-gray-700 rounded p-4">
            <p className="text-gray-300 text-sm">Eliminated</p>
            <p className="text-2xl font-bold text-red-400">{leaderboard.eliminated_players.length}</p>
          </div>
          <div className="bg-gray-700 rounded p-4">
            <p className="text-gray-300 text-sm">Next Phase</p>
            <p className="text-2xl font-bold text-yellow-400">8→4</p>
          </div>
        </div>

        {/* Action Button */}
        <div className="text-center">
          <button
            onClick={onAdvance}
            className="bg-yellow-600 hover:bg-yellow-700 text-white px-8 py-3 rounded-lg font-medium text-lg"
          >
            Advance to 8→4 Phase
          </button>
          <p className="text-gray-400 mt-2">
            Top 8 will compete for 4 finalist spots in the next phase
          </p>
        </div>
      </div>
    </div>
  )
}

export default IntermediateLeaderboardComponent
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
          <h2 className="text-2xl font-display font-semibold text-text">Classement intermédiaire</h2>
          <p className="text-text-muted">Top 8 qualifiés pour la phase suivante</p>
        </div>
        <div className="text-right">
          <p className="text-text-muted">Score de coupure : <span className="text-text font-bold">{leaderboard.cutoff_score}</span></p>
          <p className="text-text-muted text-sm">Les joueurs sous ce score sont éliminés</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Qualified Players */}
        <div>
          <h3 className="text-xl font-bold text-success mb-4">✅ Qualifiés ({leaderboard.qualified_players.length})</h3>
          <div className="space-y-3">
            {leaderboard.qualified_players.map((player, index) => (
              <div key={player.id} className="bg-surface-raised rounded p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <span className="text-text-muted mr-3">#{index + 1}</span>
                    <div>
                      <p className="text-text font-medium">Joueur {player.player_id}</p>
                      <p className="text-text-muted text-sm">
                        Score : {player.score} | Correct : {player.correct_answers}/{player.questions_answered}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="bg-success text-bg px-3 py-1 rounded-full text-sm">
                      Qualifié
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Eliminated Players */}
        <div>
          <h3 className="text-xl font-bold text-danger mb-4">❌ Éliminés ({leaderboard.eliminated_players.length})</h3>
          <div className="space-y-3">
            {leaderboard.eliminated_players.map((player, index) => (
              <div key={player.id} className="bg-surface-raised rounded p-4 opacity-70">
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <span className="text-text-muted mr-3">#{leaderboard.qualified_players.length + index + 1}</span>
                    <div>
                      <p className="text-text font-medium">Joueur {player.player_id}</p>
                      <p className="text-text-muted text-sm">
                        Score : {player.score} | Correct : {player.correct_answers}/{player.questions_answered}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="bg-danger text-bg px-3 py-1 rounded-full text-sm">
                      Éliminé
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
            <p className="text-text-muted text-sm">Total joueurs</p>
            <p className="text-2xl font-bold text-text">{tournamentProgress.players_total}</p>
          </div>
          <div className="bg-surface-raised rounded p-4">
            <p className="text-text-muted text-sm">Qualifiés</p>
            <p className="text-2xl font-bold text-success">{leaderboard.qualified_players.length}</p>
          </div>
          <div className="bg-surface-raised rounded p-4">
            <p className="text-text-muted text-sm">Éliminés</p>
            <p className="text-2xl font-bold text-danger">{leaderboard.eliminated_players.length}</p>
          </div>
          <div className="bg-surface-raised rounded p-4">
            <p className="text-text-muted text-sm">Phase suivante</p>
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
              Passer à la phase 8→4
            </button>
          ) : (
            <p className="text-text-muted">En attente que l'hôte passe à la phase suivante...</p>
          )}
          <p className="text-text-muted mt-2">
            Les 8 qualifiés s'affronteront pour 4 places de finaliste lors de la phase suivante
          </p>
        </div>
      </div>
    </div>
  )
}

export default IntermediateLeaderboardComponent
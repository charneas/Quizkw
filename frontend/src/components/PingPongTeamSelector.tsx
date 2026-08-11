import type { Team } from '../types'

interface PingPongTeamSelectorProps {
  currentTeam: Team
  availableTeams: Team[]
  onSelect: (team2: Team) => void
  onCancel: () => void
}

function PingPongTeamSelector({
  currentTeam,
  availableTeams,
  onSelect,
  onCancel,
}: PingPongTeamSelectorProps) {
  return (
    <div className="card">
      <div className="text-center mb-6">
        <div className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 rounded-full mb-4">
          <span className="text-2xl">🏓</span>
          <span className="font-bold text-white">DUEL PING-PONG</span>
        </div>
        <h2 className="text-xl font-bold mb-2">Choisissez votre adversaire</h2>
        <p className="text-text-muted text-sm">
          <span className="font-bold text-brand">{currentTeam.name}</span>, quelle équipe voulez-vous défier ?
        </p>
      </div>

      {/* Current team */}
      <div className="bg-brand-muted/20 border-2 border-brand rounded-lg p-4 mb-6 text-center">
        <p className="text-sm text-text-muted">Votre équipe</p>
        <p className="text-xl font-bold text-brand">{currentTeam.name}</p>
        <p className="text-xs text-text-muted mt-1">Vous commencerez le duel</p>
      </div>

      {/* Opponent selection */}
      {availableTeams.length === 0 ? (
        <div className="text-center py-4">
          <p className="text-text-muted">Aucune autre équipe disponible</p>
        </div>
      ) : (
        <div className="space-y-3 mb-6">
          <p className="text-sm font-semibold text-text-muted uppercase tracking-wide">
            Adversaires disponibles
          </p>
          {availableTeams.map((team) => (
            <button
              key={team.id}
              onClick={() => onSelect(team)}
              className="w-full p-4 bg-surface-raised hover:bg-surface border-2 border-border hover:border-brand rounded-lg text-left transition-colors flex items-center justify-between group"
            >
              <div>
                <p className="font-bold text-text group-hover:text-brand transition-colors">
                  {team.name}
                </p>
                <p className="text-sm text-text-muted">
                  Score actuel : {team.score} pts
                </p>
              </div>
              <span className="text-2xl opacity-0 group-hover:opacity-100 transition-opacity">
                ⚔️
              </span>
            </button>
          ))}
        </div>
      )}

      {/* Cancel */}
      <button onClick={onCancel} className="w-full py-2 border-2 border-dashed border-border hover:border-danger text-text-muted hover:text-danger rounded-lg transition-colors">
        Annuler le duel ping-pong
      </button>
    </div>
  )
}

export default PingPongTeamSelector
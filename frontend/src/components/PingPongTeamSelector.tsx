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
        <p className="text-slate-400 text-sm">
          <span className="font-bold text-game-accent">{currentTeam.name}</span>, quelle équipe voulez-vous défier ?
        </p>
      </div>

      {/* Current team */}
      <div className="bg-game-accent/10 border-2 border-game-accent rounded-lg p-4 mb-6 text-center">
        <p className="text-sm text-slate-400">Votre équipe</p>
        <p className="text-xl font-bold text-game-accent">{currentTeam.name}</p>
        <p className="text-xs text-slate-500 mt-1">Vous commencerez le duel</p>
      </div>

      {/* Opponent selection */}
      {availableTeams.length === 0 ? (
        <div className="text-center py-4">
          <p className="text-slate-400">Aucune autre équipe disponible</p>
        </div>
      ) : (
        <div className="space-y-3 mb-6">
          <p className="text-sm font-semibold text-slate-400 uppercase tracking-wide">
            Adversaires disponibles
          </p>
          {availableTeams.map((team) => (
            <button
              key={team.id}
              onClick={() => onSelect(team)}
              className="w-full p-4 bg-slate-700/50 hover:bg-slate-700 border-2 border-slate-600 hover:border-game-accent rounded-lg text-left transition-colors flex items-center justify-between group"
            >
              <div>
                <p className="font-bold text-white group-hover:text-game-accent transition-colors">
                  {team.name}
                </p>
                <p className="text-sm text-slate-400">
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
      <button onClick={onCancel} className="w-full py-2 border-2 border-dashed border-slate-600 hover:border-red-500 text-slate-400 hover:text-red-400 rounded-lg transition-colors">
        Annuler le duel ping-pong
      </button>
    </div>
  )
}

export default PingPongTeamSelector
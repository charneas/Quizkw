import type { Team } from '../types'

interface TeamCompositionProps {
  teams: Team[]
}

// BUG-114 : l'hôte n'avait aucune vue sur la composition des équipes.
function TeamComposition({ teams }: TeamCompositionProps) {
  return (
    <div className="card">
      <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
        👥 Équipes
      </h2>
      <div className="space-y-3">
        {teams.map((team) => (
          <div key={team.id} className="p-3 rounded-lg bg-surface-raised border border-transparent">
            <p className="font-medium text-text mb-1">{team.name}</p>
            {team.players.length === 0 ? (
              <p className="text-xs text-text-muted italic">Aucun joueur</p>
            ) : (
              <ul className="text-sm text-text-muted space-y-0.5">
                {team.players.map((player) => (
                  <li key={player.id}>{player.name}</li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default TeamComposition

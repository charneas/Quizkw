import type { Team } from '../types'

interface ScoreboardProps {
  teams: Team[]
  currentTeamIndex: number
}

function Scoreboard({ teams, currentTeamIndex }: ScoreboardProps) {
  // Trier par score décroissant pour l'affichage
  const sortedTeams = [...teams]
    .map((team, originalIndex) => ({ ...team, originalIndex }))
    .sort((a, b) => b.score - a.score)

  return (
    <div className="card">
      <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
        📊 Scores
      </h2>
      <div className="space-y-2">
        {sortedTeams.map((team, rank) => (
          <div
            key={team.id}
            className={`flex items-center justify-between p-3 rounded-lg transition-all ${
              team.originalIndex === currentTeamIndex
                ? 'bg-brand-muted/30 border border-accent scale-[1.02]'
                : 'bg-surface-raised border border-transparent'
            }`}
          >
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-text-muted w-5">
                {rank + 1}.
              </span>
              <span className={`font-medium ${team.originalIndex === currentTeamIndex ? 'text-accent' : 'text-text'}`}>
                {team.name}
              </span>
              {team.originalIndex === currentTeamIndex && (
                <span className="text-xs text-accent">◄</span>
              )}
            </div>
            <span className="font-bold text-brand text-lg">
              {team.score}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default Scoreboard

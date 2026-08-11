import type { Team } from '../types'

interface ScoreboardProps {
  teams: Team[]
}

function Scoreboard({ teams }: ScoreboardProps) {
  // Trier par score décroissant pour l'affichage
  const sortedTeams = [...teams].sort((a, b) => b.score - a.score)

  return (
    <div className="card">
      <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
        📊 Scores
      </h2>
      <div className="space-y-2">
        {sortedTeams.map((team, rank) => {
          // Le leader n'est mis en avant que s'il n'est pas à égalité avec
          // le suivant — une égalité en tête n'a pas de "leader" réel.
          const isLeader = rank === 0 && (sortedTeams.length === 1 || team.score > sortedTeams[1].score)
          return (
            <div
              key={team.id}
              className={`flex items-center justify-between p-3 rounded-lg border transition-colors ${
                isLeader
                  ? 'bg-brand-muted/20 border-brand'
                  : 'bg-surface-raised border-transparent'
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-text-muted w-5">
                  {isLeader ? '👑' : `${rank + 1}.`}
                </span>
                <span className="font-medium text-text">
                  {team.name}
                </span>
              </div>
              <span className="font-bold text-brand text-lg">
                {team.score}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default Scoreboard
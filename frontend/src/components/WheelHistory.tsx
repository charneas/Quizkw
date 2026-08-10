import type { WheelHistoryEntry } from '../services/api'

interface WheelHistoryProps {
  history: WheelHistoryEntry[]
}

// BUG-106 (#8) : vue consolidée des tours de roue déjà joués, dans l'ordre
// chronologique — utilisée par l'écran host et l'écran équipe.
function WheelHistory({ history }: WheelHistoryProps) {
  if (history.length === 0) return null

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wide mb-3">
        Historique de la roue
      </h3>
      <div className="space-y-1 max-h-48 overflow-y-auto">
        {history.map((entry, index) => (
          <div key={entry.id} className="flex items-baseline gap-2 text-sm">
            <span className="text-text-muted w-6 shrink-0">#{index + 1}</span>
            <span className="text-text">{entry.message}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default WheelHistory
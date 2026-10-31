import type { BlindtestClassicRevealPayload } from '../types'

interface ClassicRevealProps {
  reveal: BlindtestClassicRevealPayload
  myPseudo: string
}

export default function ClassicReveal({ reveal, myPseudo }: ClassicRevealProps) {
  return (
    <div className="space-y-4">
      <div className="card px-4 py-5 text-center">
        <p className="text-text-muted text-sm mb-1">C'était</p>
        <p className="font-display font-semibold text-2xl text-text">{reveal.title}</p>
        <p className="text-accent">{reveal.artist}</p>
      </div>
      <ul className="space-y-1">
        {Object.entries(reveal.scores)
          .sort(([, a], [, b]) => b - a)
          .map(([playerPseudo, score]) => {
            const delta = reveal.deltas[playerPseudo] ?? 0
            return (
              <li
                key={playerPseudo}
                className={`card px-3 py-2 flex justify-between items-center ${
                  playerPseudo === myPseudo ? 'ring-1 ring-brand' : ''
                }`}
              >
                <span>{playerPseudo}</span>
                <span className="flex items-center gap-2">
                  <span className={`animate-fade-in text-sm font-semibold ${delta > 0 ? 'text-success' : 'text-text-muted'}`}>
                    {delta > 0 ? `+${delta}` : delta}
                  </span>
                  <span>{score}</span>
                </span>
              </li>
            )
          })}
      </ul>
    </div>
  )
}

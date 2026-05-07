import type { TokenType } from '../types'

interface TokenPanelProps {
  teamId: number
  onUseToken: (tokenType: TokenType) => void
}

const tokenInfo: Record<TokenType, { emoji: string; label: string; description: string }> = {
  swap: {
    emoji: '🔄',
    label: 'SWAP',
    description: 'Changer de question',
  },
  penalty: {
    emoji: '⚡',
    label: 'Pénalité',
    description: 'Donner une pénalité',
  },
  bonus: {
    emoji: '⭐',
    label: 'Bonus',
    description: 'Double des points',
  },
}

function TokenPanel({ onUseToken }: TokenPanelProps) {
  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-slate-400 mb-3">🎴 Jetons disponibles</h3>
      <div className="flex gap-2">
        {(Object.keys(tokenInfo) as TokenType[]).map((type) => (
          <button
            key={type}
            onClick={() => onUseToken(type)}
            className="flex-1 bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded-lg p-3 text-center transition-all hover:scale-105 active:scale-95"
            title={tokenInfo[type].description}
          >
            <div className="text-2xl mb-1">{tokenInfo[type].emoji}</div>
            <div className="text-xs text-slate-400">{tokenInfo[type].label}</div>
          </button>
        ))}
      </div>
    </div>
  )
}

export default TokenPanel

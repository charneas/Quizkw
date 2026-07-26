import { useRef, useState } from 'react'
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

// PENALTY requiert une confirmation avant application (clic accidentel à fort
// impact identifié en session UX) — SWAP/BONUS restent sans confirmation.
// Portée confirmée avec l'utilisateur (story I-003, 2026-07-27) : le backend
// ne supporte pas de ciblage d'équipe pour PENALTY, la confirmation est générique.
function TokenPanel({ onUseToken }: TokenPanelProps) {
  const [confirmingPenalty, setConfirmingPenalty] = useState(false)
  const penaltyConfirmedRef = useRef(false)

  const handleTokenClick = (type: TokenType) => {
    if (type === 'penalty') {
      penaltyConfirmedRef.current = false
      setConfirmingPenalty(true)
    } else {
      onUseToken(type)
    }
  }

  const handleConfirmPenalty = () => {
    if (penaltyConfirmedRef.current) return
    penaltyConfirmedRef.current = true
    setConfirmingPenalty(false)
    onUseToken('penalty')
  }

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-text-muted mb-3">🎴 Jetons disponibles</h3>
      <div className="flex gap-2">
        {(Object.keys(tokenInfo) as TokenType[]).map((type) => (
          <button
            key={type}
            onClick={() => handleTokenClick(type)}
            className="flex-1 bg-surface-raised hover:bg-surface border border-border rounded-lg p-3 text-center transition-all hover:scale-105 active:scale-95"
            title={tokenInfo[type].description}
          >
            <div className="text-2xl mb-1">{tokenInfo[type].emoji}</div>
            <div className="text-xs text-text-muted">{tokenInfo[type].label}</div>
          </button>
        ))}
      </div>

      {confirmingPenalty && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
          <div className="card max-w-sm w-full text-center">
            <div className="text-4xl mb-3">⚡</div>
            <h3 className="text-lg font-semibold text-text mb-2">Appliquer PENALTY ?</h3>
            <p className="text-sm text-text-muted mb-6">
              Cette action est irréversible. Confirmez-vous l'utilisation de ce jeton ?
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setConfirmingPenalty(false)}
                className="btn-secondary flex-1 min-h-[44px]"
              >
                Annuler
              </button>
              <button
                onClick={handleConfirmPenalty}
                className="btn-danger flex-1 min-h-[44px]"
              >
                Confirmer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default TokenPanel

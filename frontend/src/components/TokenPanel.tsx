import { useRef, useState } from 'react'
import type { TokenType } from '../types'

interface Token {
  id: number
  token_type: string // Changé en string pour accepter les données brutes du backend
  is_used: boolean
}

interface TokenPanelProps {
  tokens: Token[]
  onUseToken: (type: TokenType) => void
}

function TokenPanel({ tokens = [], onUseToken }: TokenPanelProps) {
  const safeTokens = Array.isArray(tokens) ? tokens : [];

  const tokenLabels: Record<string, { label: string; desc: string; icon: string; apiType: TokenType }> = {
    swap: { label: 'SWAP', desc: 'Change de question', icon: '🔄', apiType: 'swap' },
    penalty: { label: 'PÉNALITÉ', desc: 'Enlève 10s aux adversaires', icon: '⚡', apiType: 'penalty' },
    bonus: { label: 'BONUS', desc: 'Double les points de la question', icon: '⭐', apiType: 'bonus' },
  }

<<<<<<< HEAD
  return (
    <div className="card">
      <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
        <span>🎴</span> Vos Jetons Disponibles
      </h3>
      
      {safeTokens.length === 0 ? (
        <p className="text-slate-400 text-sm italic py-2">
          Aucun jeton disponible pour cette équipe (ils doivent être générés par le backend).
        </p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {safeTokens.map((token) => {
            // Sécurité : Convertir en minuscules pour correspondre à "swap", "penalty", "bonus"
            const cleanedType = token.token_type.toLowerCase().trim();
            const config = tokenLabels[cleanedType] || { label: token.token_type, desc: '', icon: '🎫', apiType: cleanedType as TokenType };
            
            return (
              <button
                key={token.id}
                disabled={token.is_used}
                onClick={() => onUseToken(config.apiType)}
                className={`flex flex-col items-center justify-center p-4 rounded-xl border text-center transition-all ${
                  token.is_used
                    ? 'bg-slate-900/40 border-slate-800 text-slate-600 cursor-not-allowed opacity-50'
                    : 'bg-slate-800/50 border-slate-700 hover:border-game-accent text-white hover:scale-[1.02]'
                }`}
              >
                <span className="text-2xl mb-1">{config.icon}</span>
                <span className="font-bold text-sm">{config.label}</span>
                <span className="text-xs text-slate-400 mt-1">{config.desc}</span>
                {token.is_used && (
                  <span className="text-[10px] uppercase tracking-wider font-semibold text-red-400 mt-2 bg-red-950/50 px-2 py-0.5 rounded">
                    Utilisé
                  </span>
                )}
              </button>
            )
          })}
=======
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
>>>>>>> master
        </div>
      )}
    </div>
  )
}

export default TokenPanel
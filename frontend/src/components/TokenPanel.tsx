import { useRef, useState } from 'react'
import type { TokenType } from '../types'

const PENALTY_POINTS = 2

interface Token {
  id: number
  token_type: string // Changé en string pour accepter les données brutes du backend
  is_used: boolean
}

interface OtherTeam {
  team_id: number
  team_name: string
}

interface TokenPanelProps {
  tokens: Token[]
  otherTeams?: OtherTeam[]
  onUseToken: (type: TokenType, targetTeamId?: number) => void | Promise<unknown>
}

function TokenPanel({ tokens = [], otherTeams = [], onUseToken }: TokenPanelProps) {
  const safeTokens = Array.isArray(tokens) ? tokens : [];
  const [confirmingPenalty, setConfirmingPenalty] = useState<TokenType | null>(null)
  const [selectedTargetId, setSelectedTargetId] = useState<number | null>(null)
  const penaltyConfirmedRef = useRef(false)
  // Garde anti double-clic : `token.is_used` ne redevient vrai qu'après
  // l'aller-retour réseau du parent (loadTeamTokens/loadState). Entre-temps,
  // un double-tap (notamment mobile) pouvait renvoyer plusieurs requêtes
  // /tokens/use pour le même jeton avant que le bouton ne se désactive
  // (BUG-101 : "swaps infinis" — voir aussi le verrou ajouté côté backend).
  // useState (pas une simple ref) pour que le bouton se désactive visuellement
  // dès le premier clic, sans attendre le prochain rendu déclenché ailleurs.
  const [firingTokenIds, setFiringTokenIds] = useState<Set<number>>(new Set())

  const tokenLabels: Record<string, { label: string; desc: string; icon: string; apiType: TokenType }> = {
    swap: { label: 'SWAP', desc: 'Change de question', icon: '🔄', apiType: 'swap' },
    penalty: { label: 'PÉNALITÉ', desc: `Retire ${PENALTY_POINTS} points à l'équipe ciblée`, icon: '⚡', apiType: 'penalty' },
    bonus: { label: 'BONUS', desc: 'Double les points de la question', icon: '⭐', apiType: 'bonus' },
  }

  // PENALTY requiert de choisir une équipe cible puis de confirmer (clic
  // accidentel à fort impact identifié en session UX) — SWAP/BONUS restent
  // sans confirmation.
  const handleTokenClick = (apiType: TokenType, tokenId: number) => {
    if (apiType === 'penalty') {
      penaltyConfirmedRef.current = false
      setSelectedTargetId(null)
      setConfirmingPenalty(apiType)
      return
    }
    if (firingTokenIds.has(tokenId)) return
    setFiringTokenIds((prev) => new Set(prev).add(tokenId))
    // onUseToken gère déjà ses propres erreurs (voir Game.tsx/TeamScreen.tsx) ;
    // on ne fait que garantir que le bouton se redébloque dans tous les cas
    // (succès, 400 "déjà utilisé", erreur réseau...), sinon un jeton encore
    // possédé par l'équipe resterait inutilisable jusqu'au démontage du composant.
    Promise.resolve(onUseToken(apiType)).finally(() => {
      setFiringTokenIds((prev) => {
        const next = new Set(prev)
        next.delete(tokenId)
        return next
      })
    })
  }

  const handleConfirmPenalty = () => {
    if (penaltyConfirmedRef.current || !confirmingPenalty || !selectedTargetId) return
    penaltyConfirmedRef.current = true
    const apiType = confirmingPenalty
    const targetId = selectedTargetId
    setConfirmingPenalty(null)
    setSelectedTargetId(null)
    onUseToken(apiType, targetId)
  }

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
                disabled={token.is_used || firingTokenIds.has(token.id)}
                onClick={() => handleTokenClick(config.apiType, token.id)}
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
        </div>
      )}

      {confirmingPenalty && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
          <div className="card max-w-sm w-full text-center">
            <div className="text-4xl mb-3">⚡</div>
            <h3 className="text-lg font-semibold text-text mb-2">Choisir l'équipe à pénaliser</h3>
            <p className="text-sm text-text-muted mb-4">
              Cette action est irréversible.
            </p>
            {otherTeams.length === 0 ? (
              <p className="text-sm text-danger mb-4">Aucune autre équipe à cibler.</p>
            ) : (
              <div className="flex flex-col gap-2 mb-6">
                {otherTeams.map((t) => (
                  <button
                    key={t.team_id}
                    onClick={() => setSelectedTargetId(t.team_id)}
                    className={`min-h-[44px] rounded-lg border px-3 text-sm font-medium transition-all ${
                      selectedTargetId === t.team_id
                        ? 'border-game-accent bg-game-accent/20 text-white'
                        : 'border-slate-700 bg-slate-800/50 text-slate-300 hover:border-game-accent'
                    }`}
                  >
                    {t.team_name}
                  </button>
                ))}
              </div>
            )}
            <div className="flex gap-3">
              <button
                onClick={() => { setConfirmingPenalty(null); setSelectedTargetId(null) }}
                className="btn-secondary flex-1 min-h-[44px]"
              >
                Annuler
              </button>
              <button
                onClick={handleConfirmPenalty}
                disabled={!selectedTargetId}
                className="btn-danger flex-1 min-h-[44px] disabled:opacity-40 disabled:cursor-not-allowed"
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
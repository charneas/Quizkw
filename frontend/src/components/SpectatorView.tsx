import type { ReactNode } from 'react'

interface SpectatorViewProps {
  message?: string
  children: ReactNode
}

/**
 * BUG-401 (#32) : bandeau + conteneur commun pour les vues spectateur d'un
 * joueur éliminé (Manche 2 et Manche 3) — lecture seule, aucune action de
 * jeu ne doit être rendue à l'intérieur.
 */
function SpectatorView({ message = 'Vous avez été éliminé — vous suivez la partie en spectateur.', children }: SpectatorViewProps) {
  return (
    <div className="space-y-4">
      <div className="bg-surface-raised border border-border rounded-lg p-4 text-center">
        <p className="text-sm text-text-muted">👁️ {message}</p>
      </div>
      {children}
    </div>
  )
}

export default SpectatorView
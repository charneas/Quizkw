import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getGame } from '../services/api'
import type { GameSession } from '../types'

/** Écran d'attente de la file publique (spec-rooms-publiques, story 1).
 *
 * Poll (pattern de Lobby.tsx, setInterval 3s) l'état de la partie. Tant que
 * `started=False`, n'affiche jamais le code de partie — reçu dès la réponse
 * de joinPublicQueue mais délibérément caché ici (pure question d'affichage,
 * voir Boundaries de la story). Dès `started=True`, révèle le code et
 * redirige vers le lobby pour poursuivre le flow existant (choix des
 * équipes, déjà auto-assemblées ici).
 */
function PublicQueue() {
  const { code } = useParams<{ code: string }>()
  const navigate = useNavigate()
  const [game, setGame] = useState<GameSession | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!code) return
    let cancelled = false

    const poll = async () => {
      try {
        const data = await getGame(code)
        if (cancelled) return
        setGame(data)
        setError('')
        if (data.started) {
          navigate(`/lobby/${code}`)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Session non trouvée')
        }
      }
    }

    poll()
    const interval = setInterval(poll, 3000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [code, navigate])

  const playerCount = game?.teams.length ?? 0

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="card max-w-md w-full text-center space-y-4">
        <h1 className="text-2xl font-display font-semibold text-text">🌍 File d'attente publique</h1>
        {error ? (
          <div className="text-danger text-sm bg-danger/10 rounded-lg p-3">{error}</div>
        ) : (
          <>
            <p className="text-text-muted text-lg animate-pulse">
              En attente d'autres joueurs...
            </p>
            <p className="text-3xl font-display font-semibold text-brand">
              {playerCount}/4
            </p>
            <p className="text-sm text-text-muted">
              La partie démarrera automatiquement dès que 4 joueurs seront réunis.
            </p>
          </>
        )}
        <button onClick={() => navigate('/')} className="btn-secondary w-full min-h-[44px]">
          ← Annuler
        </button>
      </div>
    </div>
  )
}

export default PublicQueue

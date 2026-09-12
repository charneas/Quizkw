import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { BlindtestSocket } from '../lib/blindtestSocket'

/**
 * Lobby blind-test (Story 2.1) : saisie de pseudo + bouton pour rejoindre,
 * puis liste des joueurs présents mise à jour en temps réel via
 * `game_state`. Atteint directement par URL avec un code (`/blindtest/:code`)
 * — pas de point d'entrée dans la navigation existante, hors scope de cette
 * story (cf. Code Map de la spec).
 */
export default function BlindTestLobby() {
  const { code = '' } = useParams<{ code: string }>()
  const [pseudo, setPseudo] = useState('')
  const [joined, setJoined] = useState(false)
  const [isJoining, setIsJoining] = useState(false)
  const [players, setPlayers] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const socketRef = useRef<BlindtestSocket | null>(null)

  useEffect(() => {
    return () => {
      socketRef.current?.disconnect()
    }
  }, [])

  function handleJoin() {
    // Garde contre un double-clic/double-appel avant que le premier socket
    // ait fini de se résoudre (joined ou error) — sans ça, un second appel
    // orpheline le socket précédent au lieu de le déconnecter (revue de
    // code).
    if (isJoining) {
      return
    }

    const trimmed = pseudo.trim()
    if (!trimmed) {
      setError('Merci de saisir un pseudo.')
      return
    }
    setError(null)
    setIsJoining(true)

    const socket = new BlindtestSocket()
    socketRef.current = socket
    socket.connect(code, trimmed, {
      onGameState: (payload) => {
        setPlayers(payload.players)
        setJoined(true)
        setIsJoining(false)
      },
      onClose: (event) => {
        setJoined(false)
        setIsJoining(false)
        // Codes custom serveur (spec-2-1-lobby-connexion-partie.md) : partie
        // introuvable, pseudo invalide, pseudo déjà pris.
        if (event.code === 4404) {
          setError('Partie introuvable.')
        } else if (event.code === 4400) {
          setError('Pseudo invalide.')
        } else if (event.code === 4409) {
          setError('Ce pseudo est déjà utilisé dans cette partie.')
        } else if (event.code !== 1000) {
          setError('Connexion perdue.')
        }
      },
    })
  }

  return (
    <div className="max-w-md mx-auto p-6 space-y-4">
      <h1 className="text-xl font-semibold">Blind test — Lobby {code}</h1>

      {error && <p className="text-sm text-red-500">{error}</p>}

      {!joined ? (
        <div className="flex gap-2">
          <input
            type="text"
            className="input-field flex-1"
            placeholder="Ton pseudo"
            value={pseudo}
            onChange={(e) => setPseudo(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleJoin()}
            disabled={isJoining}
          />
          <button className="btn-primary" onClick={handleJoin} disabled={isJoining}>
            Rejoindre
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-text-muted">Joueurs présents :</p>
          <ul className="space-y-1">
            {players.map((p) => (
              <li key={p} className="card px-3 py-2">
                {p}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

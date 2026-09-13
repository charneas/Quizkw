import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { BlindtestSocket } from '../lib/blindtestSocket'
import { createHiddenPlayer, type YouTubePlayer } from '../lib/youtubePlayer'
import { importBlindtestPlaylist } from '../services/api'
import type { BlindtestRevealPayload } from '../types'

/**
 * Lobby blind-test (Story 2.1) : saisie de pseudo + bouton pour rejoindre,
 * puis liste des joueurs présents mise à jour en temps réel via
 * `game_state`. Atteint directement par URL avec un code (`/blindtest/:code`)
 * — pas de point d'entrée dans la navigation existante, hors scope de cette
 * story (cf. Code Map de la spec).
 *
 * Story 2.2 : une fois `joined`, un formulaire d'import de playlist scopé
 * à cette partie/pseudo apparaît (mirroir du pattern pseudo-form ci-dessus :
 * champ + bouton + état d'erreur/succès inline).
 */
export default function BlindTestLobby() {
  const { code = '' } = useParams<{ code: string }>()
  const [pseudo, setPseudo] = useState('')
  const [joined, setJoined] = useState(false)
  const [isJoining, setIsJoining] = useState(false)
  const [players, setPlayers] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const socketRef = useRef<BlindtestSocket | null>(null)

  const [playlistUrl, setPlaylistUrl] = useState('')
  const [isImporting, setIsImporting] = useState(false)
  const [importError, setImportError] = useState<string | null>(null)
  const [importSuccess, setImportSuccess] = useState<string | null>(null)

  // Story 2.4 : phase/hôte poussés par `game_state` (jamais recalculés
  // côté client, epic-2-context.md) et morceau en cours reçu via
  // `round_started`.
  const [phase, setPhase] = useState('lobby')
  const [hostPseudo, setHostPseudo] = useState<string | null>(null)
  const [roundTrack, setRoundTrack] = useState<{ videoId: string; startSeconds: number } | null>(null)
  const playerContainerId = 'blindtest-hidden-player'

  // Story 2.5 : sélection multiple locale pour la devinette du round en
  // cours — remise à zéro à chaque nouveau round (`roundTrack` change).
  const [selectedPlayers, setSelectedPlayers] = useState<string[]>([])

  // Story 2.6 : reveal (propriétaire réel + score cumulatif de chaque
  // joueur présent) reçu à la clôture du round — remis à `null` à chaque
  // nouveau round tiré (`roundTrack` change), avant qu'un éventuel nouveau
  // `reveal` n'arrive pour ce round-là.
  const [reveal, setReveal] = useState<BlindtestRevealPayload | null>(null)

  useEffect(() => {
    setSelectedPlayers([])
    setReveal(null)
  }, [roundTrack])

  useEffect(() => {
    return () => {
      socketRef.current?.disconnect()
    }
  }, [])

  useEffect(() => {
    if (!roundTrack) return
    // Un vrai geste utilisateur a déjà eu lieu avant cet effet (le clic
    // "Rejoindre" du joueur, ou "Démarrer" côté hôte) — au-delà de ça,
    // l'autoplay reste dépendant du navigateur (cf. Boundaries de la spec,
    // hors scope d'être garanti ici).
    let cancelled = false
    let player: YouTubePlayer | null = null
    createHiddenPlayer(playerContainerId, roundTrack.videoId, roundTrack.startSeconds)
      .then((createdPlayer) => {
        if (cancelled) {
          // Le round a déjà changé / le composant a démonté pendant que la
          // création se résolvait : ne pas laisser ce lecteur orphelin
          // continuer à jouer (revue de code).
          createdPlayer.destroy()
          return
        }
        player = createdPlayer
      })
      .catch(() => {
        // Échec de chargement du lecteur : pas de message d'erreur dédié
        // dans cette story (hors scope), on laisse simplement la vue "round
        // en cours" affichée sans audio plutôt que de crasher.
      })
    return () => {
      cancelled = true
      player?.destroy()
    }
  }, [roundTrack])

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
        setPhase(payload.phase)
        setHostPseudo(payload.host_pseudo)
        setJoined(true)
        setIsJoining(false)
      },
      onRoundStarted: (payload) => {
        setRoundTrack({ videoId: payload.videoId, startSeconds: payload.startSeconds })
      },
      onReveal: (payload) => {
        setReveal(payload)
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

  function handleStartGame() {
    socketRef.current?.sendStartGame()
  }

  function toggleSelectedPlayer(p: string) {
    setSelectedPlayers((prev) => (prev.includes(p) ? prev.filter((name) => name !== p) : [...prev, p]))
  }

  function handleSubmitGuess() {
    if (selectedPlayers.length === 0) return
    socketRef.current?.sendGuess(selectedPlayers)
  }

  function handleImportPlaylist() {
    // Même garde anti-double-appel que handleJoin : un second clic avant
    // que le premier import ait fini de se résoudre ne doit pas partir en
    // parallèle (deux imports simultanés de la même URL, état d'erreur qui
    // s'écrase de façon imprévisible).
    if (isImporting) {
      return
    }

    const trimmedUrl = playlistUrl.trim()
    if (!trimmedUrl) {
      setImportError('Merci de coller un lien de playlist.')
      setImportSuccess(null)
      return
    }

    setImportError(null)
    setImportSuccess(null)
    setIsImporting(true)

    importBlindtestPlaylist(trimmedUrl, code, pseudo.trim())
      .then((playlist) => {
        setImportSuccess(`Playlist importée (${playlist.tracks.length} morceau${playlist.tracks.length > 1 ? 'x' : ''}).`)
        setPlaylistUrl('')
      })
      .catch((err: Error) => {
        setImportError(err.message || "Échec de l'import.")
      })
      .finally(() => {
        setIsImporting(false)
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
      ) : reveal ? (
        <div className="space-y-4">
          <p className="text-text-muted">
            Le morceau avait été importé par <strong>{reveal.owner_pseudo}</strong>.
          </p>
          <div className="space-y-2">
            <p className="text-text-muted">Scores cumulés :</p>
            <ul className="space-y-1">
              {Object.entries(reveal.scores)
                .sort(([, a], [, b]) => b - a)
                .map(([playerPseudo, score]) => (
                  <li key={playerPseudo} className="card px-3 py-2 flex justify-between">
                    <span>{playerPseudo}</span>
                    <span>{score}</span>
                  </li>
                ))}
            </ul>
          </div>
        </div>
      ) : phase === 'round_started' ? (
        <div className="space-y-4">
          <p className="text-text-muted">Round en cours — écoute l'extrait et devine qui l'a importé !</p>
          {/* Lecteur YouTube jamais affiché (blind test) : positionné
              hors-écran, pas en `display:none`, pour éviter les quirks de
              suppression d'autoplay sur un iframe caché (cf. Boundaries de
              la spec). */}
          <div
            id={playerContainerId}
            style={{ position: 'absolute', left: '-9999px', top: '-9999px', width: '1px', height: '1px' }}
          />

          {/* Story 2.5 : sélection multiple des joueurs présents — jamais de
              champ texte libre pour nommer une cible (FR8, cf. Boundaries de
              la spec). */}
          <div className="space-y-2">
            <p className="text-text-muted">Qui a importé ce morceau ? (plusieurs choix possibles)</p>
            <ul className="space-y-1">
              {players.map((p) => {
                const isSelected = selectedPlayers.includes(p)
                return (
                  <li key={p}>
                    <button
                      type="button"
                      className={`card px-3 py-2 w-full text-left ${isSelected ? 'ring-2 ring-primary' : ''}`}
                      onClick={() => toggleSelectedPlayer(p)}
                      aria-pressed={isSelected}
                    >
                      {p}
                    </button>
                  </li>
                )
              })}
            </ul>
            <button
              className="btn-primary w-full"
              onClick={handleSubmitGuess}
              disabled={selectedPlayers.length === 0}
            >
              Valider ma réponse
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
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

          {pseudo.trim() === hostPseudo && (
            <button className="btn-primary w-full" onClick={handleStartGame}>
              Démarrer la partie
            </button>
          )}

          <div className="space-y-2">
            <p className="text-text-muted">Importer ta playlist (Spotify, YouTube ou Apple Music) :</p>
            {importError && <p className="text-sm text-red-500">{importError}</p>}
            {importSuccess && <p className="text-sm text-green-600">{importSuccess}</p>}
            <div className="flex gap-2">
              <input
                type="text"
                className="input-field flex-1"
                placeholder="Lien de la playlist"
                value={playlistUrl}
                onChange={(e) => setPlaylistUrl(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleImportPlaylist()}
                disabled={isImporting}
              />
              <button className="btn-primary" onClick={handleImportPlaylist} disabled={isImporting}>
                Importer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

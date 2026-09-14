import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { BlindtestSocket } from '../lib/blindtestSocket'
import { createHiddenPlayer, type YouTubePlayer } from '../lib/youtubePlayer'
import { importBlindtestPlaylist } from '../services/api'
import Scoreboard from '../components/Scoreboard'
import type { BlindtestRevealPayload } from '../types'

// Story 4 (spec-blindtest-integration-ui) : hash déterministe d'un pseudo,
// utilisé comme `Team.id` (React key) pour le scoreboard réutilisé — stable
// d'un render à l'autre pour un même pseudo, contrairement à un index de
// tableau dont l'ordre dépend de `Object.keys` côté serveur.
function hashPseudo(pseudo: string): number {
  let hash = 0
  for (let i = 0; i < pseudo.length; i++) {
    hash = (hash * 31 + pseudo.charCodeAt(i)) | 0
  }
  return hash
}

/**
 * Lobby blind-test (Story 2.1) : saisie de pseudo + bouton pour rejoindre,
 * puis liste des joueurs présents mise à jour en temps réel via
 * `game_state`. Atteint par URL avec un code (`/blindtest/:code`), y compris
 * depuis la carte "Blindtest" de la home (spec-blindtest-integration-ui,
 * story 1).
 *
 * Story 2.2 : une fois `joined`, un formulaire d'import de playlist scopé
 * à cette partie/pseudo apparaît (mirroir du pattern pseudo-form ci-dessus :
 * champ + bouton + état d'erreur/succès inline).
 */
export default function BlindTestLobby() {
  const { code = '' } = useParams<{ code: string }>()
  const navigate = useNavigate()
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
  const [roundTrack, setRoundTrack] = useState<{
    videoId: string
    startSeconds: number
    title: string
    artist: string
  } | null>(null)
  const playerContainerId = 'blindtest-hidden-player'

  // Retour utilisateur (2026-09-14) : "pouvoir baisser le son de la page" —
  // volume (0-100) appliqué à chaque nouveau lecteur créé (`initialVolume`)
  // et répercuté en direct sur le lecteur courant via `playerRef` (le
  // slider ne doit pas attendre le prochain round pour avoir un effet).
  // `localStorage` (pas de capacité runtime ici) : préférence purement
  // locale au navigateur, pas besoin d'être partagée entre joueurs.
  const [volume, setVolume] = useState<number>(() => {
    try {
      const stored = window.localStorage.getItem('blindtest-volume')
      const parsed = stored ? Number(stored) : NaN
      return Number.isFinite(parsed) ? Math.min(100, Math.max(0, parsed)) : 100
    } catch {
      return 100
    }
  })
  const playerRef = useRef<YouTubePlayer | null>(null)

  function handleVolumeChange(next: number) {
    setVolume(next)
    playerRef.current?.setVolume(next)
    try {
      window.localStorage.setItem('blindtest-volume', String(next))
    } catch {
      // Stockage indisponible (navigation privée, quota) : le slider reste
      // fonctionnel pour la session en cours, seule la persistance est perdue.
    }
  }

  // Story 2.5 : sélection multiple locale pour la devinette du round en
  // cours — remise à zéro à chaque nouveau round (`roundTrack` change).
  const [selectedPlayers, setSelectedPlayers] = useState<string[]>([])

  // Story 2.6 : reveal (propriétaire réel + score cumulatif de chaque
  // joueur présent) reçu à la clôture du round — remis à `null` à chaque
  // nouveau round tiré (`roundTrack` change), avant qu'un éventuel nouveau
  // `reveal` n'arrive pour ce round-là.
  const [reveal, setReveal] = useState<BlindtestRevealPayload | null>(null)

  // Story 2.7 : classement final cumulatif, poussé dans `game_state` une
  // fois `phase === "ended"` — état terminal permanent (jamais remis à
  // `null` une fois reçu, contrairement à `reveal` qui se remet à zéro à
  // chaque nouveau round : `ended` ne connaît plus de round suivant).
  const [finalScores, setFinalScores] = useState<Record<string, number> | null>(null)

  // Story 4 (spec-blindtest-integration-ui) : score cumulatif courant,
  // mis à jour depuis chaque `game_state` — affiché en permanence pendant
  // le round (`round_started`), pas seulement au reveal/ended.
  const [scores, setScores] = useState<Record<string, number>>({})

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
    createHiddenPlayer(playerContainerId, roundTrack.videoId, roundTrack.startSeconds, volume)
      .then((createdPlayer) => {
        if (cancelled) {
          // Le round a déjà changé / le composant a démonté pendant que la
          // création se résolvait : ne pas laisser ce lecteur orphelin
          // continuer à jouer (revue de code).
          createdPlayer.destroy()
          return
        }
        player = createdPlayer
        playerRef.current = createdPlayer
      })
      .catch(() => {
        // Échec de chargement du lecteur : pas de message d'erreur dédié
        // dans cette story (hors scope), on laisse simplement la vue "round
        // en cours" affichée sans audio plutôt que de crasher.
      })
    return () => {
      cancelled = true
      player?.destroy()
      if (playerRef.current === player) {
        playerRef.current = null
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `volume` sert
    // uniquement de valeur initiale à la création : un changement de volume
    // seul ne doit pas recréer le lecteur (coupure audio), il passe par
    // `playerRef.current?.setVolume` dans `handleVolumeChange`.
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
        // Story 2.7 : `final_scores` n'arrive que sur ce `game_state`-là
        // (fin de partie automatique, ou (re)join pendant `ended`) — ne
        // touche `finalScores` que lorsqu'il est réellement présent, pour
        // ne jamais l'effacer sur un `game_state` intermédiaire (roster mis
        // à jour, `next_round`, ...) reçu après la fin de partie.
        if (payload.final_scores) {
          setFinalScores(payload.final_scores)
        }
        if (payload.scores) {
          setScores(payload.scores)
        }
        if (payload.phase === 'ended') {
          // Revue de code : sans ceci, le lecteur YouTube caché du dernier
          // round joué continue de tourner (audio) derrière l'écran de
          // classement final — le nettoyage du lecteur ne se déclenche que
          // sur un *changement* de `roundTrack`, jamais sur un simple
          // changement de `phase`.
          setRoundTrack(null)
        }
        setJoined(true)
        setIsJoining(false)
      },
      onRoundStarted: (payload) => {
        setRoundTrack({
          videoId: payload.videoId,
          startSeconds: payload.startSeconds,
          title: payload.title,
          artist: payload.artist,
        })
      },
      onReveal: (payload) => {
        setReveal(payload)
        // Retour utilisateur (2026-09-14) : "laisser un peu de temps entre 2
        // musiques" — sans ceci, le lecteur du round qui vient de se
        // terminer continuait de jouer par-dessus l'écran de reveal jusqu'à
        // ce que le round suivant démarre (aucun vrai silence entre deux
        // morceaux). En coupant l'audio dès le reveal, le silence dure
        // ensuite `REVEAL_DISPLAY_SECONDS` côté serveur (~6s) avant le
        // `round_started` suivant.
        setRoundTrack(null)
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

  function handleRestartGame() {
    socketRef.current?.sendRestartGame()
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
        const truncatedNote = playlist.truncated
          ? ` Playlist trop grosse : seuls les ${playlist.tracks.length} premiers morceaux ont été importés.`
          : ''
        setImportSuccess(
          `Playlist importée (${playlist.tracks.length} morceau${playlist.tracks.length > 1 ? 'x' : ''}).${truncatedNote}`,
        )
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
    // Story 6 (spec-blindtest-integration-ui) : même système de layout
    // plein écran que Home.tsx (min-h-screen flex) au lieu d'un conteneur
    // sans notion de hauteur — corrige le rendu "tout tassé en haut".
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="max-w-md w-full space-y-4">
        {/* Story 1 (spec-blindtest-integration-ui) : visible dans toutes les
            phases (partagent ce même retour racine) pour laisser un moyen de
            sortir de l'écran blindtest à tout moment. */}
        <button
          onClick={() => navigate('/')}
          className="text-text-muted text-sm hover:text-text underline"
        >
          ← Retour à l'accueil
        </button>

        {/* Story 6 : `text-accent` (magenta Neon Pit Lane) comme identité de
            section blindtest — usage restreint au texte/bordures, jamais en
            fond de bouton (DESIGN.md Do's/Don'ts : accent parcimonieux,
            jamais en fond de grande surface). */}
        <h1 className="text-xl font-semibold text-accent">Blind test — Lobby {code}</h1>

        {error && <p className="text-sm text-red-500">{error}</p>}

        {/* Bug corrigé (page blanche en prod, 2026-09-13) : ce conteneur
            n'était monté que pendant `phase === 'round_started'`, alors que
            le lecteur YouTube lui-même (créé/détruit selon `roundTrack`,
            pas `phase`) reste actif après la fin du round — React démontait
            le conteneur sous les pieds du lecteur encore vivant, et
            `player.destroy()` plantait ensuite sur un noeud DOM déjà
            disparu (`NotFoundError: Failed to execute 'removeChild'`),
            sans error boundary pour l'amortir. Toujours monté maintenant :
            seul le cycle de vie impératif du lecteur (`createHiddenPlayer`/
            `destroy`) possède ce noeud, React ne le monte/démonte plus. */}
        <div
          id={playerContainerId}
          style={{ position: 'absolute', left: '-9999px', top: '-9999px', width: '1px', height: '1px' }}
        />

        {/* Retour utilisateur (2026-09-14, ajusté 2026-09-14) : "pouvoir
            baisser le son de la page" — inutile sur l'écran de lobby (avant
            que la partie démarre, aucun lecteur n'existe encore) : affiché
            seulement une fois de la musique potentiellement en cours
            (round_started/reveal/next_round), jamais en `lobby` ni `ended`. */}
        {joined && phase !== 'lobby' && phase !== 'ended' && (
          <div className="flex items-center gap-2">
            <label htmlFor="blindtest-volume" className="text-text-muted text-sm shrink-0">
              🔊 Volume
            </label>
            <input
              id="blindtest-volume"
              type="range"
              min={0}
              max={100}
              value={volume}
              onChange={(e) => handleVolumeChange(Number(e.target.value))}
              className="flex-1"
            />
          </div>
        )}

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
        ) : phase === 'ended' && finalScores ? (
          <div className="space-y-4">
            <p className="text-text-muted">Partie terminée — classement final :</p>
            <ul className="space-y-1">
              {Object.entries(finalScores)
                .sort(([, a], [, b]) => b - a)
                .map(([playerPseudo, score], index) => (
                  <li key={playerPseudo} className="card px-3 py-2 flex justify-between">
                    <span>
                      {index + 1}. {playerPseudo}
                    </span>
                    <span>{score}</span>
                  </li>
                ))}
            </ul>
            {/* Retour utilisateur (2026-09-14) : rejouer sans quitter le
                salon (même code, mêmes playlists déjà importées) — réservé à
                l'hôte, même garde d'affichage que "Démarrer la partie". */}
            {pseudo.trim() === hostPseudo && (
              <button className="btn-primary w-full" onClick={handleRestartGame}>
                Rejouer dans ce salon
              </button>
            )}
          </div>
        ) : phase === 'next_round' ? (
          // Story 2.7 : bref indicateur transitoire entre le `game_state
          // {phase: next_round}` et le `round_started` qui suit — purement
          // informatif, aucune action joueur possible ici (NFR5).
          <p className="text-text-muted">Round suivant...</p>
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
                  .map(([playerPseudo, score]) => {
                    // Optional-chaining défensif (revue de code) : un payload
                    // `reveal` sans `deltas` (nice-to-have, ne doit jamais faire
                    // planter l'écran) dégrade silencieusement à 0 plutôt que de
                    // lever une TypeError sur un accès direct.
                    const delta = reveal.deltas?.[playerPseudo] ?? 0
                    return (
                      <li key={playerPseudo} className="card px-3 py-2 flex justify-between items-center">
                        <span>{playerPseudo}</span>
                        <span className="flex items-center gap-2">
                          {/* Story 5 (spec-blindtest-integration-ui, nice-to-have) :
                              clé basée sur `roundTrack` (identifiant unique du
                              round, stable pendant tout l'affichage du reveal)
                              plutôt que sur `delta` — deux rounds consécutifs
                              avec le même delta (ex: 0 puis 0) ne rejoueraient
                              pas l'animation `.animate-fade-in` sinon (déjà
                              respectueuse de prefers-reduced-motion). */}
                          <span
                            key={`${playerPseudo}-${roundTrack?.videoId ?? ''}`}
                            className={`animate-fade-in text-sm font-semibold ${
                              delta > 0 ? 'text-success' : delta < 0 ? 'text-danger' : 'text-text-muted'
                            }`}
                          >
                            {delta > 0 ? `+${delta}` : delta}
                          </span>
                          <span>{score}</span>
                        </span>
                      </li>
                    )
                  })}
              </ul>
            </div>
          </div>
        ) : phase === 'round_started' ? (
          <div className="space-y-4">
            <p className="text-text-muted">Round en cours — écoute l'extrait et devine qui l'a importé !</p>
            {/* Story 3 (spec-blindtest-integration-ui) : le titre/artiste ne
                spoile pas la devinette (deviner la playlist d'origine, jamais
                le morceau) — affichés en permanence pendant toute la durée du
                round. */}
            {roundTrack && (
              <p className="font-semibold">
                {roundTrack.title} — {roundTrack.artist}
              </p>
            )}

            {/* Story 2.5 : sélection multiple des joueurs présents — jamais de
                champ texte libre pour nommer une cible (FR8, cf. Boundaries de
                la spec). */}
            <div className="space-y-2">
              <p className="text-text-muted">Qui a ajouté ce morceau à sa playlist ? (plusieurs choix possibles)</p>
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

            {/* Story 4 (spec-blindtest-integration-ui) : scoreboard visible
                pendant tout le round, pas seulement au reveal/ended. Placé
                en bas (retour utilisateur) : en haut, avant la devinette,
                son rôle n'était pas clair. Merge du roster complet
                (`players`) avec les scores partiels connus (`score_store`
                n'a que les pseudos déjà scorés) pour que chaque joueur
                présent apparaisse, à 0 par défaut. `Scoreboard.tsx` ne lit
                que `.id`/`.name`/`.score` — les autres champs `Team` sont
                des valeurs de remplissage sans effet sur le rendu. */}
            <Scoreboard
              teams={players.map((p) => ({
                // `Team.id` sert de clé React dans `Scoreboard.tsx` (pas de
                // vrai id numérique côté blindtest, pas de `Player` DB table).
                // Dérivé du pseudo (hash stable), pas de l'index dans
                // `players` : `players` vient de `Object.keys` du dict de
                // connexions côté serveur, dont l'ordre bouge à chaque
                // (re)connexion — un id basé sur l'index ferait remonter
                // toute la liste sans raison à chaque reconnexion d'un tiers.
                id: hashPseudo(p),
                name: p,
                score: scores[p] ?? 0,
                game_session_id: 0,
                players: [],
              }))}
            />
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
              <p className="text-text-muted">Importer ta playlist (Deezer ou YouTube) :</p>
              {importError && <p className="text-sm text-red-500">{importError}</p>}
              {importSuccess && <p className="text-sm text-green-600">{importSuccess}</p>}
              {isImporting && <p className="text-sm text-text-muted">Import en cours… ça peut prendre quelques secondes.</p>}
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
                  {isImporting ? 'Import…' : 'Importer'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

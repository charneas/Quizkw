/**
 * Chargement/wrapper minimal de l'API YouTube IFrame Player (Story 2.4).
 *
 * Aucune lecture vidéo n'existait auparavant dans ce dépôt — ce module est
 * entièrement nouveau (cf. Code Map de spec-2-4-lancement-round.md). Il ne
 * couvre que ce dont cette story a besoin : charger le script une seule
 * fois (singleton) et créer un lecteur caché qui démarre à un offset donné.
 * Jamais de SDK Spotify/Apple Music ici — la lecture passe exclusivement
 * par YouTube (NFR d'epic-2-context.md).
 */

// Déclarations minimales du sous-ensemble de l'API globale `YT` utilisé ici
// (pas de paquet `@types/youtube` dans ce projet) — volontairement étroit,
// pas une reproduction complète de l'API IFrame Player.
declare global {
  interface Window {
    YT?: {
      Player: new (elementId: string, options: YouTubePlayerOptions) => YouTubePlayer
    }
    onYouTubeIframeAPIReady?: () => void
  }
}

interface YouTubePlayerOptions {
  videoId: string
  host?: string
  playerVars?: Record<string, number | string>
  events?: {
    onReady?: (event: { target: YouTubePlayer }) => void
  }
}

export interface YouTubePlayer {
  seekTo(seconds: number, allowSeekAhead: boolean): void
  playVideo(): void
  setVolume(volume: number): void
  destroy(): void
}

const IFRAME_API_URL = 'https://www.youtube.com/iframe_api'

// Singleton module-level : une seule injection du script/une seule promesse
// de chargement, même si plusieurs rounds/composants appellent cette
// fonction au fil d'une session.
let apiReadyPromise: Promise<void> | null = null

function loadIframeApi(): Promise<void> {
  if (apiReadyPromise) {
    return apiReadyPromise
  }

  apiReadyPromise = new Promise((resolve, reject) => {
    if (window.YT?.Player) {
      resolve()
      return
    }

    // `onYouTubeIframeAPIReady` est un callback global appelé par le script
    // YouTube lui-même une fois prêt — on ne l'écrase pas s'il existe déjà
    // (autre appelant potentiel), on chaîne dessus.
    const previous = window.onYouTubeIframeAPIReady
    window.onYouTubeIframeAPIReady = () => {
      previous?.()
      resolve()
    }

    const script = document.createElement('script')
    script.src = IFRAME_API_URL
    script.onerror = () => {
      // Échec de chargement du script (réseau, bloqueur de pub/tracker,
      // hors-ligne) : rejeter plutôt que de laisser la promesse en attente
      // indéfiniment, et réinitialiser le singleton pour qu'un appel
      // ultérieur puisse retenter au lieu de rester bloqué sur cette même
      // promesse cassée pour le reste de la session (revue de code).
      apiReadyPromise = null
      reject(new Error("Échec du chargement du script de l'API YouTube IFrame."))
    }
    document.head.appendChild(script)
  })

  return apiReadyPromise
}

/**
 * Crée un lecteur YouTube IFrame Player dans le conteneur `containerId` et
 * démarre la lecture à `startSeconds`. Le conteneur doit déjà exister dans
 * le DOM (positionné hors-écran par l'appelant — jamais `display:none`,
 * pour éviter les quirks de suppression d'autoplay sur un iframe caché —
 * cf. Boundaries & Constraints de la spec) ; ce module ne gère que la
 * création/le positionnement du lecteur lui-même, pas le style de son
 * conteneur.
 */
export function createHiddenPlayer(
  containerId: string,
  videoId: string,
  startSeconds: number,
  // Retour utilisateur (2026-09-14) : "pouvoir baisser le son de la page" —
  // volume initial (0-100) appliqué dès la création du lecteur, avant même
  // `onReady`/`playVideo`, pour qu'aucune frame ne joue au volume par défaut
  // de l'API (100) le temps qu'un appelant rappelle `setVolume` après coup.
  initialVolume = 100,
): Promise<YouTubePlayer> {
  return loadIframeApi().then(
    () =>
      new Promise<YouTubePlayer>((resolve) => {
        const YTApi = window.YT
        if (!YTApi) {
          throw new Error("L'API YouTube IFrame n'a pas pu être chargée.")
        }
        new YTApi.Player(containerId, {
          videoId,
          // Bruit console réduit (retour utilisateur, 2026-09-13) :
          // `host` en mode "confidentialité renforcée" coupe une partie du
          // tracking/cookies par défaut de youtube.com ; `origin` corrige le
          // warning "postMessage target origin does not match recipient
          // window's origin" (le widget IFrame a besoin de connaître l'URL
          // hôte pour cibler correctement ses messages) ; `rel`/
          // `iv_load_policy`/`modestbranding` désactivent des fonctionnalités
          // UI inutiles ici (lecteur toujours caché) qui déclenchent elles
          // aussi des appels réseau annexes. Le reste du bruit visible
          // (`ERR_BLOCKED_BY_CLIENT`) vient d'un bloqueur de pub côté
          // navigateur, pas de ce code — rien à corriger ici pour ça.
          host: 'https://www.youtube-nocookie.com',
          playerVars: {
            autoplay: 1,
            start: Math.max(0, Math.floor(startSeconds)),
            controls: 0,
            disablekb: 1,
            rel: 0,
            iv_load_policy: 3,
            modestbranding: 1,
            origin: window.location.origin,
          },
          events: {
            onReady: (event) => {
              event.target.setVolume(initialVolume)
              event.target.seekTo(startSeconds, true)
              event.target.playVideo()
              resolve(event.target)
            },
          },
        })
      }),
  )
}

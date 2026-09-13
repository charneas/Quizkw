import type {
  BlindtestGameStatePayload,
  BlindtestRevealPayload,
  BlindtestRoundStartedPayload,
  BlindtestWsEnvelope,
} from '../types'

/**
 * Client WS minimal pour le lobby blind-test (Story 2.1) : connexion,
 * envoi du `join {pseudo}`, abonnement à `game_state`. Mirroir de
 * l'enveloppe `{type, payload, ts}` du backend (`main_blindtest.py`) — le
 * client ne renseigne jamais `ts` lui-même sur ses propres messages, seul
 * le serveur l'horodate à réception (NFR5, cf. epic-2-context.md).
 */
export class BlindtestSocket {
  private ws: WebSocket | null = null

  /** Construit l'URL `ws(s)://.../api/blindtest/games/{code}/ws` — passe
   * par le même proxy same-origin `/api` que le reste du frontend (dev:
   * vite.config.ts avec `ws: true`, prod: Nginx), pas d'appel cross-origin. */
  private buildUrl(code: string): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}/api/blindtest/games/${encodeURIComponent(code)}/ws`
  }

  connect(
    code: string,
    pseudo: string,
    handlers: {
      onGameState?: (payload: BlindtestGameStatePayload) => void
      onRoundStarted?: (payload: BlindtestRoundStartedPayload) => void
      onReveal?: (payload: BlindtestRevealPayload) => void
      onClose?: (event: CloseEvent) => void
      onError?: (event: Event) => void
    } = {},
  ): void {
    const ws = new WebSocket(this.buildUrl(code))
    this.ws = ws

    ws.onopen = () => {
      this.send('join', { pseudo })
    }

    ws.onmessage = (event: MessageEvent) => {
      let envelope: BlindtestWsEnvelope
      try {
        envelope = JSON.parse(event.data)
      } catch {
        return
      }
      if (envelope.type === 'game_state' && handlers.onGameState) {
        handlers.onGameState(envelope.payload as BlindtestGameStatePayload)
      } else if (envelope.type === 'round_started' && handlers.onRoundStarted) {
        handlers.onRoundStarted(envelope.payload as BlindtestRoundStartedPayload)
      } else if (envelope.type === 'reveal' && handlers.onReveal) {
        handlers.onReveal(envelope.payload as BlindtestRevealPayload)
      }
    }

    ws.onclose = (event) => handlers.onClose?.(event)
    ws.onerror = (event) => handlers.onError?.(event)
  }

  send(type: string, payload: unknown): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return
    // `ts` n'est jamais renseigné côté client : le serveur l'horodate à
    // réception (NFR5) — un `ts` client ne ferait que se faire ignorer.
    const envelope: BlindtestWsEnvelope = { type, payload }
    this.ws.send(JSON.stringify(envelope))
  }

  /** Déclenche le lancement du round (Story 2.4) — n'a d'effet que si
   * l'appelant est bien `host_pseudo` et que la partie est en `lobby` ;
   * sinon le serveur ignore silencieusement (défense en profondeur, le
   * bouton n'est déjà montré qu'à l'hôte). */
  sendStartGame(): void {
    this.send('start_game', {})
  }

  /** Envoie la devinette du joueur (Story 2.5) : sélection multiple de
   * pseudos parmi les joueurs présents, jamais de texte libre (FR8). Une
   * resoumission avant la fin du round remplace la précédente côté
   * serveur (AC3) — ce client n'a rien de spécial à faire pour ça, il
   * suffit de renvoyer le même message type. */
  sendGuess(targetPlayerIds: string[]): void {
    this.send('guess_submitted', { target_player_ids: targetPlayerIds })
  }

  disconnect(): void {
    this.ws?.close()
    this.ws = null
  }
}

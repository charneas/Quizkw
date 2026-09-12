import type { BlindtestGameStatePayload, BlindtestWsEnvelope } from '../types'

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

  disconnect(): void {
    this.ws?.close()
    this.ws = null
  }
}

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { BlindtestSocket } from './blindtestSocket'

/**
 * Mock minimal de `WebSocket` : capture l'URL/les messages envoyés et permet
 * de déclencher `onopen`/`onmessage`/`onclose` manuellement depuis les
 * tests, sans dépendre d'un vrai serveur. Pas de convention WS existante
 * ailleurs dans le repo (`Home.test.tsx`/`Propositions.test.tsx` ne testent
 * que du HTTP via `services/api`), donc mock local ad hoc.
 */
class MockWebSocket {
  static instances: MockWebSocket[] = []
  static OPEN = 1

  url: string
  readyState = MockWebSocket.OPEN
  sent: string[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send(data: string): void {
    this.sent.push(data)
  }

  close(): void {
    this.readyState = 3
  }

  triggerOpen(): void {
    this.onopen?.()
  }

  triggerMessage(data: unknown): void {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent)
  }

  triggerClose(code: number, reason = ''): void {
    this.onclose?.({ code, reason } as CloseEvent)
  }
}

describe('BlindtestSocket', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('envoie un message join avec le pseudo dès la connexion ouverte', () => {
    const socket = new BlindtestSocket()
    socket.connect('ABC123', 'Alice')

    const ws = MockWebSocket.instances[0]
    expect(ws).toBeDefined()
    ws.triggerOpen()

    expect(ws.sent).toHaveLength(1)
    const envelope = JSON.parse(ws.sent[0])
    expect(envelope.type).toBe('join')
    expect(envelope.payload).toEqual({ pseudo: 'Alice' })
  })

  it('appelle onGameState quand un message game_state est reçu', () => {
    const socket = new BlindtestSocket()
    const onGameState = vi.fn()
    socket.connect('ABC123', 'Alice', { onGameState })

    const ws = MockWebSocket.instances[0]
    ws.triggerOpen()
    ws.triggerMessage({ type: 'game_state', payload: { players: ['Alice'] }, ts: '2026-01-01T00:00:00Z' })

    expect(onGameState).toHaveBeenCalledWith({ players: ['Alice'] })
  })

  it('appelle onClose avec le code et la raison de fermeture', () => {
    const socket = new BlindtestSocket()
    const onClose = vi.fn()
    socket.connect('ZZZZZZ', 'Alice', { onClose })

    const ws = MockWebSocket.instances[0]
    ws.triggerClose(4404, 'Partie introuvable')

    expect(onClose).toHaveBeenCalledWith(expect.objectContaining({ code: 4404 }))
  })
})

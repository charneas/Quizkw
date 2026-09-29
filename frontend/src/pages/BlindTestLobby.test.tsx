import { render, screen, fireEvent, act } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import BlindTestLobby from './BlindTestLobby'
import type { BlindtestGameStatePayload, BlindtestRoundStartedPayload } from '../types'

type Handlers = {
  onGameState?: (payload: BlindtestGameStatePayload) => void
  onRoundStarted?: (payload: BlindtestRoundStartedPayload) => void
}

// Socket mocké : capture les handlers passés à `connect` pour simuler les
// messages serveur, et espionne `sendGuess` (spec-blindtest-late-guess-round-guard).
const socketMock = vi.hoisted(() => ({
  handlers: {} as Handlers,
  sendGuess: vi.fn(),
}))

vi.mock('../lib/blindtestSocket', () => ({
  BlindtestSocket: class {
    connect(_code: string, _pseudo: string, handlers: Handlers) {
      socketMock.handlers = handlers
    }
    sendGuess = socketMock.sendGuess
    sendStartGame = vi.fn()
    sendRestartGame = vi.fn()
    disconnect = vi.fn()
  },
}))

vi.mock('../lib/youtubePlayer', () => ({
  createHiddenPlayer: vi.fn(() => Promise.resolve({ destroy: vi.fn(), setVolume: vi.fn() })),
}))

function renderLobby(code = 'ABC123') {
  return render(
    <MemoryRouter initialEntries={[`/blindtest/${code}`]}>
      <Routes>
        <Route path="/blindtest/:code" element={<BlindTestLobby />} />
      </Routes>
    </MemoryRouter>
  )
}

function join() {
  fireEvent.change(screen.getByPlaceholderText('Ton pseudo'), { target: { value: 'Alice' } })
  fireEvent.click(screen.getByRole('button', { name: 'Rejoindre' }))
}

function roundStartedState(extra: Partial<BlindtestGameStatePayload> = {}): BlindtestGameStatePayload {
  return { players: ['Alice', 'Bob'], phase: 'round_started', host_pseudo: 'Alice', ...extra }
}

function roundStarted(trackId: number): BlindtestRoundStartedPayload {
  return { videoId: `vid-${trackId}`, startSeconds: 0, title: 'Titre', artist: 'Artiste', trackId }
}

function guessBob() {
  fireEvent.click(screen.getByRole('button', { name: 'Bob' }))
  fireEvent.click(screen.getByRole('button', { name: 'Valider ma réponse' }))
}

describe('BlindTestLobby — devinette liée au round (spec-blindtest-late-guess-round-guard)', () => {
  beforeEach(() => {
    socketMock.handlers = {}
    socketMock.sendGuess.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('un joignant en cours de round envoie le track_id du game_state de join', () => {
    renderLobby()
    join()
    act(() => socketMock.handlers.onGameState?.(roundStartedState({ track_id: 5 })))

    guessBob()

    expect(socketMock.sendGuess).toHaveBeenCalledWith(5, ['Bob'])
  })

  it('envoie le trackId du round_started', () => {
    renderLobby()
    join()
    act(() => socketMock.handlers.onGameState?.(roundStartedState()))
    act(() => socketMock.handlers.onRoundStarted?.(roundStarted(9)))

    guessBob()

    expect(socketMock.sendGuess).toHaveBeenCalledWith(9, ['Bob'])
  })

  it('un nouveau round_started remplace le trackId précédent', () => {
    renderLobby()
    join()
    act(() => socketMock.handlers.onGameState?.(roundStartedState()))
    act(() => socketMock.handlers.onRoundStarted?.(roundStarted(9)))
    act(() => socketMock.handlers.onRoundStarted?.(roundStarted(10)))

    guessBob()

    expect(socketMock.sendGuess).toHaveBeenCalledTimes(1)
    expect(socketMock.sendGuess).toHaveBeenCalledWith(10, ['Bob'])
  })
})

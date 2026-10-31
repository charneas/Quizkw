import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import BlindTestLobby from './BlindTestLobby'
import * as api from '../services/api'
import { createHiddenPlayer } from '../lib/youtubePlayer'
import type {
  BlindtestAnswerResultPayload,
  BlindtestClassicRevealPayload,
  BlindtestGameStatePayload,
  BlindtestRoundStartedPayload,
  BlindtestRoundVoidedPayload,
  BlindtestScoresUpdatedPayload,
  BlindtestStartRefusedPayload,
} from '../types'

type Handlers = {
  onGameState?: (payload: BlindtestGameStatePayload) => void
  onRoundStarted?: (payload: BlindtestRoundStartedPayload) => void
  onReveal?: (payload: BlindtestClassicRevealPayload) => void
  onAnswerResult?: (payload: BlindtestAnswerResultPayload) => void
  onScoresUpdated?: (payload: BlindtestScoresUpdatedPayload) => void
  onRoundVoided?: (payload: BlindtestRoundVoidedPayload) => void
  onStartRefused?: (payload: BlindtestStartRefusedPayload) => void
}

const socketMock = vi.hoisted(() => ({
  handlers: {} as Handlers,
  sendAnswer: vi.fn(),
  sendStartGame: vi.fn(),
  sendVideoError: vi.fn(),
}))

vi.mock('../lib/blindtestSocket', () => ({
  BlindtestSocket: class {
    connect(_code: string, _pseudo: string, handlers: Handlers) {
      socketMock.handlers = handlers
    }
    sendAnswer = socketMock.sendAnswer
    sendStartGame = socketMock.sendStartGame
    sendVideoError = socketMock.sendVideoError
    sendGuess = vi.fn()
    sendRestartGame = vi.fn()
    disconnect = vi.fn()
  },
}))

vi.mock('../lib/youtubePlayer', () => ({
  createHiddenPlayer: vi.fn(() => Promise.resolve({ destroy: vi.fn(), setVolume: vi.fn() })),
}))

function state(extra: Partial<BlindtestGameStatePayload> = {}): BlindtestGameStatePayload {
  return { players: ['Alice', 'Bob'], phase: 'lobby', host_pseudo: 'Alice', mode: 'classic', ...extra }
}

function joinAs(pseudo: string) {
  render(
    <MemoryRouter initialEntries={['/blindtest/ABC123']}>
      <Routes>
        <Route path="/blindtest/:code" element={<BlindTestLobby />} />
      </Routes>
    </MemoryRouter>
  )
  fireEvent.change(screen.getByPlaceholderText('Ton pseudo'), { target: { value: pseudo } })
  fireEvent.click(screen.getByRole('button', { name: 'Rejoindre' }))
}

function startRound(trackId = 7) {
  act(() => socketMock.handlers.onGameState?.(state({ phase: 'round_started' })))
  act(() =>
    socketMock.handlers.onRoundStarted?.({ videoId: 'vid', startSeconds: 12, trackId, durationSeconds: 20 })
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  socketMock.handlers = {}
  vi.spyOn(api, 'getBlindtestSource').mockResolvedValue({ name: null, playable_count: 0, checking: false })
  vi.spyOn(api, 'getBlindtestPresets').mockResolvedValue([
    { slug: 'hits-80', name: 'Hits années 80', track_count: 100 },
  ])
})

describe('BlindTestLobby — lobby classique', () => {
  it('propose les playlists préparées à l’hôte et bloque le départ sans playlist', async () => {
    joinAs('Alice')
    act(() => socketMock.handlers.onGameState?.(state()))

    expect(await screen.findByRole('button', { name: /Hits années 80/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Démarrer la partie' })).toBeDisabled()
    expect(screen.queryByPlaceholderText('Lien de la playlist')).toBeInTheDocument()
  })

  it('ne montre aucun contrôle à un joueur qui n’est pas hôte', async () => {
    joinAs('Bob')
    act(() => socketMock.handlers.onGameState?.(state()))

    expect(await screen.findByText("L'hôte choisit la playlist…")).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Démarrer la partie' })).not.toBeInTheDocument()
    expect(api.getBlindtestPresets).not.toHaveBeenCalled()
  })

  it('choisit un preset puis affiche le compte de titres jouables', async () => {
    const select = vi
      .spyOn(api, 'selectBlindtestPreset')
      .mockResolvedValue({ name: 'Hits années 80', playable_count: 100, checking: false })
    joinAs('Alice')
    act(() => socketMock.handlers.onGameState?.(state()))

    vi.mocked(api.getBlindtestSource).mockResolvedValue({ name: 'Hits années 80', playable_count: 100, checking: false })
    fireEvent.click(await screen.findByRole('button', { name: /Hits années 80/ }))

    expect(select).toHaveBeenCalledWith('ABC123', 'hits-80', 'Alice')
    expect(await screen.findByText('100 titres jouables')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Hits années 80/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('100 titres')).toBeInTheDocument()
  })

  it('prévient l’hôte quand il demande plus de titres que disponibles', async () => {
    vi.mocked(api.getBlindtestSource).mockResolvedValue({ name: 'Ma liste', playable_count: 30, checking: false })
    joinAs('Alice')
    act(() => socketMock.handlers.onGameState?.(state()))
    await screen.findByText('30 titres jouables')

    fireEvent.change(screen.getByLabelText(/Nombre de titres/), { target: { value: '50' } })
    expect(screen.getByText('50 titres demandés, 30 jouables : la partie fera 30 titres.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Démarrer la partie' }))
    expect(socketMock.sendStartGame).toHaveBeenCalledWith(50)
  })

  it('signale un pot trop petit une fois la vérification finie, même avec des doublons', async () => {
    vi.mocked(api.getBlindtestSource).mockResolvedValue({ name: 'Ma liste', playable_count: 4, checking: false })
    joinAs('Alice')
    act(() => socketMock.handlers.onGameState?.(state()))

    expect(await screen.findByText(/au moins 10 titres/)).toBeInTheDocument()
    expect(screen.queryByText(/vérification en cours/)).not.toBeInTheDocument()
  })

  it('attend la fin de la vérification avant de signaler un pot trop petit', async () => {
    const source = { name: 'Ma liste', playable_count: 4, checking: true }
    vi.mocked(api.getBlindtestSource).mockResolvedValue(source)
    joinAs('Alice')
    act(() => socketMock.handlers.onGameState?.(state()))

    expect(await screen.findByText(/vérification en cours/)).toBeInTheDocument()
    expect(screen.queryByText(/au moins 10 titres/)).not.toBeInTheDocument()
  })

  it('efface le refus au retour au lobby', async () => {
    joinAs('Alice')
    act(() => socketMock.handlers.onGameState?.(state()))
    await screen.findByRole('button', { name: /Hits années 80/ })
    act(() => socketMock.handlers.onStartRefused?.({ reason: 'pool_too_small', message: 'Seulement 3 titres' }))
    act(() => socketMock.handlers.onGameState?.(state()))

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('refuse localement un nombre de titres hors bornes', async () => {
    vi.mocked(api.getBlindtestSource).mockResolvedValue({ name: 'Ma liste', playable_count: 30, checking: false })
    joinAs('Alice')
    act(() => socketMock.handlers.onGameState?.(state()))
    await screen.findByText('30 titres jouables')

    fireEvent.change(screen.getByLabelText(/Nombre de titres/), { target: { value: '9' } })
    expect(screen.getByRole('button', { name: 'Démarrer la partie' })).toBeDisabled()
  })

  it('affiche le motif d’un start_refused', async () => {
    joinAs('Alice')
    act(() => socketMock.handlers.onGameState?.(state()))
    act(() => socketMock.handlers.onStartRefused?.({ reason: 'pool_too_small', message: 'Seulement 3 titres' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Seulement 3 titres')
  })
})

describe('BlindTestLobby — round classique', () => {
  it('n’affiche ni champ de pseudo à cocher ni titre, et envoie la réponse avec le trackId', () => {
    joinAs('Alice')
    startRound(7)

    expect(screen.queryByRole('button', { name: 'Valider ma réponse' })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Ta réponse'), { target: { value: ' daft punk ' } })
    fireEvent.keyDown(screen.getByLabelText('Ta réponse'), { key: 'Enter' })

    expect(socketMock.sendAnswer).toHaveBeenCalledWith(7, 'daft punk')
    expect(screen.getByLabelText('Ta réponse')).toHaveValue('')
  })

  it('montre ce qui est trouvé et garde le champ pour le reste', () => {
    joinAs('Alice')
    startRound(7)
    act(() =>
      socketMock.handlers.onAnswerResult?.({ track_id: 7, added: ['title'], found: ['title'], points: 100 })
    )

    expect(screen.getByText('✓ Titre trouvé')).toBeInTheDocument()
    expect(screen.getByText('Artiste')).toBeInTheDocument()
    expect(screen.getByLabelText('Ta réponse')).toBeInTheDocument()
  })

  it('ne compte pas comme raté le rejeu après une reconnexion', () => {
    joinAs('Alice')
    startRound(7)
    act(() =>
      socketMock.handlers.onAnswerResult?.({ track_id: 7, added: [], found: ['title'], points: 0, restored: true })
    )

    expect(screen.getByText('✓ Titre trouvé')).toBeInTheDocument()
    expect(screen.getByRole('status', { name: '' })).toHaveClass('invisible')
  })

  it('retire le champ quand tout est trouvé', () => {
    joinAs('Alice')
    startRound(7)
    act(() =>
      socketMock.handlers.onAnswerResult?.({ track_id: 7, added: ['title', 'artist'], found: ['artist', 'title'], points: 200 })
    )

    expect(screen.queryByLabelText('Ta réponse')).not.toBeInTheDocument()
  })

  it('ignore un résultat arrivé après le changement de round', () => {
    joinAs('Alice')
    startRound(7)
    startRound(8)
    act(() =>
      socketMock.handlers.onAnswerResult?.({ track_id: 7, added: ['title'], found: ['title'], points: 100 })
    )

    expect(screen.queryByText('✓ Titre trouvé')).not.toBeInTheDocument()
  })

  it('met le score à jour en direct', () => {
    joinAs('Alice')
    startRound(7)
    act(() => socketMock.handlers.onScoresUpdated?.({ scores: { Alice: 160 } }))

    expect(screen.getByText('160')).toBeInTheDocument()
  })

  it('compte à rebours depuis le temps déjà écoulé pour un joignant', () => {
    joinAs('Bob')
    act(() => socketMock.handlers.onGameState?.(state({ phase: 'round_started' })))
    act(() =>
      socketMock.handlers.onRoundStarted?.({
        videoId: 'vid', startSeconds: 12, trackId: 7, durationSeconds: 20, elapsedSeconds: 15,
      })
    )

    expect(screen.getByRole('timer')).toHaveTextContent('5')
  })

  it('signale au serveur une vidéo que le lecteur refuse de jouer', async () => {
    joinAs('Alice')
    startRound(7)

    await waitFor(() => expect(createHiddenPlayer).toHaveBeenCalled())
    const onError = vi.mocked(createHiddenPlayer).mock.calls[0][4]
    act(() => onError?.(150))

    expect(socketMock.sendVideoError).toHaveBeenCalledWith(7, 150)
  })

  it('annonce un round annulé puis reprend au titre suivant', () => {
    joinAs('Alice')
    startRound(7)
    act(() => socketMock.handlers.onRoundVoided?.({ scores: {} }))
    expect(screen.getByText(/Cette vidéo est bloquée/)).toBeInTheDocument()

    startRound(8)
    expect(screen.queryByText(/Cette vidéo est bloquée/)).not.toBeInTheDocument()
    expect(screen.getByLabelText('Ta réponse')).toBeInTheDocument()
  })
})

describe('BlindTestLobby — reveal classique', () => {
  const reveal = {
    title: 'One More Time',
    artist: 'Daft Punk',
    deltas: { Alice: 160, Bob: 0 },
    scores: { Alice: 160, Bob: 0 },
  }

  it('affiche la réponse et les points du round, et garde l’écran jusqu’au round suivant', () => {
    joinAs('Alice')
    startRound(7)
    act(() => socketMock.handlers.onReveal?.(reveal))

    expect(screen.getByText('One More Time')).toBeInTheDocument()
    expect(screen.getByText('Daft Punk')).toBeInTheDocument()
    expect(screen.getByText('+160')).toBeInTheDocument()
    expect(screen.queryByLabelText('Ta réponse')).not.toBeInTheDocument()

    startRound(8)
    expect(screen.queryByText('One More Time')).not.toBeInTheDocument()
  })

  it('revient au lobby classique après Rejouer', () => {
    joinAs('Alice')
    startRound(7)
    act(() => socketMock.handlers.onReveal?.(reveal))
    act(() => socketMock.handlers.onGameState?.(state({ phase: 'lobby' })))

    expect(screen.queryByText('One More Time')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Démarrer la partie' })).toBeInTheDocument()
  })
})

describe('BlindTestLobby — mode owner inchangé', () => {
  it('garde l’écran owner quand game_state ne porte pas de mode', () => {
    joinAs('Alice')
    act(() => socketMock.handlers.onGameState?.(state({ mode: undefined })))

    expect(api.getBlindtestSource).not.toHaveBeenCalled()
    expect(screen.getByText('Importer ta playlist (Deezer ou YouTube) :')).toBeInTheDocument()
  })
})

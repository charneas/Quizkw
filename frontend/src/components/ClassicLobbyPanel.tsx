import { useCallback, useEffect, useState } from 'react'
import {
  getBlindtestPresets,
  getBlindtestSource,
  importClassicPlaylist,
  selectBlindtestPreset,
} from '../services/api'
import type { BlindtestClassicSource, BlindtestPreset } from '../types'

const MIN_TITLES = 10
const MAX_TITLES = 50
const DEFAULT_TITLES = 20
const SOURCE_REFRESH_MS = 3000

interface ClassicLobbyPanelProps {
  code: string
  pseudo: string
  isHost: boolean
  players: string[]
  startRefused: string | null
  onSourceChange: () => void
  onStart: (rounds: number) => void
}

/**
 * Lobby du blind test classique : l'hôte choisit une seule playlist (préparée
 * ou personnelle) et le nombre de titres. La source est relue régulièrement :
 * le choix de l'hôte doit apparaître chez tout le monde, et une playlist
 * importée devient jouable au fil de l'arrivée des durées.
 */
export default function ClassicLobbyPanel({
  code,
  pseudo,
  isHost,
  players,
  startRefused,
  onSourceChange,
  onStart,
}: ClassicLobbyPanelProps) {
  const [presets, setPresets] = useState<BlindtestPreset[]>([])
  const [source, setSource] = useState<BlindtestClassicSource | null>(null)
  const [titles, setTitles] = useState(String(DEFAULT_TITLES))
  const [playlistUrl, setPlaylistUrl] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const [sourceError, setSourceError] = useState<string | null>(null)

  const refreshSource = useCallback(() => {
    getBlindtestSource(code)
      .then(setSource)
      .catch(() => {
        // Relu au prochain passage : un raté ponctuel ne change rien au lobby.
      })
  }, [code])

  useEffect(() => {
    refreshSource()
    const interval = window.setInterval(refreshSource, SOURCE_REFRESH_MS)
    return () => window.clearInterval(interval)
  }, [refreshSource])

  useEffect(() => {
    onSourceChange()
  }, [source?.name, source?.playable_count, onSourceChange])

  useEffect(() => {
    if (!isHost) return
    getBlindtestPresets()
      .then(setPresets)
      .catch(() => setPresets([]))
  }, [isHost])

  function changeSource(request: Promise<unknown>) {
    setSourceError(null)
    setIsBusy(true)
    request
      .then(refreshSource)
      .catch((err: Error) => setSourceError(err.message || 'Impossible de charger cette playlist.'))
      .finally(() => setIsBusy(false))
  }

  function handleImport() {
    const url = playlistUrl.trim()
    if (!url || isBusy) return
    changeSource(importClassicPlaylist(url, code, pseudo).then(() => setPlaylistUrl('')))
  }

  const requested = Math.trunc(Number(titles))
  const validCount = Number.isFinite(requested) && requested >= MIN_TITLES && requested <= MAX_TITLES
  const playable = source?.playable_count ?? 0
  const stillLoading = source?.checking ?? false

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <p className="text-text-muted">Joueurs présents :</p>
        <ul className="space-y-1">
          {players.map((player) => (
            <li key={player} className="card px-3 py-2">
              {player}
            </li>
          ))}
        </ul>
      </div>

      <div role="status">
        {source?.name ? (
          <p className="text-text-muted">
            Playlist : <strong className="text-text">{source.name}</strong> —{' '}
            <span>
              {playable} titre{playable > 1 ? 's' : ''} jouable{playable > 1 ? 's' : ''}
            </span>
            {stillLoading ? ' — vérification en cours…' : ''}
          </p>
        ) : (
          <p className="text-text-muted">
            {isHost ? 'Choisis une playlist pour commencer.' : "L'hôte choisit la playlist…"}
          </p>
        )}
      </div>

      {isHost && (
        <>
          {presets.length > 0 && (
            <div className="space-y-2">
              <p className="text-text-muted">Playlists préparées :</p>
              <div className="grid sm:grid-cols-2 gap-2">
                {presets.map((preset) => {
                  const isSelected = source?.name === preset.name
                  return (
                    <button
                      key={preset.slug}
                      className={`btn-secondary disabled:opacity-50 disabled:cursor-not-allowed ${
                        isSelected ? 'ring-2 ring-brand' : ''
                      }`}
                      disabled={isBusy}
                      aria-pressed={isSelected}
                      onClick={() => changeSource(selectBlindtestPreset(code, preset.slug, pseudo))}
                    >
                      {preset.name}
                      <span className="block text-xs font-normal text-text-muted">{preset.track_count} titres</span>
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          <div className="space-y-2">
            <p className="text-text-muted">Ou ta propre playlist (Deezer ou YouTube) :</p>
            <div className="flex gap-2">
              <input
                type="text"
                className="input-field flex-1"
                placeholder="Lien de la playlist"
                aria-label="Lien de la playlist"
                value={playlistUrl}
                onChange={(e) => setPlaylistUrl(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleImport()}
                disabled={isBusy}
              />
              <button className="btn-primary" onClick={handleImport} disabled={isBusy || !playlistUrl.trim()}>
                {isBusy ? 'Chargement…' : 'Importer'}
              </button>
            </div>
            {sourceError && <p className="text-sm text-danger">{sourceError}</p>}
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <label htmlFor="classic-titles" className="text-text-muted text-sm shrink-0">
                Nombre de titres ({MIN_TITLES} à {MAX_TITLES})
              </label>
              <input
                id="classic-titles"
                type="number"
                min={MIN_TITLES}
                max={MAX_TITLES}
                className="input-field w-20"
                value={titles}
                onChange={(e) => setTitles(e.target.value)}
              />
            </div>
            {source?.name && playable < MIN_TITLES && !stillLoading && (
              <p className="text-sm text-danger">
                Il faut au moins {MIN_TITLES} titres jouables pour lancer la partie.
              </p>
            )}
            {validCount && playable >= MIN_TITLES && requested > playable && (
              <p className="text-sm text-text-muted">
                {requested} titres demandés, {playable} jouables : la partie fera {playable} titres.
              </p>
            )}
            {startRefused && (
              <p role="alert" className="text-sm text-danger">
                {startRefused}
              </p>
            )}
            <button
              className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={!validCount || playable < MIN_TITLES}
              onClick={() => onStart(requested)}
            >
              Démarrer la partie
            </button>
          </div>
        </>
      )}
    </div>
  )
}

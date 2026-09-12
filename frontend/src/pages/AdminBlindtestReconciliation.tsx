import { useEffect, useState } from 'react'
import type { UnresolvedBlindtestTrack } from '../types'
import { adminListUnresolvedBlindtestTracks, adminResolveBlindtestTrack } from '../services/api'
import AdminLayout from '../components/AdminLayout'

/**
 * Réconciliation manuelle des morceaux blind-test jamais résolus par le
 * matching automatique (`youtube_video_id IS NULL`) — spec
 * spec-blindtest-admin-reconciliation.md. Liste globale (toutes playlists
 * confondues, cf. Design Notes de la spec), un seul champ éditable par
 * ligne (lien YouTube ou videoId nu), pas de pagination/édition en masse
 * (hors scope), mirroir du pattern inline-actions de `AdminPropositions`.
 */
export default function AdminBlindtestReconciliation() {
  const [tracks, setTracks] = useState<UnresolvedBlindtestTrack[]>([])
  const [inputs, setInputs] = useState<Record<number, string>>({})
  const [savingId, setSavingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  async function refresh() {
    try {
      setTracks(await adminListUnresolvedBlindtestTracks())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  function setInput(trackId: number, value: string) {
    setInputs((prev) => ({ ...prev, [trackId]: value }))
  }

  async function handleResolve(track: UnresolvedBlindtestTrack) {
    const value = (inputs[track.id] ?? '').trim()
    if (!value) {
      setError('Merci de coller un lien YouTube ou un identifiant de vidéo.')
      return
    }
    setSavingId(track.id)
    setError(null)
    setMessage(null)
    try {
      await adminResolveBlindtestTrack(track.id, value)
      setMessage(`« ${track.title} » résolu.`)
      setInputs((prev) => {
        const next = { ...prev }
        delete next[track.id]
        return next
      })
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSavingId(null)
    }
  }

  return (
    <AdminLayout>
      <div>
        <div className="max-w-5xl mx-auto space-y-4">
          <div className="flex items-center justify-between">
            <h1 className="text-xl font-semibold">Blind test — morceaux non trouvés</h1>
            <button className="btn-secondary" onClick={refresh}>Rafraîchir</button>
          </div>

          {message && <p className="text-sm text-green-600">{message}</p>}
          {error && <p className="text-sm text-red-500">{error}</p>}

          <div className="card overflow-x-auto">
            {tracks.length === 0 ? (
              <p className="text-text-muted">Aucun morceau non trouvé.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left border-b border-border">
                    <th className="p-2">Titre</th>
                    <th className="p-2">Artiste</th>
                    <th className="p-2">ISRC</th>
                    <th className="p-2">Lien du morceau</th>
                    <th className="p-2">Playlist</th>
                    <th className="p-2">Lien YouTube / videoId</th>
                    <th className="p-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {tracks.map((track) => (
                    <tr key={track.id} className="border-b border-border">
                      <td className="p-2">{track.title}</td>
                      <td className="p-2">{track.artist}</td>
                      <td className="p-2">{track.isrc ?? '—'}</td>
                      <td className="p-2 max-w-xs truncate">
                        {track.source_url ? (
                          <a href={track.source_url} target="_blank" rel="noreferrer" className="text-brand hover:underline">
                            {track.source_url}
                          </a>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="p-2">
                        #{track.playlist_id} ({track.playlist_provider})
                      </td>
                      <td className="p-2">
                        <input
                          type="text"
                          className="input-field w-full min-w-[16rem]"
                          placeholder="https://www.youtube.com/watch?v=... ou videoId"
                          value={inputs[track.id] ?? ''}
                          onChange={(e) => setInput(track.id, e.target.value)}
                        />
                      </td>
                      <td className="p-2">
                        <button
                          className="btn-primary disabled:opacity-50"
                          disabled={savingId === track.id}
                          onClick={() => handleResolve(track)}
                        >
                          {savingId === track.id ? 'Enregistrement…' : 'Enregistrer'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </AdminLayout>
  )
}

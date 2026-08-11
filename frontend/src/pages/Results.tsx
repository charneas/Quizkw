import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getGame, getFinalStandings, getHostToken, startSuddenDeath, answerSuddenDeath, getSuddenDeathState } from '../services/api'
import type { GameSession } from '../types'
import type { MemoryGridStandings, SuddenDeathState } from '../services/api'

function Results() {
  const { code } = useParams<{ code: string }>()
  const navigate = useNavigate()
  const [game, setGame] = useState<GameSession | null>(null)
  const [standings, setStandings] = useState<MemoryGridStandings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [suddenDeath, setSuddenDeath] = useState<SuddenDeathState | null>(null)
  const [suddenDeathAnswers, setSuddenDeathAnswers] = useState<Record<number, string>>({})
  const [submittingPlayerIds, setSubmittingPlayerIds] = useState<Record<number, boolean>>({})
  const isHost = !!getHostToken(code!)
  // Évite de redéclencher start-sudden-death en boucle pendant qu'un rejeu
  // (round épuisé sans vainqueur) est déjà en cours de création côté serveur.
  const restartingRef = useRef(false)

  useEffect(() => {
    if (code) loadResults()
  }, [code])

  useEffect(() => {
    if (!code || !standings?.is_tie) return
    const poll = async () => {
      const state = await getSuddenDeathState(code)
      setSuddenDeath(state)
      if (state?.is_completed) {
        if (state.winner_player_id) {
          // Vainqueur désigné : recharger le classement final (AC #5).
          await loadResults()
        } else if (!restartingRef.current) {
          // Round épuisé sans vainqueur : rejeu automatique (AC #4).
          restartingRef.current = true
          try {
            await startSuddenDeath(code)
          } catch {
            // Un autre client a peut-être déjà relancé — pas bloquant.
          } finally {
            restartingRef.current = false
          }
        }
      }
    }
    poll()
    const interval = setInterval(poll, 2000)
    return () => clearInterval(interval)
  }, [code, standings?.is_tie])

  const loadResults = async () => {
    try {
      setGame(await getGame(code!))
      // AD-1 : le vainqueur du tournoi sort de la Manche 3 SEULE. Les manches
      // 1 et 2 sont purement qualificatives et n'entrent pas dans ce classement.
      const result = await getFinalStandings(code!)
      setStandings(result)
      if (!result.is_tie) setSuddenDeath(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Résultats indisponibles')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setSubmittingPlayerIds({})
    setSuddenDeathAnswers({})
  }, [suddenDeath?.id])

  const handleStartSuddenDeath = async () => {
    try {
      const state = await startSuddenDeath(code!)
      setSuddenDeath(state)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Impossible de lancer la mort subite')
    }
  }

  const handleSubmitSuddenDeathAnswer = async (playerId: number) => {
    if (!suddenDeath || submittingPlayerIds[playerId]) return
    setSubmittingPlayerIds((prev) => ({ ...prev, [playerId]: true }))
    try {
      const result = await answerSuddenDeath(code!, suddenDeath.id, playerId, suddenDeathAnswers[playerId] || '')
      if (result.is_completed) {
        const state = await getSuddenDeathState(code!)
        setSuddenDeath(state)
        if (result.winner_player_id) await loadResults()
      } else {
        const state = await getSuddenDeathState(code!)
        setSuddenDeath(state)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Réponse refusée')
      setSubmittingPlayerIds((prev) => ({ ...prev, [playerId]: false }))
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-2xl text-text-muted animate-pulse">Chargement...</div>
      </div>
    )
  }

  if (!game) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="card text-center">
          <p className="text-text-muted">Partie non trouvée</p>
          <button onClick={() => navigate('/')} className="btn-primary mt-4">Retour</button>
        </div>
      </div>
    )
  }

  const podium = standings?.player_scores ?? []

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="max-w-lg w-full space-y-6">
        <div className="text-center">
          <h1 className="text-4xl font-display font-semibold">🏆 Résultats</h1>
          <p className="text-text-muted mt-2">Partie {game.code}</p>
          <p className="text-xs text-text-muted mt-1">
            Classement de la Manche 3 — les manches 1 et 2 étaient qualificatives
          </p>
        </div>

        {podium.length === 0 ? (
          <div className="card text-center">
            <p className="text-text-muted">
              {error || "La Manche 3 n'a pas encore désigné de vainqueur."}
            </p>
          </div>
        ) : (
          <div className="card">
            {/* Or/bronze : identifiants fonctionnels de rang, pas des tokens de marque —
                comme FINALIST_COLORS (MemoryGrid.tsx), conservés en classes Tailwind
                standard de façon PERMANENTE (story I-006, revue de code 2026-07-27,
                amendement AC1). Ne pas migrer vers brand/accent. */}
            {podium.map((player, index) => (
              <div
                key={player.player_id}
                className={`flex items-center justify-between p-4 rounded-lg mb-3 last:mb-0 ${
                  index === 0
                    ? 'bg-yellow-900/30 border border-yellow-600'
                    : index === 1
                      ? 'bg-surface-raised border border-text-muted'
                      : index === 2
                        ? 'bg-orange-900/30 border border-orange-700'
                        : 'bg-surface-raised border border-border'
                }`}
              >
                <div className="flex items-center gap-4">
                  <span className="text-3xl">
                    {index === 0 ? '🥇' : index === 1 ? '🥈' : index === 2 ? '🥉' : `${index + 1}.`}
                  </span>
                  <div>
                    <p className="font-display font-semibold text-lg">{player.player_name}</p>
                    <p className="text-sm text-text-muted">
                      {player.own_theme_cells} propres • {player.stolen_cells} volées
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-2xl font-display font-semibold text-accent">{player.total_score}</p>
                  <p className="text-xs text-text-muted">points</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {standings?.is_tie && !suddenDeath && (
          <div className="card text-center border-accent space-y-3">
            <p className="text-accent font-bold">Égalité — mort subite nécessaire</p>
            {isHost && (
              <button onClick={handleStartSuddenDeath} className="btn-primary">
                ⚡ Lancer la mort subite
              </button>
            )}
          </div>
        )}

        {standings?.is_tie && suddenDeath?.is_completed && !suddenDeath.winner_player_id && (
          <div className="card text-center border-accent space-y-3">
            <p className="text-accent font-bold">Personne n'a trouvé — nouvelle question en préparation...</p>
            {isHost && (
              <button onClick={handleStartSuddenDeath} className="btn-primary">
                ⚡ Relancer la mort subite
              </button>
            )}
          </div>
        )}

        {standings?.is_tie && suddenDeath && !suddenDeath.is_completed && (
          <div className="card space-y-4">
            <p className="text-accent font-bold text-center">Mort subite</p>
            <p className="text-center">{suddenDeath.question_text}</p>
            <div className="space-y-3">
              {suddenDeath.tied_player_ids
                .filter((playerId) => !suddenDeath.eliminated_player_ids.includes(playerId))
                .map((playerId) => {
                  const player = podium.find((p) => p.player_id === playerId)
                  const locked = !!submittingPlayerIds[playerId]
                  return (
                    <div key={playerId} className="flex gap-2 items-center">
                      <span className="w-32 truncate">{player?.player_name ?? `Joueur ${playerId}`}</span>
                      <input
                        type="text"
                        value={suddenDeathAnswers[playerId] || ''}
                        onChange={(e) =>
                          setSuddenDeathAnswers((prev) => ({ ...prev, [playerId]: e.target.value }))
                        }
                        disabled={locked}
                        className="input flex-1 disabled:opacity-50"
                        placeholder="Réponse..."
                      />
                      <button
                        onClick={() => handleSubmitSuddenDeathAnswer(playerId)}
                        disabled={locked}
                        className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {locked ? 'Envoyée' : 'Valider'}
                      </button>
                    </div>
                  )
                })}
            </div>
          </div>
        )}

        <div className="flex gap-3">
          <button onClick={() => navigate('/')} className="btn-primary flex-1">
            🏠 Nouvelle partie
          </button>
        </div>
      </div>
    </div>
  )
}

export default Results

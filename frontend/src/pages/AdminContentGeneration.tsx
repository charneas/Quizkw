import { Fragment, useEffect, useState } from 'react'
import AdminLayout from '../components/AdminLayout'
import type { ThemeCategory, ContentSuggestion, ContentFlag, ContentHistoryEntry, CategoryMixResponse } from '../types'
import {
  adminGenerateContent,
  adminListSuggestions,
  adminApproveSuggestion,
  adminRejectSuggestion,
  adminGetCategoryMix,
  adminListFlags,
  adminResolveFlag,
  adminGetHistory,
} from '../services/api'

const THEME_CATEGORIES: ThemeCategory[] = ['serious', 'pop_culture', 'whimsical']
const SUGGESTIONS_PER_PAGE = 5
const FLAGS_PER_PAGE = 10
const HISTORY_PAGE_SIZE = 20

export default function AdminContentGeneration() {
  const [topic, setTopic] = useState('')
  const [category, setCategory] = useState<ThemeCategory | ''>('')
  const [mix, setMix] = useState<CategoryMixResponse | null>(null)
  const [suggestions, setSuggestions] = useState<ContentSuggestion[]>([])
  const [suggestionsPage, setSuggestionsPage] = useState(0)
  const [flags, setFlags] = useState<ContentFlag[]>([])
  const [flagsPage, setFlagsPage] = useState(0)
  const [history, setHistory] = useState<ContentHistoryEntry[]>([])
  const [historyLimit, setHistoryLimit] = useState(HISTORY_PAGE_SIZE)
  const [generating, setGenerating] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [rejectingId, setRejectingId] = useState<number | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [resolvingId, setResolvingId] = useState<number | null>(null)
  const [resolveNote, setResolveNote] = useState('')

  async function refreshMix() {
    setMix(await adminGetCategoryMix())
  }

  async function refreshSuggestions() {
    setSuggestions(await adminListSuggestions('pending'))
  }

  async function refreshFlags() {
    setFlags(await adminListFlags(false))
  }

  async function refreshHistory(limit: number) {
    setHistory(await adminGetHistory({ limit }))
  }

  useEffect(() => {
    refreshMix().catch((e) => setError(String(e)))
    refreshSuggestions().catch((e) => setError(String(e)))
    refreshFlags().catch((e) => setError(String(e)))
    refreshHistory(historyLimit).catch((e) => setError(String(e)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    refreshHistory(historyLimit).catch((e) => setError(String(e)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyLimit])

  function showMessage(text: string) {
    setMessage(text)
    setError(null)
    window.setTimeout(() => setMessage(null), 4000)
  }

  function showError(err: unknown) {
    setError(err instanceof Error ? err.message : String(err))
  }

  async function generate() {
    if (!topic.trim()) return
    setGenerating(true)
    try {
      await adminGenerateContent({ topic: topic.trim(), category: category || null })
      showMessage('Suggestion générée, en attente de validation.')
      setTopic('')
      setCategory('')
      await refreshSuggestions()
      await refreshHistory(historyLimit)
    } catch (e) {
      showError(e)
    } finally {
      setGenerating(false)
    }
  }

  async function approve(suggestionId: number) {
    try {
      const result = await adminApproveSuggestion(suggestionId)
      showMessage(result.message)
      await refreshSuggestions()
      await refreshMix()
      await refreshHistory(historyLimit)
    } catch (e) {
      showError(e)
    }
  }

  async function confirmReject() {
    if (rejectingId === null || !rejectReason.trim()) return
    const suggestionId = rejectingId
    const reason = rejectReason.trim()
    setRejectingId(null)
    setRejectReason('')
    try {
      await adminRejectSuggestion(suggestionId, reason)
      showMessage('Suggestion rejetée.')
      await refreshSuggestions()
      await refreshHistory(historyLimit)
    } catch (e) {
      showError(e)
    }
  }

  async function confirmResolve() {
    if (resolvingId === null) return
    const flagId = resolvingId
    const note = resolveNote.trim() || undefined
    setResolvingId(null)
    setResolveNote('')
    try {
      await adminResolveFlag(flagId, note)
      showMessage('Signalement résolu.')
      await refreshFlags()
      await refreshHistory(historyLimit)
    } catch (e) {
      showError(e)
    }
  }

  const suggestionsPageCount = Math.max(1, Math.ceil(suggestions.length / SUGGESTIONS_PER_PAGE))
  const currentSuggestionsPage = Math.min(suggestionsPage, suggestionsPageCount - 1)
  const suggestionsPageItems = suggestions.slice(
    currentSuggestionsPage * SUGGESTIONS_PER_PAGE,
    (currentSuggestionsPage + 1) * SUGGESTIONS_PER_PAGE
  )

  const flagsPageCount = Math.max(1, Math.ceil(flags.length / FLAGS_PER_PAGE))
  const currentFlagsPage = Math.min(flagsPage, flagsPageCount - 1)
  const flagsPageItems = flags.slice(currentFlagsPage * FLAGS_PER_PAGE, (currentFlagsPage + 1) * FLAGS_PER_PAGE)

  return (
    <AdminLayout>
      <div className="max-w-5xl mx-auto space-y-4 text-text">
        <h1 className="text-2xl font-bold">Génération de contenu</h1>

        {message && <div className="bg-surface-raised text-success p-3 rounded-lg border border-success">{message}</div>}
        {error && <div className="bg-surface-raised text-danger p-3 rounded-lg border border-danger">{error}</div>}

        <section className="card space-y-3">
          {mix && (
            <div className="text-sm text-text-muted">
              Mix actuel ({mix.total_themes} thème(s)) :{' '}
              {mix.mix.map((m) => `${m.category} ${Math.round(m.current_ratio * 100)}%/${Math.round(m.target_ratio * 100)}%`).join(' · ')}
              {' — '}recommandé : <strong>{mix.recommended_category}</strong>
            </div>
          )}

          <div className="flex flex-wrap items-end gap-2">
            <div className="flex-1 min-w-[200px]">
              <label htmlFor="gen-topic" className="block text-xs text-text-muted mb-1">Sujet</label>
              <input
                id="gen-topic"
                className="input-field w-full"
                placeholder="ex: Napoléon"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="gen-category" className="block text-xs text-text-muted mb-1">Catégorie</label>
              <select
                id="gen-category"
                className="input-field"
                value={category}
                onChange={(e) => setCategory(e.target.value as ThemeCategory | '')}
              >
                <option value="">Recommandée</option>
                {THEME_CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <button className="btn-primary disabled:opacity-50" onClick={generate} disabled={generating}>
              {generating ? 'Génération...' : 'Générer'}
            </button>
          </div>
        </section>

        <section className="card space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Suggestions en attente ({suggestions.length})</h2>
          </div>
          {suggestionsPageItems.map((s) => (
            <div key={s.id} className="border border-border rounded-lg p-3 space-y-2">
              <div className="font-medium">{s.generated_theme_name} — {s.generated_category} (sujet : {s.topic})</div>
              <ul className="text-sm list-disc pl-5">
                {s.generated_questions.map((q, i) => (
                  <li key={i}>{q.text} — <em>{q.correct_answer}</em> ({q.difficulty})</li>
                ))}
              </ul>
              <div className="flex gap-2">
                <button className="btn-success text-xs px-2 py-1 min-h-0" onClick={() => approve(s.id)}>Approuver</button>
                <button
                  className="btn-danger text-xs px-2 py-1 min-h-0"
                  onClick={() => { setRejectingId(s.id); setRejectReason('') }}
                >
                  Rejeter
                </button>
              </div>
              {rejectingId === s.id && (
                <div className="flex gap-2 items-center pt-1">
                  <input
                    autoFocus
                    className="input-field flex-1 text-sm py-1.5"
                    placeholder="Raison du rejet"
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && confirmReject()}
                  />
                  <button className="btn-danger text-xs px-2 py-1 min-h-0 disabled:opacity-50" disabled={!rejectReason.trim()} onClick={confirmReject}>
                    Confirmer
                  </button>
                  <button className="btn-secondary text-xs px-2 py-1 min-h-0" onClick={() => setRejectingId(null)}>
                    Annuler
                  </button>
                </div>
              )}
            </div>
          ))}
          {suggestions.length > SUGGESTIONS_PER_PAGE && (
            <div className="flex items-center justify-end gap-2 text-sm text-text-muted">
              <button
                className="btn-secondary text-xs px-3 py-1 min-h-0 disabled:opacity-40 disabled:cursor-not-allowed"
                disabled={currentSuggestionsPage <= 0}
                onClick={() => setSuggestionsPage((p) => Math.max(0, p - 1))}
              >
                ← Précédent
              </button>
              <span>Page {currentSuggestionsPage + 1} / {suggestionsPageCount}</span>
              <button
                className="btn-secondary text-xs px-3 py-1 min-h-0 disabled:opacity-40 disabled:cursor-not-allowed"
                disabled={currentSuggestionsPage >= suggestionsPageCount - 1}
                onClick={() => setSuggestionsPage((p) => Math.min(suggestionsPageCount - 1, p + 1))}
              >
                Suivant →
              </button>
            </div>
          )}
        </section>

        <section className="card space-y-3">
          <h2 className="font-semibold">Signalements non résolus ({flags.length})</h2>
          <table className="w-full text-sm">
            <tbody>
              {flagsPageItems.map((f) => (
                <Fragment key={f.id}>
                  <tr className="border-b border-border">
                    <td className="p-2">Question #{f.question_id}</td>
                    <td className="p-2">{f.reason}</td>
                    <td className="p-2">
                      <button
                        className="btn-secondary text-xs px-2 py-1 min-h-0"
                        onClick={() => { setResolvingId(f.id); setResolveNote('') }}
                      >
                        Résoudre
                      </button>
                    </td>
                  </tr>
                  {resolvingId === f.id && (
                    <tr className="border-b border-border">
                      <td colSpan={3} className="p-2">
                        <div className="flex gap-2 items-center">
                          <input
                            autoFocus
                            className="input-field flex-1 text-sm py-1.5"
                            placeholder="Note de résolution (optionnel)"
                            value={resolveNote}
                            onChange={(e) => setResolveNote(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && confirmResolve()}
                          />
                          <button className="btn-primary text-xs px-2 py-1 min-h-0" onClick={confirmResolve}>
                            Confirmer
                          </button>
                          <button className="btn-secondary text-xs px-2 py-1 min-h-0" onClick={() => setResolvingId(null)}>
                            Annuler
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
          {flags.length > FLAGS_PER_PAGE && (
            <div className="flex items-center justify-end gap-2 text-sm text-text-muted">
              <button
                className="btn-secondary text-xs px-3 py-1 min-h-0 disabled:opacity-40 disabled:cursor-not-allowed"
                disabled={currentFlagsPage <= 0}
                onClick={() => setFlagsPage((p) => Math.max(0, p - 1))}
              >
                ← Précédent
              </button>
              <span>Page {currentFlagsPage + 1} / {flagsPageCount}</span>
              <button
                className="btn-secondary text-xs px-3 py-1 min-h-0 disabled:opacity-40 disabled:cursor-not-allowed"
                disabled={currentFlagsPage >= flagsPageCount - 1}
                onClick={() => setFlagsPage((p) => Math.min(flagsPageCount - 1, p + 1))}
              >
                Suivant →
              </button>
            </div>
          )}
        </section>

        <section className="card space-y-3">
          <h2 className="font-semibold">Historique récent</h2>
          <table className="w-full text-sm">
            <tbody>
              {history.map((h) => (
                <tr key={h.id} className="border-b border-border">
                  <td className="p-2">{h.entity_type} #{h.entity_id}</td>
                  <td className="p-2">{h.action}</td>
                  <td className="p-2 text-text-muted">{h.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {history.length >= historyLimit && (
            <div className="flex justify-end">
              <button
                className="btn-secondary text-xs px-3 py-1 min-h-0"
                onClick={() => setHistoryLimit((l) => l + HISTORY_PAGE_SIZE)}
              >
                Charger plus
              </button>
            </div>
          )}
        </section>
      </div>
    </AdminLayout>
  )
}

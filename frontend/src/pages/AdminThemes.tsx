import { useEffect, useState } from 'react'
import AdminLayout from '../components/AdminLayout'
import ConfirmModal from '../components/ConfirmModal'
import type { Theme, ThemeCategory } from '../types'
import { adminListThemes, adminCreateTheme, adminUpdateTheme, adminDeleteTheme, adminListQuestions } from '../services/api'

const THEME_CATEGORIES: ThemeCategory[] = ['serious', 'pop_culture', 'whimsical']
const THEMES_PER_PAGE = 20

function emptyThemeForm() {
  return { name: '', category: 'serious' as ThemeCategory, difficulty_level: 5, description: '' }
}

export default function AdminThemes() {
  const [themes, setThemes] = useState<Theme[]>([])
  const [questionCountByTheme, setQuestionCountByTheme] = useState<Record<number, number>>({})
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [themeForm, setThemeForm] = useState(emptyThemeForm())
  const [editingThemeId, setEditingThemeId] = useState<number | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirmDeleteTheme, setConfirmDeleteTheme] = useState<{ id: number; name: string } | null>(null)

  async function refreshThemes() {
    setThemes(await adminListThemes())
  }

  async function refreshQuestionCounts() {
    const all = await adminListQuestions()
    const counts: Record<number, number> = {}
    for (const q of all) {
      if (q.theme_id !== null) counts[q.theme_id] = (counts[q.theme_id] ?? 0) + 1
    }
    setQuestionCountByTheme(counts)
  }

  useEffect(() => {
    refreshThemes().catch((e) => setError(String(e)))
    refreshQuestionCounts().catch((e) => setError(String(e)))
  }, [])

  useEffect(() => {
    setPage(0)
  }, [search])

  function showMessage(text: string) {
    setMessage(text)
    setError(null)
    window.setTimeout(() => setMessage(null), 4000)
  }

  function showError(err: unknown) {
    setError(err instanceof Error ? err.message : String(err))
  }

  async function submitTheme() {
    try {
      if (editingThemeId) {
        await adminUpdateTheme(editingThemeId, themeForm)
        showMessage('Thème mis à jour.')
      } else {
        await adminCreateTheme(themeForm)
        showMessage('Thème créé.')
      }
      setThemeForm(emptyThemeForm())
      setEditingThemeId(null)
      await refreshThemes()
      await refreshQuestionCounts()
    } catch (e) {
      showError(e)
    }
  }

  function editTheme(theme: Theme) {
    setEditingThemeId(theme.id)
    setThemeForm({
      name: theme.name,
      category: theme.category,
      difficulty_level: theme.difficulty_level,
      description: theme.description ?? '',
    })
  }

  async function confirmRemoveTheme() {
    if (!confirmDeleteTheme) return
    const { id: themeId } = confirmDeleteTheme
    setConfirmDeleteTheme(null)
    try {
      const result = await adminDeleteTheme(themeId)
      showMessage(result.message)
      await refreshThemes()
      await refreshQuestionCounts()
    } catch (e) {
      showError(e)
    }
  }

  const filtered = themes.filter((theme) => {
    const term = search.trim().toLowerCase()
    if (!term) return true
    return theme.name.toLowerCase().includes(term) || theme.category.toLowerCase().includes(term)
  })
  const pageCount = Math.max(1, Math.ceil(filtered.length / THEMES_PER_PAGE))
  const currentPage = Math.min(page, pageCount - 1)
  const pageItems = filtered.slice(currentPage * THEMES_PER_PAGE, (currentPage + 1) * THEMES_PER_PAGE)

  return (
    <AdminLayout>
      <div className="max-w-5xl mx-auto space-y-4 text-text">
        <h1 className="text-2xl font-bold">Thèmes</h1>

        {message && <div className="bg-surface-raised text-success p-3 rounded-lg border border-success">{message}</div>}
        {error && <div className="bg-surface-raised text-danger p-3 rounded-lg border border-danger">{error}</div>}

        <section className="card space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <div>
              <label htmlFor="theme-name" className="block text-xs text-text-muted mb-1">Nom</label>
              <input
                id="theme-name"
                className="input-field"
                value={themeForm.name}
                onChange={(e) => setThemeForm({ ...themeForm, name: e.target.value })}
              />
            </div>
            <div>
              <label htmlFor="theme-category" className="block text-xs text-text-muted mb-1">Catégorie</label>
              <select
                id="theme-category"
                className="input-field"
                value={themeForm.category}
                onChange={(e) => setThemeForm({ ...themeForm, category: e.target.value as ThemeCategory })}
              >
                {THEME_CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="theme-difficulty" className="block text-xs text-text-muted mb-1">Difficulté (1-10)</label>
              <input
                id="theme-difficulty"
                className="input-field"
                type="number"
                min={1}
                max={10}
                value={themeForm.difficulty_level}
                onChange={(e) => setThemeForm({ ...themeForm, difficulty_level: Number(e.target.value) })}
              />
            </div>
            <div>
              <label htmlFor="theme-description" className="block text-xs text-text-muted mb-1">Description</label>
              <input
                id="theme-description"
                className="input-field"
                value={themeForm.description}
                onChange={(e) => setThemeForm({ ...themeForm, description: e.target.value })}
              />
            </div>
          </div>
          <button className="btn-primary" onClick={submitTheme}>
            {editingThemeId ? 'Mettre à jour le thème' : 'Créer le thème'}
          </button>
          {editingThemeId && (
            <button
              className="btn-secondary ml-2"
              onClick={() => { setEditingThemeId(null); setThemeForm(emptyThemeForm()) }}
            >
              Annuler
            </button>
          )}
        </section>

        <section className="card space-y-3">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <label htmlFor="theme-search" className="block text-xs text-text-muted mb-1">Rechercher</label>
              <input
                id="theme-search"
                className="input-field w-auto"
                placeholder="Nom, catégorie"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <span className="text-sm text-text-muted">{filtered.length} thème(s)</span>
          </div>

          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b border-border">
                <th className="p-2">Nom</th>
                <th className="p-2">Catégorie</th>
                <th className="p-2">Difficulté</th>
                <th className="p-2">Questions</th>
                <th className="p-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {pageItems.map((theme) => (
                <tr key={theme.id} className="border-b border-border">
                  <td className="p-2">{theme.name}</td>
                  <td className="p-2">{theme.category}</td>
                  <td className="p-2">{theme.difficulty_level}</td>
                  <td className="p-2">
                    {questionCountByTheme[theme.id] ?? 0}
                    {(questionCountByTheme[theme.id] ?? 0) < 10 && (
                      <span className="ml-1 text-danger" title="Sous le seuil de 10 questions requis pour être utilisable en jeu">⚠</span>
                    )}
                  </td>
                  <td className="p-2 space-x-2">
                    <button className="btn-secondary text-xs px-2 py-1 min-h-0" onClick={() => editTheme(theme)}>Éditer</button>
                    <button className="btn-danger text-xs px-2 py-1 min-h-0" onClick={() => setConfirmDeleteTheme({ id: theme.id, name: theme.name })}>Supprimer</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="flex items-center justify-between mt-2 text-sm text-text-muted">
            <span>
              {filtered.length === 0
                ? 'Aucun thème'
                : `${currentPage * THEMES_PER_PAGE + 1}–${Math.min((currentPage + 1) * THEMES_PER_PAGE, filtered.length)} sur ${filtered.length}`}
            </span>
            <div className="flex items-center gap-2">
              <button
                className="btn-secondary text-xs px-3 py-1 min-h-0 disabled:opacity-40 disabled:cursor-not-allowed"
                disabled={currentPage <= 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
              >
                ← Précédent
              </button>
              <span>Page {currentPage + 1} / {pageCount}</span>
              <button
                className="btn-secondary text-xs px-3 py-1 min-h-0 disabled:opacity-40 disabled:cursor-not-allowed"
                disabled={currentPage >= pageCount - 1}
                onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
              >
                Suivant →
              </button>
            </div>
          </div>
        </section>

        {confirmDeleteTheme && (
          <ConfirmModal
            title="Supprimer le thème"
            message={
              (questionCountByTheme[confirmDeleteTheme.id] ?? 0) > 0
                ? `Supprimer le thème "${confirmDeleteTheme.name}" ? Ses ${questionCountByTheme[confirmDeleteTheme.id]} question(s) associée(s) deviendront orphelines (aucun thème).`
                : `Supprimer le thème "${confirmDeleteTheme.name}" ?`
            }
            confirmLabel="Supprimer"
            onConfirm={confirmRemoveTheme}
            onCancel={() => setConfirmDeleteTheme(null)}
          />
        )}
      </div>
    </AdminLayout>
  )
}

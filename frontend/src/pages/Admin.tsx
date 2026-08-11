import { Fragment, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import ConfirmModal from '../components/ConfirmModal'
import type { Theme, Question, ThemeCategory, Difficulty, QuestionStatsResponse, ContentSuggestion, ContentFlag, ContentHistoryEntry, CategoryMixResponse } from '../types'
import {
  adminListThemes,
  adminCreateTheme,
  adminUpdateTheme,
  adminDeleteTheme,
  adminListQuestions,
  adminCreateQuestion,
  adminUpdateQuestion,
  adminDeleteQuestion,
  adminGetQuestionStats,
  adminExportContent,
  adminImportContent,
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
const DIFFICULTIES: Difficulty[] = ['easy', 'medium', 'hard']
const DIFFICULTY_POINTS: Record<Difficulty, number> = { easy: 2, medium: 4, hard: 6 }

function emptyThemeForm() {
  return { name: '', category: 'serious' as ThemeCategory, difficulty_level: 5, description: '' }
}

function emptyQuestionForm() {
  return {
    text: '',
    category: '',
    difficulty: 'easy' as Difficulty,
    correct_answer: '',
    wrong_answers: '',
    theme_id: '' as number | '',
    question_number: '' as number | '',
    image_url: '',
  }
}

export default function Admin() {
  const [themes, setThemes] = useState<Theme[]>([])
  const [questions, setQuestions] = useState<Question[]>([])
  // Comptes de questions par thème, toujours calculés sur la liste NON filtrée
  // (sinon activer le filtre par thème fait afficher 0 pour tous les autres —
  // trouvé en revue de code).
  const [questionCountByTheme, setQuestionCountByTheme] = useState<Record<number, number>>({})
  const [filterThemeId, setFilterThemeId] = useState<number | ''>('')
  const [questionSearch, setQuestionSearch] = useState('')
  const [themeForm, setThemeForm] = useState(emptyThemeForm())
  const [editingThemeId, setEditingThemeId] = useState<number | null>(null)
  const [questionForm, setQuestionForm] = useState(emptyQuestionForm())
  const [editingQuestionId, setEditingQuestionId] = useState<number | null>(null)
  const questionFormRef = useRef<HTMLElement>(null)
  const [statsByQuestion, setStatsByQuestion] = useState<Record<number, QuestionStatsResponse>>({})
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirmDeleteTheme, setConfirmDeleteTheme] = useState<{ id: number; name: string } | null>(null)
  const [confirmDeleteQuestionId, setConfirmDeleteQuestionId] = useState<number | null>(null)
  const [questionPage, setQuestionPage] = useState(0)
  const QUESTIONS_PER_PAGE = 20

  async function refreshThemes() {
    setThemes(await adminListThemes())
  }

  async function refreshQuestions(themeId?: number) {
    setQuestions(await adminListQuestions(themeId))
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
    refreshQuestions(filterThemeId === '' ? undefined : filterThemeId).catch((e) => setError(String(e)))
  }, [filterThemeId])

  useEffect(() => {
    setQuestionPage(0)
  }, [filterThemeId, questionSearch])

  function showMessage(text: string) {
    setMessage(text)
    setError(null)
    window.setTimeout(() => setMessage(null), 4000)
  }

  function showError(err: unknown) {
    setError(err instanceof Error ? err.message : String(err))
  }

  // --- Thèmes ---

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
      await refreshQuestions(filterThemeId === '' ? undefined : filterThemeId)
    } catch (e) {
      showError(e)
    }
  }

  // --- Questions ---

  async function submitQuestion() {
    try {
      const payload = {
        text: questionForm.text,
        category: questionForm.category,
        difficulty: questionForm.difficulty,
        points: DIFFICULTY_POINTS[questionForm.difficulty],
        correct_answer: questionForm.correct_answer,
        wrong_answers: questionForm.wrong_answers.split(',').map((s) => s.trim()).filter(Boolean),
        theme_id: questionForm.theme_id === '' ? null : questionForm.theme_id,
        question_number: questionForm.question_number === '' ? null : questionForm.question_number,
        image_url: questionForm.image_url.trim() === '' ? null : questionForm.image_url.trim(),
      }
      if (editingQuestionId) {
        await adminUpdateQuestion(editingQuestionId, payload)
        showMessage('Question mise à jour.')
      } else {
        await adminCreateQuestion(payload)
        showMessage('Question créée.')
      }
      setQuestionForm(emptyQuestionForm())
      setEditingQuestionId(null)
      await refreshQuestions(filterThemeId === '' ? undefined : filterThemeId)
      await refreshQuestionCounts()
    } catch (e) {
      showError(e)
    }
  }

  function editQuestion(question: Question) {
    setEditingQuestionId(question.id)
    setQuestionForm({
      text: question.text,
      category: question.category,
      difficulty: question.difficulty,
      correct_answer: question.correct_answer,
      wrong_answers: question.wrong_answers.join(', '),
      theme_id: question.theme_id ?? '',
      question_number: question.question_number ?? '',
      image_url: question.image_url ?? '',
    })
    // Le formulaire est au-dessus de la liste des questions : sans ce scroll,
    // cliquer "Éditer" en bas d'une longue liste ne produit aucun changement
    // visible à l'écran et donne l'impression que le bouton ne fait rien.
    questionFormRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  async function confirmRemoveQuestion() {
    if (confirmDeleteQuestionId === null) return
    const questionId = confirmDeleteQuestionId
    setConfirmDeleteQuestionId(null)
    try {
      const result = await adminDeleteQuestion(questionId)
      showMessage(result.warning ? result.warning.message : result.message)
      await refreshQuestions(filterThemeId === '' ? undefined : filterThemeId)
      await refreshQuestionCounts()
    } catch (e) {
      showError(e)
    }
  }

  async function loadStats(questionId: number) {
    try {
      const stats = await adminGetQuestionStats(questionId)
      setStatsByQuestion((prev) => ({ ...prev, [questionId]: stats }))
    } catch (e) {
      showError(e)
    }
  }

  // --- Export / Import ---

  async function exportContent() {
    try {
      const data = await adminExportContent()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'quizkw-content-export.json'
      document.body.appendChild(a)
      a.click()
      a.remove()
      // Révoquer après le clic plutôt que juste après : sur certains navigateurs
      // (Firefox/Safari), révoquer trop tôt fait échouer le téléchargement
      // silencieusement (trouvé en revue de code).
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) {
      showError(e)
    }
  }

  async function importContent(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const parsed = JSON.parse(text)
      // `source_id` : l'id du thème dans le fichier exporté. Le serveur s'en sert
      // uniquement pour remapper les theme_id des questions de ce même import
      // vers le nouvel id attribué (les thèmes importés reçoivent toujours un
      // nouvel id) ; sans lui, réimporter un export rattache les questions à un
      // theme_id périmé (trouvé en revue de code).
      const themesPayload = (parsed.themes ?? []).map((t: Theme) => ({
        source_id: t.id,
        name: t.name,
        category: t.category,
        difficulty_level: t.difficulty_level,
        description: t.description ?? null,
      }))
      const questionsPayload = (parsed.questions ?? []).map((q: Question) => ({
        text: q.text,
        category: q.category,
        difficulty: q.difficulty,
        points: q.points,
        correct_answer: q.correct_answer,
        wrong_answers: q.wrong_answers,
        theme_id: q.theme_id,
        question_number: q.question_number,
      }))
      const result = await adminImportContent({ themes: themesPayload, questions: questionsPayload })
      showMessage(result.message)
      await refreshThemes()
      await refreshQuestions(filterThemeId === '' ? undefined : filterThemeId)
      await refreshQuestionCounts()
    } catch (e) {
      showError(e)
    } finally {
      event.target.value = ''
    }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-8 text-text">
      <h1 className="text-2xl font-bold">Administration du contenu</h1>

      <Link to="/admin/propositions" className="text-brand hover:underline text-sm">
        Propositions en attente →
      </Link>

      {message && <div className="bg-surface-raised text-success p-3 rounded-lg border border-success">{message}</div>}
      {error && <div className="bg-surface-raised text-danger p-3 rounded-lg border border-danger">{error}</div>}

      <div className="flex gap-3">
        <button className="btn-primary" onClick={exportContent}>
          Exporter le contenu (JSON)
        </button>
        <label className="btn-secondary cursor-pointer inline-flex items-center">
          Importer un fichier JSON
          <input type="file" accept="application/json" className="hidden" onChange={importContent} />
        </label>
      </div>

      <section className="card space-y-3">
        <h2 className="text-xl font-semibold">Thèmes</h2>
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

        <table className="w-full mt-3 text-sm">
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
            {themes.map((theme) => (
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
      </section>

      <section className="card space-y-3" ref={questionFormRef}>
        <h2 className="text-xl font-semibold">Questions</h2>

        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label htmlFor="question-filter-theme" className="block text-xs text-text-muted mb-1">Filtrer par thème</label>
            <select
              id="question-filter-theme"
              className="input-field inline-block w-auto"
              value={filterThemeId}
              onChange={(e) => setFilterThemeId(e.target.value === '' ? '' : Number(e.target.value))}
            >
              <option value="">Tous les thèmes</option>
              {themes.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="question-search" className="block text-xs text-text-muted mb-1">Rechercher</label>
            <input
              id="question-search"
              className="input-field w-auto"
              placeholder="Texte, catégorie, réponse"
              value={questionSearch}
              onChange={(e) => setQuestionSearch(e.target.value)}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
          <div className="col-span-2">
            <label htmlFor="question-text" className="block text-xs text-text-muted mb-1">Texte de la question</label>
            <input
              id="question-text"
              className="input-field w-full"
              value={questionForm.text}
              onChange={(e) => setQuestionForm({ ...questionForm, text: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="question-category" className="block text-xs text-text-muted mb-1">Catégorie</label>
            <input
              id="question-category"
              className="input-field w-full"
              value={questionForm.category}
              onChange={(e) => setQuestionForm({ ...questionForm, category: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="question-difficulty" className="block text-xs text-text-muted mb-1">Difficulté</label>
            <select
              id="question-difficulty"
              className="input-field w-full"
              value={questionForm.difficulty}
              onChange={(e) => setQuestionForm({ ...questionForm, difficulty: e.target.value as Difficulty })}
            >
              {DIFFICULTIES.map((d) => (
                <option key={d} value={d}>{d} ({DIFFICULTY_POINTS[d]} pts)</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="question-correct-answer" className="block text-xs text-text-muted mb-1">Réponse correcte</label>
            <input
              id="question-correct-answer"
              className="input-field w-full"
              value={questionForm.correct_answer}
              onChange={(e) => setQuestionForm({ ...questionForm, correct_answer: e.target.value })}
            />
          </div>
          <div className="col-span-2">
            <label htmlFor="question-wrong-answers" className="block text-xs text-text-muted mb-1">Mauvaises réponses (séparées par des virgules)</label>
            <input
              id="question-wrong-answers"
              className="input-field w-full"
              value={questionForm.wrong_answers}
              onChange={(e) => setQuestionForm({ ...questionForm, wrong_answers: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="question-theme" className="block text-xs text-text-muted mb-1">Thème</label>
            <select
              id="question-theme"
              className="input-field w-full"
              value={questionForm.theme_id}
              onChange={(e) => setQuestionForm({ ...questionForm, theme_id: e.target.value === '' ? '' : Number(e.target.value) })}
            >
              <option value="">Sans thème</option>
              {themes.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="question-number" className="block text-xs text-text-muted mb-1">N° question (Round 2)</label>
            <input
              id="question-number"
              className="input-field w-full"
              type="number"
              min={1}
              max={10}
              value={questionForm.question_number}
              onChange={(e) => setQuestionForm({ ...questionForm, question_number: e.target.value === '' ? '' : Number(e.target.value) })}
            />
          </div>
          <div className="col-span-2">
            <label htmlFor="question-image-url" className="block text-xs text-text-muted mb-1">URL de l'image (optionnel)</label>
            <input
              id="question-image-url"
              className="input-field w-full"
              value={questionForm.image_url}
              onChange={(e) => setQuestionForm({ ...questionForm, image_url: e.target.value })}
            />
          </div>
        </div>
        <button className="btn-primary" onClick={submitQuestion}>
          {editingQuestionId ? 'Mettre à jour la question' : 'Créer la question'}
        </button>
        {editingQuestionId && (
          <button
            className="btn-secondary ml-2"
            onClick={() => { setEditingQuestionId(null); setQuestionForm(emptyQuestionForm()) }}
          >
            Annuler
          </button>
        )}

        {(() => {
          const filtered = questions.filter((question) => {
            const term = questionSearch.trim().toLowerCase()
            if (!term) return true
            return (
              question.text.toLowerCase().includes(term) ||
              question.category.toLowerCase().includes(term) ||
              question.correct_answer.toLowerCase().includes(term)
            )
          })
          const pageCount = Math.max(1, Math.ceil(filtered.length / QUESTIONS_PER_PAGE))
          const page = Math.min(questionPage, pageCount - 1)
          const pageItems = filtered.slice(page * QUESTIONS_PER_PAGE, (page + 1) * QUESTIONS_PER_PAGE)

          return (
            <>
              <table className="w-full mt-3 text-sm">
                <thead>
                  <tr className="text-left border-b border-border">
                    <th className="p-2">Texte</th>
                    <th className="p-2">Difficulté</th>
                    <th className="p-2">Réponse</th>
                    <th className="p-2">Stats</th>
                    <th className="p-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {pageItems.map((question) => (
                    <tr key={question.id} className="border-b border-border">
                      <td className="p-2">{question.text}</td>
                      <td className="p-2">{question.difficulty} ({question.points} pts)</td>
                      <td className="p-2">{question.correct_answer}</td>
                      <td className="p-2">
                        {statsByQuestion[question.id] ? (
                          <span>
                            {statsByQuestion[question.id].times_answered} réponses,{' '}
                            {Math.round(statsByQuestion[question.id].success_rate * 100)}% réussite
                          </span>
                        ) : (
                          <button className="btn-secondary text-xs px-2 py-1 min-h-0" onClick={() => loadStats(question.id)}>Charger</button>
                        )}
                      </td>
                      <td className="p-2 space-x-2">
                        <button className="btn-secondary text-xs px-2 py-1 min-h-0" onClick={() => editQuestion(question)}>Éditer</button>
                        <button className="btn-danger text-xs px-2 py-1 min-h-0" onClick={() => setConfirmDeleteQuestionId(question.id)}>Supprimer</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="flex items-center justify-between mt-2 text-sm text-text-muted">
                <span>
                  {filtered.length === 0
                    ? 'Aucune question'
                    : `${page * QUESTIONS_PER_PAGE + 1}–${Math.min((page + 1) * QUESTIONS_PER_PAGE, filtered.length)} sur ${filtered.length}`}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    className="btn-secondary text-xs px-3 py-1 min-h-0 disabled:opacity-40 disabled:cursor-not-allowed"
                    disabled={page <= 0}
                    onClick={() => setQuestionPage((p) => Math.max(0, p - 1))}
                  >
                    ← Précédent
                  </button>
                  <span>Page {page + 1} / {pageCount}</span>
                  <button
                    className="btn-secondary text-xs px-3 py-1 min-h-0 disabled:opacity-40 disabled:cursor-not-allowed"
                    disabled={page >= pageCount - 1}
                    onClick={() => setQuestionPage((p) => Math.min(pageCount - 1, p + 1))}
                  >
                    Suivant →
                  </button>
                </div>
              </div>
            </>
          )
        })()}
      </section>

      <ContentGenerationSection onContentApproved={() => { refreshThemes(); refreshQuestionCounts() }} />

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

      {confirmDeleteQuestionId !== null && (
        <ConfirmModal
          title="Supprimer la question"
          message="Supprimer cette question ?"
          confirmLabel="Supprimer"
          onConfirm={confirmRemoveQuestion}
          onCancel={() => setConfirmDeleteQuestionId(null)}
        />
      )}
    </div>
  )
}

// Story F.2 : génération semi-automatique de contenu (Wikipedia + Claude),
// validation humaine, mix de catégories, signalements joueurs, historique.
function ContentGenerationSection({ onContentApproved }: { onContentApproved: () => void }) {
  const [topic, setTopic] = useState('')
  const [category, setCategory] = useState<ThemeCategory | ''>('')
  const [mix, setMix] = useState<CategoryMixResponse | null>(null)
  const [suggestions, setSuggestions] = useState<ContentSuggestion[]>([])
  const [flags, setFlags] = useState<ContentFlag[]>([])
  const [history, setHistory] = useState<ContentHistoryEntry[]>([])
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

  async function refreshHistory() {
    setHistory(await adminGetHistory({ limit: 20 }))
  }

  useEffect(() => {
    refreshMix().catch((e) => setError(String(e)))
    refreshSuggestions().catch((e) => setError(String(e)))
    refreshFlags().catch((e) => setError(String(e)))
    refreshHistory().catch((e) => setError(String(e)))
  }, [])

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
      await refreshHistory()
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
      await refreshHistory()
      onContentApproved()
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
      await refreshHistory()
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
      await refreshHistory()
    } catch (e) {
      showError(e)
    }
  }

  return (
    <section className="card space-y-3">
      <h2 className="text-xl font-semibold">Génération de contenu</h2>

      {message && <div className="bg-surface-raised text-success p-3 rounded-lg border border-success">{message}</div>}
      {error && <div className="bg-surface-raised text-danger p-3 rounded-lg border border-danger">{error}</div>}

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

      <h3 className="font-semibold mt-4">Suggestions en attente ({suggestions.length})</h3>
      {suggestions.map((s) => (
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

      <h3 className="font-semibold mt-4">Signalements non résolus ({flags.length})</h3>
      <table className="w-full text-sm">
        <tbody>
          {flags.map((f) => (
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

      <h3 className="font-semibold mt-4">Historique récent</h3>
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
    </section>
  )
}

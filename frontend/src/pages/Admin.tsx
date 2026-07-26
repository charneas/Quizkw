import { useEffect, useState } from 'react'
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
  const [themeForm, setThemeForm] = useState(emptyThemeForm())
  const [editingThemeId, setEditingThemeId] = useState<number | null>(null)
  const [questionForm, setQuestionForm] = useState(emptyQuestionForm())
  const [editingQuestionId, setEditingQuestionId] = useState<number | null>(null)
  const [statsByQuestion, setStatsByQuestion] = useState<Record<number, QuestionStatsResponse>>({})
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

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

  async function removeTheme(themeId: number, themeName: string) {
    const questionCount = questionCountByTheme[themeId] ?? 0
    const confirmMessage = questionCount > 0
      ? `Supprimer le thème "${themeName}" ? Ses ${questionCount} question(s) associée(s) deviendront orphelines (aucun thème).`
      : `Supprimer le thème "${themeName}" ?`
    if (!window.confirm(confirmMessage)) return
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
    })
  }

  async function removeQuestion(questionId: number) {
    if (!window.confirm('Supprimer cette question ?')) return
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
    <div className="p-6 max-w-5xl mx-auto space-y-8">
      <h1 className="text-2xl font-bold">Administration du contenu</h1>

      {message && <div className="bg-green-100 text-green-800 p-3 rounded">{message}</div>}
      {error && <div className="bg-red-100 text-red-800 p-3 rounded">{error}</div>}

      <div className="flex gap-3">
        <button className="px-4 py-2 bg-blue-600 text-white rounded" onClick={exportContent}>
          Exporter le contenu (JSON)
        </button>
        <label className="px-4 py-2 bg-gray-600 text-white rounded cursor-pointer">
          Importer un fichier JSON
          <input type="file" accept="application/json" className="hidden" onChange={importContent} />
        </label>
      </div>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Thèmes</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <input
            className="border p-2 rounded"
            placeholder="Nom"
            value={themeForm.name}
            onChange={(e) => setThemeForm({ ...themeForm, name: e.target.value })}
          />
          <select
            className="border p-2 rounded"
            value={themeForm.category}
            onChange={(e) => setThemeForm({ ...themeForm, category: e.target.value as ThemeCategory })}
          >
            {THEME_CATEGORIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <input
            className="border p-2 rounded"
            type="number"
            min={1}
            max={10}
            placeholder="Difficulté (1-10)"
            value={themeForm.difficulty_level}
            onChange={(e) => setThemeForm({ ...themeForm, difficulty_level: Number(e.target.value) })}
          />
          <input
            className="border p-2 rounded"
            placeholder="Description"
            value={themeForm.description}
            onChange={(e) => setThemeForm({ ...themeForm, description: e.target.value })}
          />
        </div>
        <button className="px-4 py-2 bg-green-600 text-white rounded" onClick={submitTheme}>
          {editingThemeId ? 'Mettre à jour le thème' : 'Créer le thème'}
        </button>
        {editingThemeId && (
          <button
            className="ml-2 px-4 py-2 bg-gray-300 rounded"
            onClick={() => { setEditingThemeId(null); setThemeForm(emptyThemeForm()) }}
          >
            Annuler
          </button>
        )}

        <table className="w-full mt-3 text-sm">
          <thead>
            <tr className="text-left border-b">
              <th className="p-2">Nom</th>
              <th className="p-2">Catégorie</th>
              <th className="p-2">Difficulté</th>
              <th className="p-2">Questions</th>
              <th className="p-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {themes.map((theme) => (
              <tr key={theme.id} className="border-b">
                <td className="p-2">{theme.name}</td>
                <td className="p-2">{theme.category}</td>
                <td className="p-2">{theme.difficulty_level}</td>
                <td className="p-2">
                  {questionCountByTheme[theme.id] ?? 0}
                  {(questionCountByTheme[theme.id] ?? 0) < 10 && (
                    <span className="ml-1 text-amber-600" title="Sous le seuil de 10 questions requis pour être utilisable en jeu">⚠</span>
                  )}
                </td>
                <td className="p-2 space-x-2">
                  <button className="text-blue-600" onClick={() => editTheme(theme)}>Éditer</button>
                  <button className="text-red-600" onClick={() => removeTheme(theme.id, theme.name)}>Supprimer</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Questions</h2>

        <div>
          <label className="mr-2">Filtrer par thème :</label>
          <select
            className="border p-2 rounded"
            value={filterThemeId}
            onChange={(e) => setFilterThemeId(e.target.value === '' ? '' : Number(e.target.value))}
          >
            <option value="">Tous les thèmes</option>
            {themes.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
          <input
            className="border p-2 rounded col-span-2"
            placeholder="Texte de la question"
            value={questionForm.text}
            onChange={(e) => setQuestionForm({ ...questionForm, text: e.target.value })}
          />
          <input
            className="border p-2 rounded"
            placeholder="Catégorie"
            value={questionForm.category}
            onChange={(e) => setQuestionForm({ ...questionForm, category: e.target.value })}
          />
          <select
            className="border p-2 rounded"
            value={questionForm.difficulty}
            onChange={(e) => setQuestionForm({ ...questionForm, difficulty: e.target.value as Difficulty })}
          >
            {DIFFICULTIES.map((d) => (
              <option key={d} value={d}>{d} ({DIFFICULTY_POINTS[d]} pts)</option>
            ))}
          </select>
          <input
            className="border p-2 rounded"
            placeholder="Réponse correcte"
            value={questionForm.correct_answer}
            onChange={(e) => setQuestionForm({ ...questionForm, correct_answer: e.target.value })}
          />
          <input
            className="border p-2 rounded col-span-2"
            placeholder="Mauvaises réponses (séparées par des virgules)"
            value={questionForm.wrong_answers}
            onChange={(e) => setQuestionForm({ ...questionForm, wrong_answers: e.target.value })}
          />
          <select
            className="border p-2 rounded"
            value={questionForm.theme_id}
            onChange={(e) => setQuestionForm({ ...questionForm, theme_id: e.target.value === '' ? '' : Number(e.target.value) })}
          >
            <option value="">Sans thème</option>
            {themes.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
          <input
            className="border p-2 rounded"
            type="number"
            min={1}
            max={10}
            placeholder="N° question (Round 2)"
            value={questionForm.question_number}
            onChange={(e) => setQuestionForm({ ...questionForm, question_number: e.target.value === '' ? '' : Number(e.target.value) })}
          />
        </div>
        <button className="px-4 py-2 bg-green-600 text-white rounded" onClick={submitQuestion}>
          {editingQuestionId ? 'Mettre à jour la question' : 'Créer la question'}
        </button>
        {editingQuestionId && (
          <button
            className="ml-2 px-4 py-2 bg-gray-300 rounded"
            onClick={() => { setEditingQuestionId(null); setQuestionForm(emptyQuestionForm()) }}
          >
            Annuler
          </button>
        )}

        <table className="w-full mt-3 text-sm">
          <thead>
            <tr className="text-left border-b">
              <th className="p-2">Texte</th>
              <th className="p-2">Difficulté</th>
              <th className="p-2">Réponse</th>
              <th className="p-2">Stats</th>
              <th className="p-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {questions.map((question) => (
              <tr key={question.id} className="border-b">
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
                    <button className="text-blue-600" onClick={() => loadStats(question.id)}>Charger</button>
                  )}
                </td>
                <td className="p-2 space-x-2">
                  <button className="text-blue-600" onClick={() => editQuestion(question)}>Éditer</button>
                  <button className="text-red-600" onClick={() => removeQuestion(question.id)}>Supprimer</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <ContentGenerationSection onContentApproved={() => { refreshThemes(); refreshQuestionCounts() }} />
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

  async function reject(suggestionId: number) {
    const reason = window.prompt('Raison du rejet ?')
    if (!reason) return
    try {
      await adminRejectSuggestion(suggestionId, reason)
      showMessage('Suggestion rejetée.')
      await refreshSuggestions()
      await refreshHistory()
    } catch (e) {
      showError(e)
    }
  }

  async function resolve(flagId: number) {
    const note = window.prompt('Note de résolution (optionnel) ?') ?? undefined
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
    <section className="space-y-3">
      <h2 className="text-xl font-semibold">Génération de contenu</h2>

      {message && <div className="bg-green-100 text-green-800 p-3 rounded">{message}</div>}
      {error && <div className="bg-red-100 text-red-800 p-3 rounded">{error}</div>}

      {mix && (
        <div className="text-sm text-slate-600">
          Mix actuel ({mix.total_themes} thème(s)) :{' '}
          {mix.mix.map((m) => `${m.category} ${Math.round(m.current_ratio * 100)}%/${Math.round(m.target_ratio * 100)}%`).join(' · ')}
          {' — '}recommandé : <strong>{mix.recommended_category}</strong>
        </div>
      )}

      <div className="flex gap-2">
        <input
          className="border p-2 rounded flex-1"
          placeholder="Sujet (ex: Napoléon)"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
        />
        <select
          className="border p-2 rounded"
          value={category}
          onChange={(e) => setCategory(e.target.value as ThemeCategory | '')}
        >
          <option value="">Catégorie recommandée</option>
          {THEME_CATEGORIES.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <button className="px-4 py-2 bg-green-600 text-white rounded disabled:opacity-50" onClick={generate} disabled={generating}>
          {generating ? 'Génération...' : 'Générer'}
        </button>
      </div>

      <h3 className="font-semibold mt-4">Suggestions en attente ({suggestions.length})</h3>
      {suggestions.map((s) => (
        <div key={s.id} className="border rounded p-3 space-y-2">
          <div className="font-medium">{s.generated_theme_name} — {s.generated_category} (sujet : {s.topic})</div>
          <ul className="text-sm list-disc pl-5">
            {s.generated_questions.map((q, i) => (
              <li key={i}>{q.text} — <em>{q.correct_answer}</em> ({q.difficulty})</li>
            ))}
          </ul>
          <div className="space-x-2">
            <button className="text-green-600" onClick={() => approve(s.id)}>Approuver</button>
            <button className="text-red-600" onClick={() => reject(s.id)}>Rejeter</button>
          </div>
        </div>
      ))}

      <h3 className="font-semibold mt-4">Signalements non résolus ({flags.length})</h3>
      <table className="w-full text-sm">
        <tbody>
          {flags.map((f) => (
            <tr key={f.id} className="border-b">
              <td className="p-2">Question #{f.question_id}</td>
              <td className="p-2">{f.reason}</td>
              <td className="p-2"><button className="text-blue-600" onClick={() => resolve(f.id)}>Résoudre</button></td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 className="font-semibold mt-4">Historique récent</h3>
      <table className="w-full text-sm">
        <tbody>
          {history.map((h) => (
            <tr key={h.id} className="border-b">
              <td className="p-2">{h.entity_type} #{h.entity_id}</td>
              <td className="p-2">{h.action}</td>
              <td className="p-2 text-slate-500">{h.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

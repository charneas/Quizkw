import { useEffect, useRef, useState } from 'react'
import AdminLayout from '../components/AdminLayout'
import ConfirmModal from '../components/ConfirmModal'
import type { Theme, Question, Difficulty, QuestionStatsResponse } from '../types'
import {
  adminListThemes,
  adminListQuestions,
  adminCreateQuestion,
  adminUpdateQuestion,
  adminDeleteQuestion,
  adminGetQuestionStats,
} from '../services/api'

const DIFFICULTIES: Difficulty[] = ['easy', 'medium', 'hard']
const DIFFICULTY_POINTS: Record<Difficulty, number> = { easy: 2, medium: 4, hard: 6 }
const QUESTIONS_PER_PAGE = 20

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

export default function AdminQuestions() {
  const [themes, setThemes] = useState<Theme[]>([])
  const [questions, setQuestions] = useState<Question[]>([])
  const [filterThemeId, setFilterThemeId] = useState<number | ''>('')
  const [questionSearch, setQuestionSearch] = useState('')
  const [questionForm, setQuestionForm] = useState(emptyQuestionForm())
  const [editingQuestionId, setEditingQuestionId] = useState<number | null>(null)
  const questionFormRef = useRef<HTMLElement>(null)
  const [statsByQuestion, setStatsByQuestion] = useState<Record<number, QuestionStatsResponse>>({})
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirmDeleteQuestionId, setConfirmDeleteQuestionId] = useState<number | null>(null)
  const [questionPage, setQuestionPage] = useState(0)

  async function refreshThemes() {
    setThemes(await adminListThemes())
  }

  async function refreshQuestions(themeId?: number) {
    setQuestions(await adminListQuestions(themeId))
  }

  useEffect(() => {
    refreshThemes().catch((e) => setError(String(e)))
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
    <AdminLayout>
      <div className="max-w-5xl mx-auto space-y-4 text-text">
        <h1 className="text-2xl font-bold">Questions</h1>

        {message && <div className="bg-surface-raised text-success p-3 rounded-lg border border-success">{message}</div>}
        {error && <div className="bg-surface-raised text-danger p-3 rounded-lg border border-danger">{error}</div>}

        <section className="card space-y-3" ref={questionFormRef}>
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
        </section>

        <section className="card space-y-3">
          <table className="w-full text-sm">
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
        </section>

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
    </AdminLayout>
  )
}

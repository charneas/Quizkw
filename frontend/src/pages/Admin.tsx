import { Link } from 'react-router-dom'
import AdminLayout from '../components/AdminLayout'
import type { Theme, Question } from '../types'
import { adminExportContent, adminImportContent } from '../services/api'
import { useState } from 'react'

export default function Admin() {
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  function showMessage(text: string) {
    setMessage(text)
    setError(null)
    window.setTimeout(() => setMessage(null), 4000)
  }

  function showError(err: unknown) {
    setError(err instanceof Error ? err.message : String(err))
  }

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
    } catch (e) {
      showError(e)
    } finally {
      event.target.value = ''
    }
  }

  return (
    <AdminLayout>
      <div className="max-w-5xl mx-auto space-y-6 text-text">
        <h1 className="text-2xl font-bold">Administration du contenu</h1>

        {message && <div className="bg-surface-raised text-success p-3 rounded-lg border border-success">{message}</div>}
        {error && <div className="bg-surface-raised text-danger p-3 rounded-lg border border-danger">{error}</div>}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Link to="/admin/themes" className="card hover:border-brand transition-colors block">
            <h2 className="text-lg font-semibold mb-1">Thèmes</h2>
            <p className="text-sm text-text-muted">Créer, éditer et supprimer les thèmes de questions.</p>
          </Link>
          <Link to="/admin/questions" className="card hover:border-brand transition-colors block">
            <h2 className="text-lg font-semibold mb-1">Questions</h2>
            <p className="text-sm text-text-muted">Créer, éditer et supprimer les questions, consulter leurs statistiques.</p>
          </Link>
          <Link to="/admin/content/generate" className="card hover:border-brand transition-colors block">
            <h2 className="text-lg font-semibold mb-1">Génération de contenu</h2>
            <p className="text-sm text-text-muted">Générer des questions via Wikipedia + IA, valider les suggestions, gérer les signalements.</p>
          </Link>
        </div>

        <section className="card space-y-3">
          <h2 className="text-xl font-semibold">Export / Import</h2>
          <div className="flex gap-3">
            <button className="btn-primary" onClick={exportContent}>
              Exporter le contenu (JSON)
            </button>
            <label className="btn-secondary cursor-pointer inline-flex items-center">
              Importer un fichier JSON
              <input type="file" accept="application/json" className="hidden" onChange={importContent} />
            </label>
          </div>
        </section>
      </div>
    </AdminLayout>
  )
}

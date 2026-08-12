import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import type { Difficulty, Proposition, ThemeCategory } from '../types'
import { adminListPendingPropositions, adminListThemes, adminUpdateProposition } from '../services/api'
import type { Theme } from '../types'
import AdminLayout from '../components/AdminLayout'

const DIFFICULTIES: Difficulty[] = ['easy', 'medium', 'hard']
const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  easy: 'Facile',
  medium: 'Moyen',
  hard: 'Difficile',
}
const THEME_CATEGORIES: ThemeCategory[] = ['serious', 'pop_culture', 'whimsical']

const NEW_THEME_VALUE = '__new__'

export default function AdminPropositionEdit() {
  const { id } = useParams<{ id: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const propositionId = Number(id)

  const [proposition, setProposition] = useState<Proposition | null>(
    (location.state as { proposition?: Proposition } | null)?.proposition ?? null
  )
  const [themes, setThemes] = useState<Theme[]>([])
  const [text, setText] = useState('')
  const [correctAnswer, setCorrectAnswer] = useState('')
  const [wrongAnswers, setWrongAnswers] = useState(['', '', ''])
  const [difficulty, setDifficulty] = useState<Difficulty>('easy')
  const [imageUrl, setImageUrl] = useState('')
  const [themeChoice, setThemeChoice] = useState<string>('')
  const [newThemeName, setNewThemeName] = useState('')
  const [newThemeCategory, setNewThemeCategory] = useState<ThemeCategory>('serious')
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    adminListThemes().then(setThemes).catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  useEffect(() => {
    if (proposition) return
    // Navigation directe (pas de state) : pas d'endpoint GET par id dans cette
    // story, on retrouve la proposition dans la liste des propositions en attente.
    adminListPendingPropositions()
      .then((list) => {
        const found = list.find((p) => p.id === propositionId)
        if (found) setProposition(found)
        else setError('Proposition introuvable (déjà traitée ou inexistante).')
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [proposition, propositionId])

  useEffect(() => {
    if (!proposition) return
    setText(proposition.text)
    setCorrectAnswer(proposition.correct_answer)
    setWrongAnswers([
      proposition.wrong_answers[0] ?? '',
      proposition.wrong_answers[1] ?? '',
      proposition.wrong_answers[2] ?? '',
    ])
    setDifficulty(proposition.difficulty)
    setImageUrl(proposition.image_url ?? '')
    setThemeChoice(proposition.theme_id === null ? '' : String(proposition.theme_id))
  }, [proposition])

  function updateWrongAnswer(index: number, value: string) {
    setWrongAnswers((prev) => prev.map((w, i) => (i === index ? value : w)))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setIsSaving(true)
    try {
      const cleanedWrongAnswers = wrongAnswers.map((w) => w.trim()).filter((w) => w.length > 0)
      const isNewTheme = themeChoice === NEW_THEME_VALUE
      await adminUpdateProposition(propositionId, {
        text,
        correct_answer: correctAnswer,
        wrong_answers: cleanedWrongAnswers,
        difficulty,
        image_url: imageUrl.trim() === '' ? null : imageUrl.trim(),
        ...(isNewTheme
          ? { new_theme: { name: newThemeName, category: newThemeCategory, difficulty_level: 5 } }
          : { theme_id: themeChoice === '' ? null : Number(themeChoice) }),
      })
      navigate('/admin/propositions')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsSaving(false)
    }
  }

  if (!proposition) {
    return (
      <AdminLayout>
      <div>
        <div className="max-w-2xl mx-auto">
          {error ? <p className="text-sm text-red-500">{error}</p> : <p className="text-text-muted">Chargement...</p>}
        </div>
      </div>
      </AdminLayout>
    )
  }

  return (
    <AdminLayout>
    <div>
      <div className="max-w-2xl mx-auto space-y-4">
        <h1 className="text-xl font-semibold">Éditer la proposition</h1>

        <form onSubmit={handleSubmit} className="card space-y-4">
          <div>
            <label className="block text-sm mb-1" htmlFor="prop-text">Question</label>
            <input id="prop-text" className="input-field" value={text} onChange={(e) => setText(e.target.value)} required />
          </div>

          <div>
            <label className="block text-sm mb-1" htmlFor="prop-correct">Bonne réponse</label>
            <input
              id="prop-correct"
              className="input-field"
              value={correctAnswer}
              onChange={(e) => setCorrectAnswer(e.target.value)}
              required
            />
          </div>

          <div className="space-y-2">
            <span className="block text-sm">Mauvaises réponses (jusqu'à 3)</span>
            {wrongAnswers.map((w, i) => (
              <input
                key={i}
                className="input-field"
                value={w}
                onChange={(e) => updateWrongAnswer(i, e.target.value)}
                placeholder={`Mauvaise réponse ${i + 1}`}
              />
            ))}
          </div>

          <div>
            <label className="block text-sm mb-1" htmlFor="prop-difficulty">Difficulté</label>
            <select
              id="prop-difficulty"
              className="input-field"
              value={difficulty}
              onChange={(e) => setDifficulty(e.target.value as Difficulty)}
            >
              {DIFFICULTIES.map((d) => (
                <option key={d} value={d}>{DIFFICULTY_LABELS[d]}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm mb-1" htmlFor="prop-image-url">Lien vers une image (facultatif)</label>
            <input
              id="prop-image-url"
              type="url"
              className="input-field"
              value={imageUrl}
              onChange={(e) => setImageUrl(e.target.value)}
              placeholder="https://..."
            />
          </div>

          <div>
            <label className="block text-sm mb-1" htmlFor="prop-theme">Thème</label>
            <select
              id="prop-theme"
              className="input-field"
              value={themeChoice}
              onChange={(e) => setThemeChoice(e.target.value)}
            >
              <option value="">À déterminer</option>
              {themes.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
              <option value={NEW_THEME_VALUE}>Créer un nouveau thème...</option>
            </select>
          </div>

          {themeChoice === NEW_THEME_VALUE && (
            <div className="space-y-2 pl-4 border-l-2 border-border">
              <div>
                <label className="block text-sm mb-1" htmlFor="new-theme-name">Nom du nouveau thème</label>
                <input
                  id="new-theme-name"
                  className="input-field"
                  value={newThemeName}
                  onChange={(e) => setNewThemeName(e.target.value)}
                  required
                />
              </div>
              <div>
                <label className="block text-sm mb-1" htmlFor="new-theme-category">Catégorie</label>
                <select
                  id="new-theme-category"
                  className="input-field"
                  value={newThemeCategory}
                  onChange={(e) => setNewThemeCategory(e.target.value as ThemeCategory)}
                >
                  {THEME_CATEGORIES.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {error && <p className="text-sm text-red-500">{error}</p>}

          <div className="flex gap-3">
            <button type="submit" className="btn-primary" disabled={isSaving}>
              {isSaving ? 'Enregistrement...' : 'Enregistrer'}
            </button>
            <button type="button" className="btn-secondary" onClick={() => navigate('/admin/propositions')}>
              Annuler
            </button>
          </div>
        </form>
      </div>
    </div>
    </AdminLayout>
  )
}

import { useEffect, useState } from 'react'
import { listThemesForProposition, submitProposition } from '../services/api'
import type { Difficulty, Theme } from '../types'

const DIFFICULTIES: { value: Difficulty; label: string }[] = [
  { value: 'easy', label: 'Facile' },
  { value: 'medium', label: 'Moyenne' },
  { value: 'hard', label: 'Difficile' },
]

const EMPTY_FORM = {
  text: '',
  correctAnswer: '',
  wrongAnswers: ['', '', ''],
  themeId: '',
  difficulty: '' as Difficulty | '',
  imageUrl: '',
}

function Propositions() {
  const [themes, setThemes] = useState<Theme[]>([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [confirmation, setConfirmation] = useState('')

  useEffect(() => {
    listThemesForProposition()
      .then(setThemes)
      .catch(() => setThemes([]))
  }, [])

  const isValid = form.text.trim() !== '' && form.correctAnswer.trim() !== '' && form.difficulty !== ''

  const handleWrongAnswerChange = (index: number, value: string) => {
    setForm((prev) => {
      const wrongAnswers = [...prev.wrongAnswers]
      wrongAnswers[index] = value
      return { ...prev, wrongAnswers }
    })
  }

  const handleSubmit = async () => {
    if (!isValid || isSubmitting) return
    setIsSubmitting(true)
    setError('')
    try {
      await submitProposition({
        text: form.text.trim(),
        correct_answer: form.correctAnswer.trim(),
        wrong_answers: form.wrongAnswers.map((a) => a.trim()).filter((a) => a !== ''),
        theme_id: form.themeId === '' ? undefined : Number(form.themeId),
        difficulty: form.difficulty as Difficulty,
        image_url: form.imageUrl.trim() === '' ? undefined : form.imageUrl.trim(),
      })
      setConfirmation('Votre proposition a bien été enregistrée. Elle sera vérifiée avant d\'être ajoutée au jeu.')
      setForm(EMPTY_FORM)
    } catch (err) {
      setConfirmation('')
      setError(err instanceof Error ? err.message : 'Erreur lors de la soumission')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <h1 className="font-display font-extrabold text-3xl tracking-tight text-text">
            Proposer une question
          </h1>
        </div>

        <div className="card space-y-4">
          <div>
            <label htmlFor="proposition-text" className="block text-sm text-text-muted mb-1">Question *</label>
            <input
              id="proposition-text"
              type="text"
              value={form.text}
              onChange={(e) => setForm((prev) => ({ ...prev, text: e.target.value }))}
              className="input-field"
              maxLength={500}
            />
          </div>

          <div>
            <label htmlFor="proposition-correct-answer" className="block text-sm text-text-muted mb-1">Bonne réponse *</label>
            <input
              id="proposition-correct-answer"
              type="text"
              value={form.correctAnswer}
              onChange={(e) => setForm((prev) => ({ ...prev, correctAnswer: e.target.value }))}
              className="input-field"
              maxLength={200}
            />
          </div>

          <div>
            <label htmlFor="proposition-wrong-answer-0" className="block text-sm text-text-muted mb-1">Mauvaises réponses (facultatif)</label>
            <div className="space-y-2">
              {form.wrongAnswers.map((value, index) => (
                <input
                  key={index}
                  id={`proposition-wrong-answer-${index}`}
                  aria-label={`Mauvaise réponse ${index + 1}`}
                  type="text"
                  value={value}
                  onChange={(e) => handleWrongAnswerChange(index, e.target.value)}
                  className="input-field"
                  maxLength={200}
                />
              ))}
            </div>
          </div>

          <div>
            <label htmlFor="proposition-theme" className="block text-sm text-text-muted mb-1">Thème</label>
            <select
              id="proposition-theme"
              value={form.themeId}
              onChange={(e) => setForm((prev) => ({ ...prev, themeId: e.target.value }))}
              className="input-field"
            >
              <option value="">À déterminer</option>
              {themes.map((theme) => (
                <option key={theme.id} value={theme.id}>
                  {theme.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="proposition-image-url" className="block text-sm text-text-muted mb-1">
              Lien vers une image (facultatif)
            </label>
            <input
              id="proposition-image-url"
              type="url"
              value={form.imageUrl}
              onChange={(e) => setForm((prev) => ({ ...prev, imageUrl: e.target.value }))}
              className="input-field"
              placeholder="https://..."
            />
          </div>

          <div>
            <label className="block text-sm text-text-muted mb-1">Difficulté *</label>
            <div className="flex gap-3">
              {DIFFICULTIES.map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setForm((prev) => ({ ...prev, difficulty: value }))}
                  className={`flex-1 min-h-[44px] py-2 px-4 rounded-lg border transition-colors ${
                    form.difficulty === value
                      ? 'bg-brand-600 border-brand text-white'
                      : 'bg-surface border-border text-text-muted hover:border-brand'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {error && (
            <div className="text-danger text-sm text-center bg-danger/10 rounded-lg p-2">
              {error}
            </div>
          )}

          {confirmation && (
            <div className="text-sm text-center bg-brand-muted/20 text-text rounded-lg p-2">
              {confirmation}
            </div>
          )}

          <button
            onClick={handleSubmit}
            disabled={!isValid || isSubmitting}
            className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? 'Envoi...' : 'Valider'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default Propositions

import { useState } from 'react'
import { flagQuestion } from '../services/api'

interface FlagQuestionButtonProps {
  questionId: number
}

// Story F.2, AC #4 : permet à un joueur de signaler une question incorrecte
// pendant la partie. Route publique (pas de préfixe /admin, pas d'auth).
function FlagQuestionButton({ questionId }: FlagQuestionButtonProps) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    if (!reason.trim()) return
    try {
      await flagQuestion(questionId, reason.trim())
      setSent(true)
      setOpen(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  if (sent) {
    return <span className="text-xs text-text-muted">Signalement envoyé, merci.</span>
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-xs text-text-muted hover:text-danger underline"
      >
        Signaler cette question
      </button>
    )
  }

  return (
    <div className="flex items-center gap-2 text-xs">
      <input
        type="text"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Pourquoi ? (réponse fausse, faute...)"
        className="input-field flex-1 text-xs py-1"
      />
      <button type="button" onClick={submit} className="text-danger underline">
        Envoyer
      </button>
      <button type="button" onClick={() => setOpen(false)} className="text-text-muted underline">
        Annuler
      </button>
      {error && <span className="text-danger">{error}</span>}
    </div>
  )
}

export default FlagQuestionButton

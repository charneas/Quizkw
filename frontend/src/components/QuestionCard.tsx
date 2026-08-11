import { useState } from 'react'
import type { QuestionResponse } from '../types'
import FlagQuestionButton from './FlagQuestionButton'

interface QuestionCardProps {
  question: QuestionResponse
  onAnswer: (answer: string) => void
  isBonusActive?: boolean
}

function QuestionCard({
  question,
  onAnswer,
  isBonusActive = false,
}: QuestionCardProps) {
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null)
  const [confirmed, setConfirmed] = useState(false)

  const difficultyColors = {
    easy: 'bg-green-900/30 text-green-400 border-green-600',
    medium: 'bg-yellow-900/30 text-yellow-400 border-yellow-600',
    hard: 'bg-red-900/30 text-red-400 border-red-600',
  }

  const difficultyLabels = {
    easy: 'Facile',
    medium: 'Moyen',
    hard: 'Difficile',
  }

  const handleConfirm = () => {
    if (selectedAnswer) {
      setConfirmed(true)
      onAnswer(selectedAnswer)
    }
  }

  // Calcul des points affichés en direct si le BONUS est actif
  const displayPoints = isBonusActive 
    ? question.question.points * 2 
    : question.question.points

  return (
    <div className="card relative overflow-hidden">
      {/* En-tête de la question */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-xs px-2 py-1 rounded border ${difficultyColors[question.question.difficulty]}`}>
            {difficultyLabels[question.question.difficulty]}
          </span>
          <span className="text-xs text-text-muted">
            {question.question.category}
          </span>
        </div>

        {/* Affichage des points (avec effet BONUS) */}
        <div className="flex items-center gap-2">
          {isBonusActive && (
            <span className="text-xs px-2 py-0.5 rounded bg-amber-500/20 border border-amber-500/50 text-amber-300 font-extrabold tracking-wide uppercase animate-bounce">
              ⭐ Bonus x2
            </span>
          )}
          <span className={`font-bold ${isBonusActive ? 'text-amber-400 text-lg' : 'text-brand'}`}>
            {displayPoints} pts
          </span>
        </div>
      </div>

      {/* Texte de la question */}
      <h3 className="text-xl font-semibold mb-6 leading-relaxed">
        {question.question.text}
      </h3>

      {/* Options */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
        {question.options.map((option, index) => (
          <button
            key={index}
            onClick={() => !confirmed && setSelectedAnswer(option)}
            disabled={confirmed}
            className={`p-4 rounded-lg text-left transition-all border-2 ${
              selectedAnswer === option
                ? 'bg-brand-muted/30 border-brand text-text'
                : 'bg-surface border-border text-text-muted hover:border-brand hover:bg-surface-raised'
            } ${confirmed ? 'cursor-not-allowed opacity-75' : 'cursor-pointer'}`}
          >
            <span className="text-sm font-medium text-text-muted mr-2">
              {String.fromCharCode(65 + index)}.
            </span>
            {option}
          </button>
        ))}
      </div>

      {/* Bouton confirmer */}
      {selectedAnswer && !confirmed && (
        <button
          onClick={handleConfirm}
          className="btn-primary w-full"
        >
          ✓ Confirmer la réponse
        </button>
      )}

      <div className="mt-3 text-right">
        <FlagQuestionButton questionId={question.question.id} />
      </div>
    </div>
  )
}

export default QuestionCard
import { useState } from 'react'
import type { QuestionResponse } from '../types'

interface QuestionCardProps {
  question: QuestionResponse
  onAnswer: (answer: string) => void
}

function QuestionCard({ question, onAnswer }: QuestionCardProps) {
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

  return (
    <div className="card">
      {/* En-tête de la question */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2 py-1 rounded border ${difficultyColors[question.question.difficulty]}`}>
            {difficultyLabels[question.question.difficulty]}
          </span>
          <span className="text-xs text-slate-500">
            {question.question.category}
          </span>
        </div>
        <span className="text-game-accent font-bold">
          {question.question.points} pts
        </span>
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
                ? 'bg-primary-900/50 border-primary-500 text-white'
                : 'bg-slate-800 border-slate-700 text-slate-300 hover:border-slate-500 hover:bg-slate-750'
            } ${confirmed ? 'cursor-not-allowed opacity-75' : 'cursor-pointer'}`}
          >
            <span className="text-sm font-medium text-slate-500 mr-2">
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
    </div>
  )
}

export default QuestionCard

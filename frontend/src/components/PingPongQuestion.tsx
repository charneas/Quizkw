import { useState, useEffect } from 'react'
import type { Team } from '../types'

interface PingPongTheme {
  id: number
  title: string
  description: string | null
  correct_answers: string[]
  min_answers_to_win: number
}

interface PingPongQuestionProps {
  theme: PingPongTheme
  currentTeam: Team
  onSubmit: (answers: string[]) => void
  timeLimit?: number
}

function PingPongQuestion({ theme, currentTeam, onSubmit, timeLimit = 60 }: PingPongQuestionProps) {
  const [answers, setAnswers] = useState<string[]>([''])
  const [timeLeft, setTimeLeft] = useState(timeLimit)

  useEffect(() => {
    const timer = setInterval(() => {
      setTimeLeft(prev => {
        if (prev <= 1) {
          clearInterval(timer)
          // Auto-submit when time runs out
          handleSubmit()
          return 0
        }
        return prev - 1
      })
    }, 1000)

    return () => clearInterval(timer)
  }, [])

  const addAnswer = () => {
    setAnswers([...answers, ''])
  }

  const updateAnswer = (index: number, value: string) => {
    const newAnswers = [...answers]
    newAnswers[index] = value
    setAnswers(newAnswers)
  }

  const removeAnswer = (index: number) => {
    if (answers.length > 1) {
      const newAnswers = answers.filter((_, i) => i !== index)
      setAnswers(newAnswers)
    }
  }

  const handleSubmit = () => {
    // Filter out empty answers
    const validAnswers = answers.filter(a => a.trim().length > 0)
    if (validAnswers.length > 0) {
      onSubmit(validAnswers)
    }
  }

  const validAnswersCount = answers.filter(a => a.trim().length > 0).length

  return (
    <div className="card">
      {/* Header */}
      <div className="text-center mb-6">
        <div className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 rounded-full mb-4">
          <span className="text-2xl">🏓</span>
          <span className="font-bold text-white">PING-PONG</span>
        </div>
        <h2 className="text-2xl font-bold mb-2">{theme.title}</h2>
        {theme.description && (
          <p className="text-slate-400 text-sm">{theme.description}</p>
        )}
      </div>

      {/* Instructions */}
      <div className="bg-slate-700/50 rounded-lg p-4 mb-6">
        <div className="flex items-start gap-3">
          <div className="text-2xl">ℹ️</div>
          <div className="flex-1">
            <p className="text-sm text-slate-300 mb-2">
              <strong className="text-white">Règles :</strong>
            </p>
            <ul className="text-sm text-slate-400 space-y-1">
              <li>• Citez le plus de réponses correctes possible</li>
              <li>• <strong className="text-game-accent">+2 points</strong> par réponse correcte</li>
              <li>• <strong className="text-game-success">+3 points bonus</strong> si vous trouvez toutes les réponses</li>
              <li>• Minimum {theme.min_answers_to_win} réponses pour gagner</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Timer */}
      <div className="mb-6">
        <div className="flex justify-between items-center mb-2">
          <span className="text-sm text-slate-400">Temps restant</span>
          <span className={`text-2xl font-bold ${
            timeLeft <= 10 ? 'text-game-danger animate-pulse' : 'text-game-accent'
          }`}>
            {timeLeft}s
          </span>
        </div>
        <div className="w-full bg-slate-700 rounded-full h-2 overflow-hidden">
          <div 
            className={`h-full transition-all duration-1000 ${
              timeLeft <= 10 ? 'bg-game-danger' : 'bg-game-accent'
            }`}
            style={{ width: `${(timeLeft / timeLimit) * 100}%` }}
          />
        </div>
      </div>

      {/* Équipe courante */}
      <div className="text-center mb-6 p-3 bg-slate-700/30 rounded-lg">
        <p className="text-sm text-slate-400">C'est au tour de</p>
        <p className="text-xl font-bold text-game-accent">{currentTeam.name}</p>
      </div>

      {/* Answer inputs */}
      <div className="space-y-3 mb-6">
        {answers.map((answer, index) => (
          <div key={index} className="flex gap-2">
            <div className="flex-shrink-0 w-8 h-10 bg-slate-700 rounded flex items-center justify-center text-sm font-bold text-slate-400">
              {index + 1}
            </div>
            <input
              type="text"
              value={answer}
              onChange={(e) => updateAnswer(index, e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && answer.trim()) {
                  e.preventDefault()
                  addAnswer()
                  // Focus next input after a short delay
                  setTimeout(() => {
                    const inputs = document.querySelectorAll('input[type="text"]')
                    const nextInput = inputs[index + 1] as HTMLInputElement
                    if (nextInput) nextInput.focus()
                  }, 50)
                }
              }}
              placeholder="Votre réponse..."
              className="flex-1 px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg focus:outline-none focus:border-game-accent transition-colors"
              autoFocus={index === 0}
            />
            {answers.length > 1 && (
              <button
                onClick={() => removeAnswer(index)}
                className="flex-shrink-0 w-10 h-10 bg-red-900/50 hover:bg-red-900 text-red-300 rounded-lg transition-colors"
                title="Supprimer"
              >
                ✕
              </button>
            )}
          </div>
        ))}
      </div>

      {/* Add answer button */}
      <button
        onClick={addAnswer}
        className="w-full py-2 mb-4 border-2 border-dashed border-slate-600 hover:border-game-accent text-slate-400 hover:text-game-accent rounded-lg transition-colors"
      >
        + Ajouter une réponse
      </button>

      {/* Stats */}
      <div className="flex justify-center gap-8 mb-6 text-sm">
        <div className="text-center">
          <div className="text-2xl font-bold text-game-accent">{validAnswersCount}</div>
          <div className="text-slate-400">Réponses</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-game-success">{validAnswersCount * 2}</div>
          <div className="text-slate-400">Points potentiels</div>
        </div>
      </div>

      {/* Submit button */}
      <button
        onClick={handleSubmit}
        disabled={validAnswersCount === 0}
        className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
      >
        Valider {validAnswersCount > 0 && `(${validAnswersCount} ${validAnswersCount > 1 ? 'réponses' : 'réponse'})`}
      </button>

      {/* Hint */}
      <p className="text-center text-xs text-slate-500 mt-4">
        Appuyez sur Entrée pour ajouter rapidement une nouvelle réponse
      </p>
    </div>
  )
}

export default PingPongQuestion

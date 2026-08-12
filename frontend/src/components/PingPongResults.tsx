interface PingPongDuelResultsProps {
  theme: {
    id: number
    title: string
    description: string | null
    correct_answers: string[]
    min_answers_to_win: number
  }
  team1: {
    id: number
    name: string
    turns: number
    correctAnswers: string[]
  }
  team2: {
    id: number
    name: string
    turns: number
    correctAnswers: string[]
  }
  winnerTeamId: number
  winnerTeamName: string
  totalTurns: number
  answersUsed: string[]
  onContinue: () => void
  // BUG-505 (#37) : tentative qui a mis fin au duel, surclassable par l'host
  // si elle était en fait valable (synonyme, réponse partielle...).
  losingTurn?: { id: number; team_id: number; answer_given: string } | null
  onOverride?: (turnId: number) => void
  overriding?: boolean
}

function PingPongResults({
  theme,
  team1,
  team2,
  winnerTeamId,
  totalTurns,
  answersUsed,
  onContinue,
  losingTurn,
  onOverride,
  overriding,
}: PingPongDuelResultsProps) {
  const winner = winnerTeamId === team1.id ? team1 : team2
  const loser = winnerTeamId === team1.id ? team2 : team1
  // Points fixes pour la victoire du duel (backend : ping_pong_manager.py,
  // winner_points = 2), pas 2 points par bonne réponse donnée — l'affichage
  // gonflait artificiellement le total avec winner.correctAnswers.length * 2.
  const winnerPoints = 2

  return (
    <div className="card">
      {/* Header */}
      <div className="text-center mb-6">
        <div className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 rounded-full mb-4">
          <span className="text-2xl">🏓</span>
          <span className="font-bold text-white">RÉSULTATS DUEL</span>
        </div>
        <h2 className="text-xl font-bold mb-2">{theme.title}</h2>
      </div>

      {/* Winner announcement */}
      <div className="bg-gradient-to-r from-yellow-600/20 to-orange-600/20 border-2 border-yellow-500 rounded-lg p-6 mb-6 text-center">
        <div className="text-6xl mb-3">🏆</div>
        <h3 className="text-2xl font-bold text-yellow-400 mb-2">
          {winner.name} remporte le duel !
        </h3>
        <p className="text-text-muted">
          {winner.correctAnswers.length} réponses correctes • +{winnerPoints} points
        </p>
        <p className="text-sm text-text-muted mt-1">
          Duel terminé en {totalTurns} tours
        </p>
      </div>

      {/* Face-à-face */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        {/* Winner */}
        <div className="bg-yellow-900/20 border-2 border-yellow-700 rounded-lg p-4 text-center">
          <p className="text-xs text-text-muted uppercase tracking-wide mb-2">Vainqueur</p>
          <p className="text-xl font-bold text-yellow-400 mb-3">{winner.name} 👑</p>
          <div className="flex justify-center gap-4 text-sm">
            <div>
              <span className="text-2xl font-bold text-text">{winner.turns}</span>
              <p className="text-xs text-text-muted">tours joués</p>
            </div>
            <div>
              <span className="text-2xl font-bold text-success">{winner.correctAnswers.length}</span>
              <p className="text-xs text-text-muted">bonnes réponses</p>
            </div>
            <div>
              <span className="text-2xl font-bold text-brand">+{winnerPoints}</span>
              <p className="text-xs text-text-muted">points</p>
            </div>
          </div>
          {winner.correctAnswers.length > 0 && (
            <div className="mt-3 pt-3 border-t border-yellow-700/50">
              <p className="text-xs text-text-muted mb-2">Réponses données :</p>
              <div className="flex flex-wrap justify-center gap-1">
                {winner.correctAnswers.map((ans, i) => (
                  <span key={i} className="px-2 py-0.5 bg-success/10 text-success rounded text-xs">
                    {ans}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Loser */}
        <div className="bg-surface-raised border-2 border-border rounded-lg p-4 text-center">
          <p className="text-xs text-text-muted uppercase tracking-wide mb-2">Perdant</p>
          <p className="text-xl font-bold text-text-muted mb-3">{loser.name}</p>
          <div className="flex justify-center gap-4 text-sm">
            <div>
              <span className="text-2xl font-bold text-text">{loser.turns}</span>
              <p className="text-xs text-text-muted">tours joués</p>
            </div>
            <div>
              <span className="text-2xl font-bold text-text-muted">{loser.correctAnswers.length}</span>
              <p className="text-xs text-text-muted">bonnes réponses</p>
            </div>
            <div>
              <span className="text-2xl font-bold text-text-muted">0</span>
              <p className="text-xs text-text-muted">points</p>
            </div>
          </div>
          {loser.correctAnswers.length > 0 && (
            <div className="mt-3 pt-3 border-t border-border">
              <p className="text-xs text-text-muted mb-2">Réponses données :</p>
              <div className="flex flex-wrap justify-center gap-1">
                {loser.correctAnswers.map((ans, i) => (
                  <span key={i} className="px-2 py-0.5 bg-surface text-text-muted rounded text-xs">
                    {ans}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* BUG-505 (#37) : surclassement manuel host de la réponse qui a
          scellé le duel — pour les synonymes / réponses partielles valides
          que la liste de réponses acceptées n'anticipait pas. */}
      {losingTurn && onOverride && (
        <div className="bg-surface-raised border border-dashed border-border rounded-lg p-4 mb-6 text-center">
          <p className="text-sm text-text-muted mb-3">
            La réponse "<span className="text-text font-semibold">{losingTurn.answer_given}</span>" de{' '}
            <span className="font-semibold">{loser.name}</span> était en fait valable ?
          </p>
          <button
            onClick={() => onOverride(losingTurn.id)}
            disabled={overriding}
            className="btn-secondary disabled:opacity-50"
          >
            {overriding ? 'Validation...' : `Valider quand même et faire continuer ${loser.name}`}
          </button>
        </div>
      )}

      {/* Toutes les réponses possibles */}
      <div className="bg-surface-raised rounded-lg p-4 mb-6">
        <h4 className="text-sm font-semibold text-text-muted uppercase tracking-wide mb-3">
          Toutes les réponses possibles ({theme.correct_answers.length})
        </h4>
        <div className="flex flex-wrap gap-2">
          {theme.correct_answers.map((answer, index) => {
            const wasGiven = answersUsed.some(
              (a) => a.toLowerCase() === answer.toLowerCase()
            )
            return (
              <span
                key={index}
                className={`px-3 py-1 rounded-full text-sm ${
                  wasGiven
                    ? 'bg-success/10 text-success border border-success/30'
                    : 'bg-surface text-text-muted border border-border'
                }`}
              >
                {answer}
                {wasGiven && ' ✓'}
              </span>
            )
          })}
        </div>
      </div>

      {/* Continue button */}
      <button onClick={onContinue} className="btn-primary w-full">
        Continuer le jeu →
      </button>
    </div>
  )
}

export default PingPongResults
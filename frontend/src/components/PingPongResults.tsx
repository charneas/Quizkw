import type { Team } from '../types'

interface PingPongResultsProps {
  theme: {
    id: number
    title: string
    description: string | null
    correct_answers: string[]
    min_answers_to_win: number
  }
  teamResults: Array<{
    team_id: number
    team_name: string
    correct_count: number
    points: number
    answers: string[]
  }>
  winnerTeamId: number | null
  currentTeam: Team
  onContinue: () => void
}

function PingPongResults({ theme, teamResults, winnerTeamId, currentTeam, onContinue }: PingPongResultsProps) {
  // Sort teams by correct count (descending)
  const sortedResults = [...teamResults].sort((a, b) => b.correct_count - a.correct_count)
  
  const currentTeamResult = teamResults.find(r => r.team_id === currentTeam.id)

  return (
    <div className="card">
      {/* Header */}
      <div className="text-center mb-6">
        <div className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-600 rounded-full mb-4">
          <span className="text-2xl">🏓</span>
          <span className="font-bold text-white">RÉSULTATS PING-PONG</span>
        </div>
        <h2 className="text-xl font-bold mb-2">{theme.title}</h2>
      </div>

      {/* Winner announcement */}
      {winnerTeamId && (
        <div className="bg-gradient-to-r from-yellow-600/20 to-orange-600/20 border-2 border-yellow-500 rounded-lg p-6 mb-6 text-center">
          <div className="text-6xl mb-3">🏆</div>
          <h3 className="text-2xl font-bold text-yellow-400 mb-2">
            {sortedResults[0]?.team_name} remporte le Ping-Pong!
          </h3>
          <p className="text-slate-300">
            {sortedResults[0]?.correct_count} réponses correctes • +{sortedResults[0]?.points} points
          </p>
        </div>
      )}

      {/* Current team result highlight */}
      {currentTeamResult && (
        <div className="bg-slate-700/50 rounded-lg p-4 mb-6 border-2 border-game-accent">
          <div className="text-center">
            <p className="text-sm text-slate-400 mb-2">Votre performance</p>
            <p className="text-2xl font-bold text-game-accent mb-1">{currentTeam.name}</p>
            <div className="flex justify-center gap-6 text-sm">
              <div>
                <span className="text-3xl font-bold text-white">{currentTeamResult.correct_count}</span>
                <span className="text-slate-400"> / {theme.correct_answers.length}</span>
                <div className="text-xs text-slate-500">réponses correctes</div>
              </div>
              <div>
                <span className="text-3xl font-bold text-game-success">+{currentTeamResult.points}</span>
                <div className="text-xs text-slate-500">points gagnés</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Team rankings */}
      <div className="space-y-3 mb-6">
        <h4 className="text-sm font-semibold text-slate-400 uppercase tracking-wide">Classement</h4>
        {sortedResults.map((result, index) => (
          <div
            key={result.team_id}
            className={`p-4 rounded-lg border-2 ${
              result.team_id === currentTeam.id
                ? 'bg-game-accent/10 border-game-accent'
                : result.team_id === winnerTeamId
                ? 'bg-yellow-900/20 border-yellow-700'
                : 'bg-slate-700/30 border-slate-700'
            }`}
          >
            <div className="flex items-center gap-4">
              {/* Rank */}
              <div className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center font-bold text-lg ${
                index === 0 ? 'bg-yellow-500 text-black' :
                index === 1 ? 'bg-slate-400 text-black' :
                index === 2 ? 'bg-orange-700 text-white' :
                'bg-slate-700 text-slate-400'
              }`}>
                {index + 1}
              </div>

              {/* Team info */}
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-bold">{result.team_name}</span>
                  {result.team_id === winnerTeamId && <span className="text-xl">👑</span>}
                </div>
                <div className="text-sm text-slate-400">
                  {result.correct_count} bonnes réponses • +{result.points} points
                </div>
              </div>

              {/* Score */}
              <div className="text-right">
                <div className="text-2xl font-bold text-game-success">+{result.points}</div>
              </div>
            </div>

            {/* User's answers preview */}
            {result.answers.length > 0 && (
              <div className="mt-3 pt-3 border-t border-slate-600">
                <p className="text-xs text-slate-500 mb-2">Réponses données:</p>
                <div className="flex flex-wrap gap-2">
                  {result.answers.slice(0, 5).map((answer, i) => (
                    <span
                      key={i}
                      className="px-2 py-1 text-xs bg-slate-700 rounded"
                    >
                      {answer}
                    </span>
                  ))}
                  {result.answers.length > 5 && (
                    <span className="px-2 py-1 text-xs text-slate-500">
                      +{result.answers.length - 5} autres
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* All correct answers */}
      <div className="bg-slate-700/30 rounded-lg p-4 mb-6">
        <h4 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">
          Toutes les réponses possibles ({theme.correct_answers.length})
        </h4>
        <div className="flex flex-wrap gap-2">
          {theme.correct_answers.map((answer, index) => (
            <span
              key={index}
              className="px-3 py-1 bg-slate-600 text-white rounded-full text-sm"
            >
              {answer}
            </span>
          ))}
        </div>
      </div>

      {/* Continue button */}
      <button
        onClick={onContinue}
        className="btn-primary w-full"
      >
        Continuer le jeu →
      </button>
    </div>
  )
}

export default PingPongResults

import type { Theme } from '../types'

interface ThemeSelectorProps {
  themes: Theme[]
  onSelectTheme: (theme: Theme) => void
  gameCode: string
}

function ThemeSelectorComponent({ themes, onSelectTheme, gameCode: _gameCode }: ThemeSelectorProps) {
  const getCategoryColor = (category: string) => {
    switch (category) {
      case 'serious':
        return 'bg-brand-600'
      case 'pop_culture':
        return 'bg-brand-600'
      case 'whimsical':
        return 'bg-brand-muted'
      default:
        return 'bg-surface-raised'
    }
  }

  const getCategoryText = (category: string) => {
    switch (category) {
      case 'serious':
        return 'Serious'
      case 'pop_culture':
        return 'Pop Culture'
      case 'whimsical':
        return 'Whimsical'
      default:
        return category
    }
  }

  const getDifficultyStars = (difficulty: number) => {
    return '★'.repeat(difficulty) + '☆'.repeat(10 - difficulty)
  }

  return (
    <div className="bg-surface rounded-lg p-6">
      <h2 className="text-2xl font-display font-semibold text-text mb-2">Choose Your Theme</h2>
      <p className="text-text-muted mb-6">Select one of these 3 random themes for your Round 2 questions</p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {themes.map((theme) => (
          <div
            key={theme.id}
            className="bg-surface-raised rounded-lg overflow-hidden hover:bg-border border border-border transition-colors cursor-pointer"
            onClick={() => onSelectTheme(theme)}
          >
            <div className={`h-2 ${getCategoryColor(theme.category)}`} />
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <span className={`px-3 py-1 rounded-full text-text text-sm ${getCategoryColor(theme.category)}`}>
                  {getCategoryText(theme.category)}
                </span>
                <span className="text-text-muted text-sm">Difficulty: {theme.difficulty_level}/10</span>
              </div>

              <h3 className="text-xl font-bold text-text mb-3">{theme.name}</h3>

              {theme.description && (
                <p className="text-text-muted mb-4">{theme.description}</p>
              )}

              <div className="mb-4">
                <p className="text-text-muted text-sm mb-1">Difficulty Level:</p>
                <div className="text-yellow-400 text-lg">
                  {getDifficultyStars(theme.difficulty_level)}
                </div>
              </div>

              <div className="text-center">
                <button className="btn-primary">
                  Select This Theme
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 text-center text-text-muted">
        <p>Each theme has 10 questions with progressive difficulty (1-10)</p>
        <p>Points awarded: 1-10 points per question based on difficulty</p>
      </div>
    </div>
  )
}

export default ThemeSelectorComponent
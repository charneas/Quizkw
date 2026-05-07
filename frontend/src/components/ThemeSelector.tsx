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
        return 'bg-blue-600'
      case 'pop_culture':
        return 'bg-purple-600'
      case 'whimsical':
        return 'bg-pink-600'
      default:
        return 'bg-gray-600'
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
    <div className="bg-gray-800 rounded-lg p-6">
      <h2 className="text-2xl font-bold text-white mb-2">Choose Your Theme</h2>
      <p className="text-gray-300 mb-6">Select one of these 3 random themes for your Round 2 questions</p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {themes.map((theme) => (
          <div
            key={theme.id}
            className="bg-gray-700 rounded-lg overflow-hidden hover:bg-gray-600 transition-colors cursor-pointer"
            onClick={() => onSelectTheme(theme)}
          >
            <div className={`h-2 ${getCategoryColor(theme.category)}`} />
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <span className={`px-3 py-1 rounded-full text-white text-sm ${getCategoryColor(theme.category)}`}>
                  {getCategoryText(theme.category)}
                </span>
                <span className="text-gray-300 text-sm">Difficulty: {theme.difficulty_level}/10</span>
              </div>

              <h3 className="text-xl font-bold text-white mb-3">{theme.name}</h3>
              
              {theme.description && (
                <p className="text-gray-300 mb-4">{theme.description}</p>
              )}

              <div className="mb-4">
                <p className="text-gray-400 text-sm mb-1">Difficulty Level:</p>
                <div className="text-yellow-400 text-lg">
                  {getDifficultyStars(theme.difficulty_level)}
                </div>
              </div>

              <div className="text-center">
                <button className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg">
                  Select This Theme
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 text-center text-gray-400">
        <p>Each theme has 10 questions with progressive difficulty (1-10)</p>
        <p>Points awarded: 1-10 points per question based on difficulty</p>
      </div>
    </div>
  )
}

export default ThemeSelectorComponent
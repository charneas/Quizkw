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

  // brand-600 est volontairement "pas trop clair" dans les deux thèmes (fond
  // plein de bouton) : texte blanc fixe, comme .btn-primary. brand-muted/
  // surface-raised suivent `text` normalement (déjà pairés correctement dans
  // les deux thèmes).
  const getCategoryTextColor = (category: string) => {
    return category === 'serious' || category === 'pop_culture' ? 'text-white' : 'text-text'
  }

  const getCategoryText = (category: string) => {
    switch (category) {
      case 'serious':
        return 'Sérieux'
      case 'pop_culture':
        return 'Culture pop'
      case 'whimsical':
        return 'Fantaisie'
      default:
        return category
    }
  }

  const getDifficultyStars = (difficulty: number) => {
    return '★'.repeat(difficulty) + '☆'.repeat(10 - difficulty)
  }

  return (
    <div className="bg-surface rounded-lg p-6">
      <h2 className="text-2xl font-display font-semibold text-text mb-2">Choisissez votre thème</h2>
      <p className="text-text-muted mb-6">
        Sélectionnez un de ces {themes.length} thème{themes.length > 1 ? 's' : ''} tiré{themes.length > 1 ? 's' : ''} au sort pour vos questions de Manche 2
      </p>

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
                <span className={`px-3 py-1 rounded-full text-sm ${getCategoryColor(theme.category)} ${getCategoryTextColor(theme.category)}`}>
                  {getCategoryText(theme.category)}
                </span>
                <span className="text-text-muted text-sm">Difficulté : {theme.difficulty_level}/10</span>
              </div>

              <h3 className="text-xl font-bold text-text mb-3">{theme.name}</h3>

              {theme.description && (
                <p className="text-text-muted mb-4">{theme.description}</p>
              )}

              <div className="mb-4">
                <p className="text-text-muted text-sm mb-1">Niveau de difficulté :</p>
                <div className="text-yellow-400 text-lg">
                  {getDifficultyStars(theme.difficulty_level)}
                </div>
              </div>

              <div className="text-center">
                <button className="btn-primary">
                  Choisir ce thème
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 text-center text-text-muted">
        <p>Chaque thème propose 10 questions de difficulté progressive (1-10)</p>
        <p>Points attribués : de 1 à 10 points par question selon la difficulté</p>
      </div>
    </div>
  )
}

export default ThemeSelectorComponent
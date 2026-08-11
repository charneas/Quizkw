// Liste curatée (pas d'entrée libre) : évite tout souci de rendu/modération,
// suffisamment large pour qu'une partie à 12 équipes n'ait jamais de doublon.
export const TEAM_EMOJIS = [
  '🦁', '🐯', '🐻', '🐺', '🦊', '🐸', '🐙', '🦈',
  '🐉', '🦄', '🦅', '🐝', '🌵', '🍕', '🍔', '🌮',
  '⚡', '🔥', '🌊', '🚀', '🎯', '🎲', '🎸', '🏆',
  '👑', '💎', '⭐', '🌈', '🍀', '☠️', '🥷', '🤖',
]

interface EmojiPickerProps {
  value: string | null
  onChange: (emoji: string) => void
}

function EmojiPicker({ value, onChange }: EmojiPickerProps) {
  return (
    <div className="grid grid-cols-8 gap-1.5">
      {TEAM_EMOJIS.map((emoji) => (
        <button
          key={emoji}
          type="button"
          onClick={() => onChange(emoji)}
          aria-pressed={value === emoji}
          aria-label={`Choisir l'emoji ${emoji}`}
          className={`text-xl aspect-square rounded-lg border flex items-center justify-center transition-colors ${
            value === emoji
              ? 'border-brand bg-brand-muted/20'
              : 'border-border bg-surface-raised hover:border-brand'
          }`}
        >
          {emoji}
        </button>
      ))}
    </div>
  )
}

export default EmojiPicker

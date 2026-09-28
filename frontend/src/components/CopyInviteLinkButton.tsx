import { useEffect, useRef, useState, type ReactNode } from 'react'

// Gain rapide n°1 du brainstorming trafic (2026-09-28) : inviter par lien
// plutôt que dicter un code. Les routes /lobby/:code et /blindtest/:code
// chargent déjà la partie depuis l'URL — il suffit de copier ce lien.
// Retours utilisateur : pas de bouton à part ni de légende sous le code
// (jugés "moches", la légende décalait le code) — le code de room lui-même
// est cliquable, avec seulement une icône de lien à côté.
function CopyInviteLinkButton({
  path,
  className,
  children,
}: {
  path: string
  className: string
  children: ReactNode
}) {
  const [status, setStatus] = useState<'idle' | 'copied' | 'manual'>('idle')
  const inputRef = useRef<HTMLInputElement>(null)
  const link = `${window.location.origin}${path}`

  useEffect(() => {
    if (status !== 'copied') return
    const timeout = setTimeout(() => setStatus('idle'), 2000)
    return () => clearTimeout(timeout)
  }, [status])

  useEffect(() => {
    if (status === 'manual') inputRef.current?.select()
  }, [status])

  const handleCopy = async () => {
    try {
      // navigator.clipboard n'existe qu'en contexte sécurisé (HTTPS/localhost) :
      // hors de ce cas, on affiche le lien à copier à la main.
      await navigator.clipboard.writeText(link)
      setStatus('copied')
    } catch {
      setStatus('manual')
    }
  }

  const copied = status === 'copied'

  return (
    <>
      <button
        type="button"
        onClick={handleCopy}
        title={copied ? 'Lien copié !' : "Copier le lien d'invitation"}
        aria-label="Copier le lien d'invitation"
        className={`inline-flex items-center gap-2 cursor-pointer transition-colors ${className}`}
      >
        {children}
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2.2}
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`w-4 h-4 shrink-0 ${copied ? 'text-success' : 'opacity-70'}`}
        >
          {copied ? (
            <path d="M20 6 9 17l-5-5" />
          ) : (
            <>
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
            </>
          )}
        </svg>
      </button>
      {/* Annonce la copie aux lecteurs d'écran (le ✓ n'est que visuel). */}
      <span aria-live="polite" className="sr-only">
        {copied ? 'Lien copié !' : ''}
      </span>
      {status === 'manual' && (
        <input
          ref={inputRef}
          type="text"
          readOnly
          value={link}
          aria-label="Lien d'invitation"
          onFocus={(e) => e.target.select()}
          className="input-field text-sm text-center w-full mt-2"
        />
      )}
    </>
  )
}

export default CopyInviteLinkButton

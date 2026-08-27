import { useEffect, useRef, useState, type RefObject } from 'react'
import { createPortal } from 'react-dom'
import { fetchAccountStats, type AccountStats } from '../services/api'

interface ProfilOverlayProps {
  onClose: () => void
  triggerRef: RefObject<HTMLElement>
}

const FOCUSABLE_SELECTOR =
  'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'

function percent(correct: number, total: number): number {
  return total === 0 ? 0 : Math.round((correct / total) * 100)
}

function StatBar({ label, personalCorrect, personalTotal, globalCorrect, globalTotal }: {
  label: string
  personalCorrect: number
  personalTotal: number
  globalCorrect: number
  globalTotal: number
}) {
  const personalPct = percent(personalCorrect, personalTotal)
  const globalPct = percent(globalCorrect, globalTotal)
  const ariaLabel = `${label} : toi ${personalPct} %, moyenne ${globalPct} %`

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm text-text">
        <span>{label}</span>
        <span className="text-text-muted">{`Toi : ${personalPct} % · Moyenne : ${globalPct} %`}</span>
      </div>
      <div
        role="img"
        aria-label={ariaLabel}
        className="h-2 rounded-full bg-surface-raised overflow-hidden flex"
      >
        <div className="h-full bg-brand" style={{ width: `${personalPct}%` }} />
      </div>
      <div
        role="img"
        aria-label={`Moyenne globale ${label} : ${globalPct} %`}
        className="h-2 rounded-full bg-surface-raised overflow-hidden flex"
      >
        <div className="h-full bg-text-muted" style={{ width: `${globalPct}%` }} />
      </div>
    </div>
  )
}

// Story O.2.2 : premier dialog accessible du projet (aucun précédent —
// role="dialog", focus trap, Échap, `inert` sur le contenu applicatif
// sous-jacent, focus rendu au déclencheur à la fermeture). Rendu par portail
// React vers `document.body` : la racine d'App.tsx devient `inert` pendant
// l'ouverture, l'overlay doit donc vivre en dehors de cet arbre pour rester
// interactif.
type LoadStatus = 'loading' | 'error' | 'ready'

function ProfilOverlay({ onClose, triggerRef }: ProfilOverlayProps) {
  const [stats, setStats] = useState<AccountStats | null>(null)
  // Revue de code : `fetchAccountStats` renvoie `null` aussi bien en échec
  // (401 expiré, 429, 5xx, réseau) qu'avant la première réponse — sans état
  // distinct, un échec restait indiscernable d'un chargement en cours et
  // affichait indéfiniment "Chargement..." sans jamais se rétablir.
  const [status, setStatus] = useState<LoadStatus>('loading')
  const dialogRef = useRef<HTMLDivElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    let cancelled = false
    fetchAccountStats()
      .then((result) => {
        if (cancelled) return
        if (result === null) {
          setStatus('error')
          return
        }
        setStats(result)
        setStatus('ready')
      })
      .catch(() => {
        if (!cancelled) setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const appRoot = document.querySelector('#root > div') as HTMLElement | null
    if (appRoot) appRoot.inert = true
    closeButtonRef.current?.focus()
    return () => {
      // `inert` doit être retiré AVANT de rendre le focus au déclencheur : un
      // élément inert (ou descendant d'un ancêtre inert) refuse `.focus()`
      // par spec — faire les deux dans ce même cleanup, dans cet ordre,
      // garantit que le focus atterrit réellement sur le bouton (trouvé en
      // revue de code : la version initiale rendait le focus depuis le
      // gestionnaire `onClose` du parent, exécuté avant que ce cleanup n'ait
      // eu la chance de retirer `inert`).
      if (appRoot) appRoot.inert = false
      triggerRef.current?.focus()
    }
  }, [triggerRef])

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
        return
      }
      if (event.key !== 'Tab' || !dialogRef.current) return
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
      )
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const general = stats?.general
  const hasGeneralData = !!general && general.personal_total > 0

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="profil-overlay-title"
        className="animate-fade-in bg-surface border border-border rounded-lg p-6 max-w-md w-full max-h-[85vh] overflow-y-auto space-y-6"
      >
        <div className="flex items-center justify-between">
          <h2 id="profil-overlay-title" className="text-xl font-semibold text-text">
            Profil
          </h2>
          <button
            ref={closeButtonRef}
            onClick={onClose}
            aria-label="Fermer"
            className="min-h-[44px] min-w-[44px] flex items-center justify-center text-text-muted hover:text-text"
          >
            ✕
          </button>
        </div>

        {status === 'loading' && (
          <p className="text-text-muted text-sm">Chargement de tes statistiques…</p>
        )}
        {status === 'error' && (
          <p className="text-text-muted text-sm">
            Impossible de charger tes statistiques pour le moment. Réessaie plus tard.
          </p>
        )}
        {status === 'ready' && stats && (
          <div className="space-y-6">
            <div>
              <h3 className="text-sm font-medium text-text-muted mb-2">Statistique générale</h3>
              {hasGeneralData ? (
                <StatBar
                  label="Toutes questions confondues"
                  personalCorrect={general!.personal_correct}
                  personalTotal={general!.personal_total}
                  globalCorrect={general!.global_correct}
                  globalTotal={general!.global_total}
                />
              ) : (
                <p className="text-text-muted text-sm">
                  Pas encore de partie jouée en étant connecté.
                </p>
              )}
            </div>

            {stats.themes.length > 0 && (
              <div className="space-y-4">
                <h3 className="text-sm font-medium text-text-muted">Par thème</h3>
                {stats.themes.map((theme) => (
                  <div key={theme.theme_id}>
                    {theme.insufficient_data ? (
                      <p className="text-text-muted text-sm">
                        {theme.theme_name} — Pas encore assez de réponses sur ce thème pour afficher ta stat.
                      </p>
                    ) : (
                      <StatBar
                        label={theme.theme_name}
                        personalCorrect={theme.personal_correct}
                        personalTotal={theme.personal_total}
                        globalCorrect={theme.global_correct}
                        globalTotal={theme.global_total}
                      />
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>,
    document.body
  )
}

export default ProfilOverlay

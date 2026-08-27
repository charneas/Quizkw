import { useEffect, useRef, useState } from 'react'
import { useDiscordAccount } from '../contexts/DiscordAccountContext'
import ProfilOverlay from './ProfilOverlay'

// Story O.1.2 : état "connecté" rendu globalement (comme ThemeToggle), sur
// tous les écrans — remplace le badge local à Home.tsx posé par O.1.1. Ne
// rend jamais le bouton "Connexion" (celui-ci reste dans Home.tsx, AC #6/#8
// d'O.1.1) : ce composant n'affiche quelque chose que lorsqu'un compte
// Discord est effectivement connecté.
//
// Story O.2.1 (revue de code) : le compte n'est plus fetché localement — il
// vient de DiscordAccountContext, partagé avec Home.tsx, pour que les deux
// composants restent synchronisés (un logout ici fait immédiatement
// réapparaître le bouton "Connexion" de Home.tsx, sans double requête réseau).
function AccountButton() {
  const { account, logout } = useDiscordAccount()
  const [menuOpen, setMenuOpen] = useState(false)
  const [isProfilOpen, setIsProfilOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const triggerButtonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!menuOpen) return
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [menuOpen])

  const handleLogout = async () => {
    // Ne ferme le menu que si le serveur a réellement confirmé la
    // déconnexion — un 429 (rate limit) ou une 5xx transitoire ne doit pas
    // faire croire à une déconnexion réussie alors que la session tient
    // toujours côté serveur.
    const success = await logout()
    if (success) setMenuOpen(false)
  }

  if (!account) return null

  return (
    <div ref={containerRef} className="fixed top-4 right-16 z-40">
      <button
        ref={triggerButtonRef}
        onClick={() => setMenuOpen((open) => !open)}
        className="min-h-[44px] px-3 flex items-center gap-2 rounded-lg bg-surface border border-border text-text hover:scale-105 transition-transform"
      >
        <img
          src={account.avatar}
          alt=""
          className="w-7 h-7 rounded-full border border-border"
        />
        <span className="text-sm font-medium">{account.pseudo}</span>
      </button>

      {menuOpen && (
        <div className="absolute right-0 mt-2 min-w-[200px] rounded-lg border border-border bg-surface shadow-lg overflow-hidden">
          <button
            onClick={() => {
              setMenuOpen(false)
              setIsProfilOpen(true)
            }}
            className="w-full text-left px-4 py-2 min-h-[44px] text-sm text-text hover:bg-brand-muted/20 transition-colors"
          >
            Voir mes statistiques
          </button>
          <button
            onClick={handleLogout}
            className="w-full text-left px-4 py-2 min-h-[44px] text-sm text-text hover:bg-brand-muted/20 transition-colors"
          >
            Se déconnecter
          </button>
        </div>
      )}

      {isProfilOpen && (
        <ProfilOverlay
          onClose={() => setIsProfilOpen(false)}
          triggerRef={triggerButtonRef}
        />
      )}
    </div>
  )
}

export default AccountButton

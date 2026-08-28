import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { deleteAccount, fetchDiscordAccount, logoutDiscord, type DiscordAccount } from '../services/api'

// Revue de code (Story O.2.1) : Home.tsx et AccountButton.tsx interrogeaient
// chacun GET /auth/discord/me indépendamment, avec leur propre state — un
// logout déclenché depuis AccountButton (global) ne faisait donc jamais
// réapparaître le bouton "Connexion" de Home.tsx sans rechargement de page.
// Un état partagé (une seule requête, une seule source de vérité) résout à la
// fois la désynchronisation et le doublement de requête.
interface DiscordAccountContextValue {
  account: DiscordAccount | null
  // Revue de code : true seulement le temps de la toute première résolution
  // GET /auth/discord/me — permet à Home.tsx de ne pas afficher le bouton
  // "Connexion" en flash pour un utilisateur déjà connecté, le temps de
  // l'aller-retour réseau initial (account valait null jusque-là, identique
  // à "non connecté").
  isLoading: boolean
  logout: () => Promise<boolean>
  deleteAccount: () => Promise<boolean>
}

const DiscordAccountContext = createContext<DiscordAccountContextValue>({
  account: null,
  isLoading: true,
  logout: async () => false,
  deleteAccount: async () => false,
})

export function DiscordAccountProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<DiscordAccount | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    fetchDiscordAccount()
      .then((result) => {
        if (!cancelled) setAccount(result)
      })
      .catch(() => {
        // Réseau indisponible/erreur inattendue : rester non connecté plutôt
        // que de laisser une rejection non gérée.
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const logout = async () => {
    const success = await logoutDiscord()
    if (success) setAccount(null)
    return success
  }

  // Story O.3.1 : même garde que logout — le compte local ne disparaît que
  // si le serveur a réellement confirmé la suppression.
  const removeAccount = async () => {
    const success = await deleteAccount()
    if (success) setAccount(null)
    return success
  }

  return (
    <DiscordAccountContext.Provider value={{ account, isLoading, logout, deleteAccount: removeAccount }}>
      {children}
    </DiscordAccountContext.Provider>
  )
}

export function useDiscordAccount() {
  return useContext(DiscordAccountContext)
}

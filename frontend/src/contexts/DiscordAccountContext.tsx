import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { fetchDiscordAccount, logoutDiscord, type DiscordAccount } from '../services/api'

// Revue de code (Story O.2.1) : Home.tsx et AccountButton.tsx interrogeaient
// chacun GET /auth/discord/me indépendamment, avec leur propre state — un
// logout déclenché depuis AccountButton (global) ne faisait donc jamais
// réapparaître le bouton "Connexion" de Home.tsx sans rechargement de page.
// Un état partagé (une seule requête, une seule source de vérité) résout à la
// fois la désynchronisation et le doublement de requête.
interface DiscordAccountContextValue {
  account: DiscordAccount | null
  logout: () => Promise<boolean>
}

const DiscordAccountContext = createContext<DiscordAccountContextValue>({
  account: null,
  logout: async () => false,
})

export function DiscordAccountProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<DiscordAccount | null>(null)

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
    return () => {
      cancelled = true
    }
  }, [])

  const logout = async () => {
    const success = await logoutDiscord()
    if (success) setAccount(null)
    return success
  }

  return (
    <DiscordAccountContext.Provider value={{ account, logout }}>
      {children}
    </DiscordAccountContext.Provider>
  )
}

export function useDiscordAccount() {
  return useContext(DiscordAccountContext)
}

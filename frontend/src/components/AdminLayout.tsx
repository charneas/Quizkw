import type { ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { adminLogout } from '../services/api'

interface AdminLayoutProps {
  children: ReactNode
}

const NAV_ITEMS = [
  { to: '/admin', label: 'Contenu (thèmes & questions)' },
  { to: '/admin/propositions', label: 'Propositions en attente' },
  { to: '/admin/propositions/rejected', label: 'Propositions refusées' },
  { to: '/admin/stats', label: 'Statistiques' },
]

/**
 * Coquille commune à toutes les pages admin : barre latérale de navigation
 * entre les différents écrans (contenu, propositions, stats) — avant cette
 * story (2026-08-12), chaque page admin n'avait de lien que vers ses voisines
 * immédiates, sans moyen de revenir à /admin depuis l'écran de gestion des
 * propositions.
 */
function AdminLayout({ children }: AdminLayoutProps) {
  const location = useLocation()
  const navigate = useNavigate()

  async function handleLogout() {
    try {
      await adminLogout()
    } finally {
      navigate('/admin/login')
    }
  }

  return (
    <div className="min-h-screen flex">
      <aside className="w-64 shrink-0 bg-surface border-r border-border p-4 flex flex-col">
        <h2 className="font-display font-bold text-lg text-text mb-4">Admin</h2>
        <nav className="flex flex-col gap-1 flex-1">
          {NAV_ITEMS.map((item) => {
            // Correspondance exacte, sauf "Propositions en attente" qui reste
            // actif sur l'écran d'édition d'une proposition (route enfant).
            const isActive =
              location.pathname === item.to ||
              (item.to === '/admin/propositions' && /^\/admin\/propositions\/\d+\/edit$/.test(location.pathname))
            return (
              <Link
                key={item.to}
                to={item.to}
                className={`px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-brand-600 text-white'
                    : 'text-text-muted hover:bg-surface-raised hover:text-text'
                }`}
              >
                {item.label}
              </Link>
            )
          })}
        </nav>
        <div className="flex flex-col gap-1 pt-4 border-t border-border">
          <Link to="/" className="px-3 py-2 rounded-lg text-sm text-text-muted hover:bg-surface-raised hover:text-text">
            ← Retour au site
          </Link>
          <button
            onClick={handleLogout}
            className="px-3 py-2 rounded-lg text-sm text-left text-danger hover:bg-surface-raised"
          >
            Déconnexion
          </button>
        </div>
      </aside>
      <main className="flex-1 min-w-0">{children}</main>
    </div>
  )
}

export default AdminLayout

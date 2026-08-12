import type { ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { adminLogout } from '../services/api'

interface AdminLayoutProps {
  children: ReactNode
}

const NAV_ITEMS = [
  { to: '/admin', label: 'Contenu' },
  { to: '/admin/themes', label: 'Thèmes' },
  { to: '/admin/questions', label: 'Questions' },
  { to: '/admin/content/generate', label: 'Génération de contenu' },
  { to: '/admin/propositions', label: 'Propositions en attente' },
  { to: '/admin/propositions/rejected', label: 'Propositions refusées' },
  { to: '/admin/stats', label: 'Statistiques' },
]

/**
 * Coquille commune à toutes les pages admin : un panneau de navigation entre
 * les différents écrans (contenu, propositions, stats), dans le même
 * vocabulaire visuel que le reste du site (carte `surface`/`border`,
 * titres en police display) plutôt qu'une barre latérale générique de
 * dashboard plein écran — avant cette story (2026-08-12), chaque page admin
 * n'avait de lien que vers ses voisines immédiates, sans moyen de revenir à
 * /admin depuis l'écran de gestion des propositions.
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
    <div className="min-h-screen p-4 md:p-6">
      <div className="max-w-6xl mx-auto flex flex-col md:flex-row gap-4 md:gap-6 items-start">
        <nav className="card w-full md:w-56 md:shrink-0 md:sticky md:top-6 p-4">
          <h2 className="font-display font-semibold text-lg text-text mb-3">Admin</h2>
          <div className="flex md:flex-col gap-1 overflow-x-auto md:overflow-visible -mx-1 px-1 md:mx-0 md:px-0">
            {NAV_ITEMS.map((item) => {
              // Correspondance exacte, sauf "Propositions en attente" qui reste
              // active sur l'écran d'édition d'une proposition (route enfant).
              const isActive =
                location.pathname === item.to ||
                (item.to === '/admin/propositions' && /^\/admin\/propositions\/\d+\/edit$/.test(location.pathname))
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`shrink-0 px-3 py-2 rounded-lg text-sm whitespace-nowrap transition-colors ${
                    isActive
                      ? 'bg-brand-600 text-white'
                      : 'text-text-muted hover:bg-surface-raised hover:text-text'
                  }`}
                >
                  {item.label}
                </Link>
              )
            })}
          </div>
          <div className="flex md:flex-col gap-1 mt-3 pt-3 border-t border-border">
            <Link
              to="/"
              className="shrink-0 px-3 py-2 rounded-lg text-sm whitespace-nowrap text-text-muted hover:bg-surface-raised hover:text-text transition-colors"
            >
              ← Retour au site
            </Link>
            <button
              onClick={handleLogout}
              className="shrink-0 px-3 py-2 rounded-lg text-sm text-left whitespace-nowrap text-danger hover:bg-surface-raised transition-colors"
            >
              Déconnexion
            </button>
          </div>
        </nav>
        <main className="flex-1 min-w-0 w-full">{children}</main>
      </div>
    </div>
  )
}

export default AdminLayout

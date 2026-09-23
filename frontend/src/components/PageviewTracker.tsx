import { useEffect } from 'react'
import { matchPath, useLocation } from 'react-router-dom'

// Mesure d'audience via GoatCounter auto-hébergé (stats.quizclimb.fr) : pas de
// cookie ni de donnée personnelle stockée, donc pas de bandeau de consentement.
// count.js ne compte que le chargement initial ; en SPA on compte nous-mêmes
// chaque changement de route (no_onload).
const ENDPOINT = 'https://stats.quizclimb.fr/count'
const SCRIPT_SRC = 'https://stats.quizclimb.fr/count.js'

// Les codes de partie sont remplacés par ":code" pour agréger les stats par
// type de page plutôt que par partie. Ordre : du plus spécifique au plus général.
const TRACKED_ROUTES = [
  '/',
  '/proposer',
  '/lobby/:code',
  '/public-queue/:code',
  '/game/:code/host',
  '/game/:code/memory-grid',
  '/game/:code/round2',
  '/game/:code',
  '/team/:code/:teamId',
  '/results/:code',
  '/blindtest/:code',
]

declare global {
  interface Window {
    goatcounter?: { count: (vars: { path: string }) => void }
  }
}

let loaded = false
let pending: string[] = []

function loadScript() {
  if (loaded) return
  loaded = true
  const script = document.createElement('script')
  script.src = SCRIPT_SRC
  script.async = true
  script.dataset.goatcounter = ENDPOINT
  script.dataset.goatcounterSettings = JSON.stringify({ no_onload: true })
  script.onload = () => {
    pending.forEach((path) => window.goatcounter?.count({ path }))
    pending = []
  }
  document.body.appendChild(script)
}

function count(path: string) {
  if (window.goatcounter) window.goatcounter.count({ path })
  else pending.push(path)
}

function PageviewTracker() {
  const { pathname } = useLocation()
  const pattern = TRACKED_ROUTES.find((p) => matchPath(p, pathname))

  useEffect(() => {
    // Admin et routes inconnues (scanners) exclus ; rien en dev.
    if (!import.meta.env.PROD || !pattern) return
    loadScript()
    count(pattern)
  }, [pattern, pathname])

  return null
}

export default PageviewTracker

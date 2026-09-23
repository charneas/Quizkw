import { useEffect } from 'react'
import { matchPath, useLocation } from 'react-router-dom'

const SCRIPT_SRC = 'https://storage.ko-fi.com/cdn/scripts/overlay-widget.js'
const KOFI_PAGE_ID = 'quizclimb00'
const HIDDEN_ATTR = 'data-kofi-hidden'

// Bouton de don affiché uniquement hors partie : un bouton flottant en bas à
// gauche pendant une manche masquerait des toasts (Game.tsx) et distrairait
// les joueurs. Le script Ko-fi n'est chargé qu'une fois (il ne sait pas se
// démonter) ; on se contente ensuite de le masquer via CSS (cf. index.css).
const VISIBLE_ROUTES = ['/', '/results/:code']

declare global {
  interface Window {
    kofiWidgetOverlay?: { draw: (pageId: string, config: Record<string, string>) => void }
  }
}

let loaded = false

function loadWidget() {
  if (loaded) return
  loaded = true
  const script = document.createElement('script')
  script.src = SCRIPT_SRC
  script.async = true
  script.onload = () => {
    window.kofiWidgetOverlay?.draw(KOFI_PAGE_ID, {
      type: 'floating-chat',
      'floating-chat.donateButton.text': 'Soutenir',
      // brand-600 du thème sombre : même violet que les boutons principaux,
      // contraste AA avec le texte blanc (le rose Ko-fi par défaut ne l'est pas).
      'floating-chat.donateButton.background-color': '#7442d6',
      'floating-chat.donateButton.text-color': '#fff',
    })
  }
  document.body.appendChild(script)
}

function KofiWidget() {
  const { pathname } = useLocation()
  const visible = VISIBLE_ROUTES.some((pattern) => matchPath(pattern, pathname))

  useEffect(() => {
    if (visible) loadWidget()
    document.documentElement.toggleAttribute(HIDDEN_ATTR, !visible)
  }, [visible])

  return null
}

export default KofiWidget

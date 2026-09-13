import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

// Bug corrigé (page blanche en prod, 2026-09-13, blind test) : une exception
// non interceptée pendant le rendu videait toute l'app React sans aucun
// message, faute de error boundary. Générique pour couvrir toute page, pas
// seulement celle qui a révélé le bug.
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary a intercepté une erreur de rendu :', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center p-4">
          <div className="card max-w-md w-full text-center space-y-4">
            <p className="text-text">Une erreur inattendue est survenue.</p>
            <a href="/" className="btn-primary inline-block">
              Retour à l'accueil
            </a>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

import { render, screen, fireEvent, within } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import DemoCarousel from './DemoCarousel'

describe('DemoCarousel (spec-home-demo-carousel)', () => {
  function currentDot() {
    return screen
      .getAllByRole('button', { name: /^Aller à la capture/ })
      .find((b) => b.getAttribute('aria-current') === 'true')
  }

  it('présente 4 captures, chacune avec un texte alternatif et une source mobile/desktop', () => {
    const { container } = render(<DemoCarousel />)
    expect(screen.getByRole('region', { name: 'À quoi ressemble une partie ?' })).toBeInTheDocument()

    const images = screen.getAllByRole('img', { hidden: true })
    expect(images).toHaveLength(4)
    for (const img of images) {
      expect(img).toHaveAttribute('alt')
      expect(img.getAttribute('alt')).not.toBe('')
      expect(img).toHaveAttribute('loading', 'lazy')
      expect(img.getAttribute('src')).toMatch(/^\/demo\/[a-z]+-mobile\.webp$/)
    }
    const sources = container.querySelectorAll('source')
    expect(sources).toHaveLength(4)
    for (const source of sources) {
      expect(source.getAttribute('srcset')).toMatch(/^\/demo\/[a-z]+-desktop\.webp$/)
    }
  })

  it('montre la première capture au départ, les autres masquées aux lecteurs d’écran', () => {
    render(<DemoCarousel />)
    expect(currentDot()).toHaveAccessibleName(/capture 1 : Chaque équipe répond/)
    const slides = screen.getAllByRole('listitem', { hidden: true })
    expect(slides[0]).not.toHaveAttribute('aria-hidden', 'true')
    expect(slides[1]).toHaveAttribute('aria-hidden', 'true')
  })

  it('navigue avec suivant/précédent, en boucle', () => {
    render(<DemoCarousel />)
    fireEvent.click(screen.getByRole('button', { name: 'Capture suivante' }))
    expect(currentDot()).toHaveAccessibleName(/capture 2 : La roue/)

    fireEvent.click(screen.getByRole('button', { name: 'Capture précédente' }))
    fireEvent.click(screen.getByRole('button', { name: 'Capture précédente' }))
    expect(currentDot()).toHaveAccessibleName(/capture 4 : Le podium/)
  })

  it('va directement à une capture via ses points', () => {
    render(<DemoCarousel />)
    fireEvent.click(screen.getByRole('button', { name: /capture 3 : Blindtest/ }))
    expect(currentDot()).toHaveAccessibleName(/capture 3 : Blindtest/)
    const slides = screen.getAllByRole('listitem', { hidden: true })
    expect(slides[2]).not.toHaveAttribute('aria-hidden', 'true')
    expect(within(slides[2]).getByText('Blindtest : devine qui a mis ce son')).toBeInTheDocument()
  })
})

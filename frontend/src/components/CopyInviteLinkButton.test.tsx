import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import CopyInviteLinkButton from './CopyInviteLinkButton'

describe('CopyInviteLinkButton', () => {
  const originalClipboard = navigator.clipboard

  afterEach(() => {
    Object.defineProperty(navigator, 'clipboard', { value: originalClipboard, configurable: true })
    vi.restoreAllMocks()
  })

  it('copie le lien complet du lobby et confirme', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })

    render(<CopyInviteLinkButton path="/lobby/ABC123" className="">ABC123</CopyInviteLinkButton>)
    fireEvent.click(screen.getByRole('button', { name: /copier le lien/i }))

    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/lobby/ABC123`)
    expect(await screen.findByText('Lien copié !')).toBeInTheDocument()
  })

  it("affiche le lien à copier à la main si le presse-papier est indisponible", async () => {
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })

    render(<CopyInviteLinkButton path="/blindtest/XYZ789" className="">XYZ789</CopyInviteLinkButton>)
    fireEvent.click(screen.getByRole('button', { name: /copier le lien/i }))

    const input = await screen.findByLabelText("Lien d'invitation")
    expect(input).toHaveValue(`${window.location.origin}/blindtest/XYZ789`)
  })
})

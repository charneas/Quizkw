import { describe, it, expect, vi, afterEach } from 'vitest'
import { createHiddenPlayer, type YouTubePlayer } from './youtubePlayer'

describe('createHiddenPlayer', () => {
  afterEach(() => {
    delete window.YT
  })

  it('résout le lecteur et remonte le code quand onError précède onReady', async () => {
    const target = { destroy: vi.fn() } as unknown as YouTubePlayer
    window.YT = {
      Player: class {
        constructor(_id: string, options: { events?: { onError?: (e: { target: YouTubePlayer; data: number }) => void } }) {
          options.events?.onError?.({ target, data: 150 })
        }
      } as unknown as NonNullable<Window['YT']>['Player'],
    }
    const onError = vi.fn()

    await expect(createHiddenPlayer('container', 'vid', 0, 100, onError)).resolves.toBe(target)

    expect(onError).toHaveBeenCalledWith(150)
  })
})

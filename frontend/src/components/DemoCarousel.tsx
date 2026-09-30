import { useEffect, useRef, useState } from 'react'

// Dimensions réelles des captures (script : mobile 390x844 @2x, desktop
// 1280x800 @1x) : réservent la place avant le chargement (pas de saut de mise
// en page quand une diapo lazy-loadée s'affiche).
const MOBILE_SIZE = { width: 780, height: 1688 }
const DESKTOP_SIZE = { width: 1280, height: 800 }
const FOCUS_RING = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand'

// Captures d'une partie fictive (spec-home-demo-carousel), générées par
// `frontend/scripts/capture-demo.mjs` dans `public/demo/`. Chaque moment
// existe en deux formats : mobile (joueurs sur leur téléphone) et desktop,
// servis selon l'écran du visiteur via <picture>.
const DEMO_SLIDES = [
  {
    id: 'question',
    title: 'Chaque équipe répond sur son téléphone',
    alt: "Écran d'une équipe en Manche 1 : une question de quiz et ses propositions de réponse",
  },
  {
    id: 'wheel',
    title: 'La roue de la fortune rebat les cartes',
    alt: "La roue de la fortune tombe sur un bonus : l'équipe gagne 3 points",
  },
  {
    id: 'blindtest',
    title: 'Blindtest : devine qui a mis ce son',
    alt: "Round de blindtest : les joueurs choisissent à qui appartient la chanson en cours",
  },
  {
    id: 'podium',
    title: 'Le podium final',
    alt: 'Écran de résultats avec le podium des meilleurs joueurs',
  },
] as const

function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

function DemoCarousel() {
  const [index, setIndex] = useState(0)
  const trackRef = useRef<HTMLUListElement>(null)
  // Pendant un défilement déclenché par un bouton, les événements `scroll`
  // intermédiaires ne doivent pas écraser la diapo visée (sinon le point du
  // milieu clignote en allant de 1 à 3).
  const programmaticScroll = useRef<number | null>(null)
  const count = DEMO_SLIDES.length

  const goTo = (target: number) => {
    const next = (target + count) % count
    setIndex(next)
    if (programmaticScroll.current !== null) window.clearTimeout(programmaticScroll.current)
    programmaticScroll.current = window.setTimeout(() => {
      programmaticScroll.current = null
    }, 700)
    const track = trackRef.current
    track?.scrollTo?.({
      left: next * track.clientWidth,
      behavior: prefersReducedMotion() ? 'auto' : 'smooth',
    })
  }

  // Swipe natif (scroll-snap) : la diapo courante suit la position du
  // défilement pour garder les points et les boutons synchronisés.
  useEffect(() => {
    const track = trackRef.current
    if (!track) return
    const onScroll = () => {
      if (!track.clientWidth || programmaticScroll.current !== null) return
      setIndex(Math.round(track.scrollLeft / track.clientWidth))
    }
    track.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      track.removeEventListener('scroll', onScroll)
      if (programmaticScroll.current !== null) window.clearTimeout(programmaticScroll.current)
    }
  }, [])

  return (
    <section
      aria-roledescription="carrousel"
      aria-labelledby="demo-carousel-title"
      className="mt-10"
    >
      <h2
        id="demo-carousel-title"
        className="font-display font-semibold text-2xl tracking-wide text-text text-center mb-4"
      >
        À quoi ressemble une partie ?
      </h2>

      <div className="rounded-2xl border border-border bg-surface p-4 sm:p-6">
        <ul
          ref={trackRef}
          className="flex overflow-x-auto snap-x snap-mandatory [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          {DEMO_SLIDES.map((slide, i) => (
            <li
              key={slide.id}
              aria-roledescription="diapositive"
              aria-label={`${i + 1} sur ${count} : ${slide.title}`}
              aria-hidden={i !== index}
              className="w-full shrink-0 snap-center"
            >
              <figure className="flex flex-col items-center">
                <picture>
                  <source
                    media="(min-width: 640px)"
                    srcSet={`/demo/${slide.id}-desktop.webp`}
                    width={DESKTOP_SIZE.width}
                    height={DESKTOP_SIZE.height}
                  />
                  <img
                    src={`/demo/${slide.id}-mobile.webp`}
                    width={MOBILE_SIZE.width}
                    height={MOBILE_SIZE.height}
                    alt={slide.alt}
                    loading="lazy"
                    decoding="async"
                    className="block h-auto max-h-[70vh] sm:max-h-none w-auto sm:w-full rounded-xl border border-border"
                  />
                </picture>
                <figcaption className="mt-3 text-sm text-text text-center">
                  <span className="font-display text-brand mr-1.5">{i + 1}.</span>
                  {slide.title}
                </figcaption>
              </figure>
            </li>
          ))}
        </ul>

        <div className="mt-4 flex items-center justify-center gap-4">
          <button
            type="button"
            onClick={() => goTo(index - 1)}
            aria-label="Capture précédente"
            className={`min-h-[44px] min-w-[44px] rounded-full border border-border text-text-muted hover:border-brand hover:text-text transition-colors ${FOCUS_RING}`}
          >
            ‹
          </button>
          <div className="flex items-center">
            {DEMO_SLIDES.map((slide, i) => (
              <button
                key={slide.id}
                type="button"
                onClick={() => goTo(i)}
                aria-label={`Aller à la capture ${i + 1} : ${slide.title}`}
                aria-current={i === index ? 'true' : undefined}
                className={`min-h-[44px] min-w-[44px] flex items-center justify-center rounded-full ${FOCUS_RING}`}
              >
                <span
                  aria-hidden="true"
                  className={`block h-2.5 rounded-full transition-all ${
                    i === index ? 'w-6 bg-brand' : 'w-2.5 bg-border'
                  }`}
                />
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => goTo(index + 1)}
            aria-label="Capture suivante"
            className={`min-h-[44px] min-w-[44px] rounded-full border border-border text-text-muted hover:border-brand hover:text-text transition-colors ${FOCUS_RING}`}
          >
            ›
          </button>
        </div>
      </div>
    </section>
  )
}

export default DemoCarousel

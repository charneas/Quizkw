/** @type {import('tailwindcss').Config} */

// Permet aux tokens `brand.*`/`surface`/etc. de rester pilotables par variables
// CSS (donc thématisables clair/sombre via [data-theme] sur <html>, cf. index.css)
// tout en conservant les modificateurs d'opacité Tailwind (bg-danger/10,
// border-brand/50...) déjà utilisés dans des dizaines de fichiers — la
// fonction renvoie `rgb(var(--x) / <opacityValue>)` uniquement quand un
// modifieur est présent, sinon `rgb(var(--x))`.
function withOpacity(variableName) {
  return ({ opacityValue }) => {
    if (opacityValue !== undefined) {
      return `rgb(var(${variableName}) / ${opacityValue})`
    }
    return `rgb(var(${variableName}))`
  }
}

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // --- Palette existante (bleu/navy/ambre) — CONSERVÉE telle quelle. ---
        // Encore activement utilisée par des dizaines de fichiers .tsx non restylés
        // (Home, Lobby, Game, HostGame, MemoryGrid, TeamScreen, Scoreboard, WheelModal,
        // PingPong*...). Sera retirée une fois toutes les stories I-002 à I-006 migrées
        // vers les tokens `brand.*` ci-dessous — ne pas supprimer avant cette migration
        // complète, sous peine de casser l'app en production (classes Tailwind non générées).
        primary: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
        },
        game: {
          bg: '#0f172a',
          card: '#1e293b',
          accent: '#f59e0b',
          success: '#10b981',
          danger: '#ef4444',
        },

        // --- Neon Pit Lane — thème "Knights of Wheels" (DESIGN.md, session UX 2026-07-26). ---
        // Tokens nommés sémantiquement, sous une clé distincte `brand.*` pour éviter toute
        // collision avec l'échelle `primary` ci-dessus le temps de la migration écran par écran
        // (I-002 à I-006). Une story de clôture renommera `brand` → `primary` une fois plus
        // aucun fichier ne référencera l'ancienne échelle 50-900.
        // Valeurs réelles définies en variables CSS RGB dans index.css (thème sombre
        // par défaut, thème clair sous [data-theme="light"]) — voir `withOpacity` ci-dessus.
        bg: withOpacity('--color-bg'),
        surface: {
          DEFAULT: withOpacity('--color-surface'),
          raised: withOpacity('--color-surface-raised'),
        },
        border: withOpacity('--color-border'),
        brand: {
          DEFAULT: withOpacity('--color-brand'),
          // brand-600 : nuance dédiée aux FONDS PLEINS DE BOUTON uniquement (pas une
          // échelle générique). Corrige un contraste WCAG insuffisant : texte clair sur
          // `brand` seul ne tenait que 3.57:1 (sous l'AA texte normal 4.5:1) ; sur
          // brand-600, le ratio monte à 5.06:1 en sombre (7.1:1 en clair). `brand`
          // (DEFAULT) reste utilisé tel quel comme couleur de texte/accent.
          600: withOpacity('--color-brand-600'),
          hover: withOpacity('--color-brand-hover'),
          muted: withOpacity('--color-brand-muted'),
        },
        accent: withOpacity('--color-accent'),
        success: withOpacity('--color-success'),
        danger: withOpacity('--color-danger'),
        text: {
          DEFAULT: withOpacity('--color-text'),
          muted: withOpacity('--color-text-muted'),
        },
        // Couleurs fixes des 4 finalistes Manche 3 : identifiants fonctionnels, PAS des
        // tokens de marque. Ne pas renommer/retoucher. Restent en classes Tailwind
        // standard (bg-blue-600/40 etc., cf. MemoryGrid.tsx FINALIST_COLORS) de façon
        // PERMANENTE — story I-005 (2026-07-27) a migré le reste du fichier vers les
        // tokens brand.* mais a confirmé que ces 4 couleurs ne doivent jamais le devenir.
      },
      fontFamily: {
        // Oswald, poids 600 uniquement (pas 700 — bold plein en majuscules jugé peu
        // lisible en revue UX, corrigé le 2026-07-26). Pile de secours SANS "Impact"
        // (cause un rendu déformé/texturé constaté sur les maquettes de la session UX).
        display: ['Oswald', '"Arial Narrow"', 'Arial', 'sans-serif'],
      },
      borderRadius: {
        sm: '8px',
        DEFAULT: '12px',
        md: '12px',
        lg: '16px',
        xl: '20px',
      },
      animation: {
        'spin-slow': 'spin 3s linear infinite',
        'bounce-once': 'bounce 0.5s ease-in-out 1',
        'pulse-fast': 'pulse 0.5s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      }
    },
  },
  plugins: [],
}

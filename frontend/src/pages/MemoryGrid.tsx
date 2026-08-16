import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  getGame,
  startMemoryGridRound,
  getMemoryGridState,
  getMemoryGridStandings,
  getCurrentPlayerTurn,
  revealCell,
  answerCell,
  advanceToPhase3,
  skipTurn,
  getMemoryGridFinalists,
  getRound2QualifiedPlayers,
  getPlayerSetupStatus,
  getAvailableColors,
  getAvailableThemesForSelection,
  selectPlayerColor,
  selectPlayerThemes,
  createMemoryGridWithThemes,
  getMemoryGridStateByCode,
  getHostToken,
} from '../services/api'
import type { GameSession, MemoryGridState, GridCell } from '../types'
import type { AvailableTheme, PlayerSetupStatus } from '../services/api'
import SpectatorView from '../components/SpectatorView'

// Playtest 2026-08-15 : le timer porte sur la RÉPONSE à la question révélée
// (60s), pas sur le choix d'une case — il démarre quand la question apparaît
// côté client, pas dès que c'est le tour du joueur.
const TURN_DURATION_SECONDS = 60
// C-003 AC4 : synchronisation par polling (décision d'architecture du 2026-07-24,
// cf. epics-and-stories.md § C-003 AC4 — pas de WebSocket).
const POLL_INTERVAL_MS = 2000

// AD-0 : la Manche 3 est INDIVIDUELLE — 4 finalistes, pas des équipes.
// Chaque finaliste porte une couleur, dans l'ordre du classement de Manche 2.
const FINALIST_COLORS = [
  { bg: 'bg-blue-600/40', border: 'border-blue-400', text: 'text-blue-300' },
  { bg: 'bg-red-600/40', border: 'border-red-400', text: 'text-red-300' },
  { bg: 'bg-green-600/40', border: 'border-green-400', text: 'text-green-300' },
  { bg: 'bg-yellow-600/40', border: 'border-yellow-400', text: 'text-yellow-300' },
]

// Bug playtest 2026-08-16 : la couleur d'un finaliste doit être CELLE qu'il
// a choisie pendant le setup (PlayerRound3Stats.color, cf. PlayerColorEnum
// côté backend — 12 valeurs), pas une couleur recalculée par position dans
// un tableau qui changeait selon l'ordre reçu après un refresh.
const PLAYER_COLOR_STYLES: Record<string, { bg: string; border: string; text: string }> = {
  red: { bg: 'bg-red-600/40', border: 'border-red-400', text: 'text-red-300' },
  blue: { bg: 'bg-blue-600/40', border: 'border-blue-400', text: 'text-blue-300' },
  green: { bg: 'bg-green-600/40', border: 'border-green-400', text: 'text-green-300' },
  yellow: { bg: 'bg-yellow-600/40', border: 'border-yellow-400', text: 'text-yellow-300' },
  purple: { bg: 'bg-purple-600/40', border: 'border-purple-400', text: 'text-purple-300' },
  orange: { bg: 'bg-orange-600/40', border: 'border-orange-400', text: 'text-orange-300' },
  pink: { bg: 'bg-pink-600/40', border: 'border-pink-400', text: 'text-pink-300' },
  cyan: { bg: 'bg-cyan-600/40', border: 'border-cyan-400', text: 'text-cyan-300' },
  teal: { bg: 'bg-teal-600/40', border: 'border-teal-400', text: 'text-teal-300' },
  brown: { bg: 'bg-amber-800/40', border: 'border-amber-700', text: 'text-amber-600' },
  gray: { bg: 'bg-gray-600/40', border: 'border-gray-400', text: 'text-gray-300' },
  black: { bg: 'bg-neutral-900/60', border: 'border-neutral-500', text: 'text-neutral-300' },
}

// 35 cellules fixes (grille 7x5, cf. create_memory_grid(rows=7, cols=5)).
const TOTAL_GRID_CELLS = 35

interface Standing {
  player_id: number
  player_name: string
  total_score: number
  // C-004 : déjà renvoyées par GET /memory-grid/{id}/winner, ignorées jusqu'ici.
  stolen_cells: number
  own_theme_cells: number
  unassigned_cells: number
}

function MemoryGrid() {
  const { code } = useParams<{ code: string }>()
  const navigate = useNavigate()
  // Chaque finaliste doit configurer son setup et jouer son tour depuis son
  // PROPRE appareil — l'hôte ne fait qu'orchestrer (créer/démarrer la grille,
  // appels host-gated côté serveur), il ne clique jamais à la place d'un joueur.
  const isHost = code ? getHostToken(code) !== null : false

  const [game, setGame] = useState<GameSession | null>(null)
  const [gridState, setGridState] = useState<MemoryGridState | null>(null)
  const [gridId, setGridId] = useState<number | null>(null)
  const [roundId, setRoundId] = useState<number | null>(null)
  const [standings, setStandings] = useState<Standing[]>([])
  // AD-8 : le serveur possède l'ordre des tours — pas de compteur local.
  const [currentPlayerId, setCurrentPlayerId] = useState<number | null>(null)
  // C-003 : le tour observé, transmis à skip-turn pour un compare-and-set
  // (chaque client connecté fait tourner son propre timer et pourrait sinon
  // appeler skip-turn plusieurs fois pour le même timeout).
  const [currentTurn, setCurrentTurn] = useState<number | null>(null)
  const [selectedCell, setSelectedCell] = useState<GridCell | null>(null)
  const [answerText, setAnswerText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [answerFeedback, setAnswerFeedback] = useState<{
    points: number
    cellType: string
    isCorrect: boolean
    correctAnswer: string
  } | null>(null)
  const [loading, setLoading] = useState(true)
  const [initStep, setInitStep] = useState('')
  const [error, setError] = useState('')
  // BUG-401 (#32) : seul l'écran hôte peut créer/démarrer/avancer la Manche 3
  // (host-gated côté serveur : create-with-themes, start, advance-to-phase3).
  // Tout autre appareil (joueur éliminé, ou finaliste sur son propre device)
  // bascule en spectateur lecture seule au lieu d'échouer sur ces appels.
  const [isSpectator, setIsSpectator] = useState(false)
  // Identité du finaliste utilisant CET appareil (null sur l'appareil hôte,
  // ou tant qu'elle n'est pas résolue). Seul ce joueur peut configurer son
  // propre setup et jouer quand c'est son tour, depuis son propre téléphone.
  const [myPlayerId, setMyPlayerId] = useState<number | null>(null)
  // Finaliste dont le setup personnel est terminé, en attente que l'hôte
  // crée/démarre effectivement la grille (appels host-gated côté serveur).
  const [waitingForGrid, setWaitingForGrid] = useState(false)

  // H.011 (BUG-302) : setup thème/couleur par finaliste avant que la grille
  // n'existe. Tant que setupPhase est vrai, aucune grille n'est créée.
  const [setupPhase, setSetupPhase] = useState(false)
  const [gameSessionId, setGameSessionId] = useState<number | null>(null)
  const [finalistIds, setFinalistIds] = useState<number[]>([])
  const [finalistNames, setFinalistNames] = useState<Record<number, string>>({})
  const [setupStatuses, setSetupStatuses] = useState<Record<number, PlayerSetupStatus>>({})
  // Écran partagé (pas d'identité de joueur par appareil, comme le reste de
  // la Manche 3) : n'importe quel finaliste peut ouvrir SON propre picker sur
  // cet écran commun, à tour de rôle.
  const [configuringPlayerId, setConfiguringPlayerId] = useState<number | null>(null)
  const [pickerColors, setPickerColors] = useState<string[]>([])
  const [pickerThemes, setPickerThemes] = useState<AvailableTheme[]>([])
  const [pickerSelectedColor, setPickerSelectedColor] = useState<string | null>(null)
  const [pickerSelectedThemeIds, setPickerSelectedThemeIds] = useState<number[]>([])
  const [pickerError, setPickerError] = useState('')
  const [pickerSubmitting, setPickerSubmitting] = useState(false)
  const [timeRemaining, setTimeRemaining] = useState<number | null>(null)
  // Playtest 2026-08-15 : phase de mémorisation avant le début du jeu — la
  // grille complète (propriétaires des cases) reste visible un temps donné,
  // décompté côté serveur (memorize_seconds_remaining), avant que les cases
  // ne se cachent. Sans quoi "grille à MÉMORISER" n'avait aucun sens.
  const [memorizeRemaining, setMemorizeRemaining] = useState<number | null>(null)
  // C-004 : effet visuel transitoire sur la cellule qui vient d'être jouée,
  // en plus de la modale de feedback existante. S'efface tout seul — ne doit
  // pas être dérivé de gridState pour ne pas se redéclencher à chaque poll.
  const [lastCaptured, setLastCaptured] = useState<{ cellId: number; isCorrect: boolean } | null>(null)
  // Évite qu'un timeout d'effacement périmé (capture précédente) n'efface la
  // capture suivante si deux réponses arrivent à moins de 1200ms d'intervalle.
  const lastCapturedCellRef = useRef<number | null>(null)
  // Le polling (2s) et les rafraîchissements déclenchés par une action peuvent
  // se chevaucher ; une réponse réseau en retard ne doit jamais écraser un
  // état plus récent déjà affiché — on ne garde que la réponse la plus récente émise.
  const refreshSeq = useRef(0)
  // React.StrictMode double-invoque les effets au montage en dev : sans ce
  // garde, initGrid() partirait deux fois en parallèle et créerait deux
  // grilles concurrentes (la vérification d'idempotence côté backend est
  // sujette à une course entre deux requêtes quasi simultanées).
  const initStarted = useRef(false)

  const matchedCells = gridState?.cells.filter((c) => c.status === 'matched').length || 0
  // Bug playtest 2026-08-16 : la partie s'arrête après 5 questions par
  // finaliste (n'importe quelle case), pas après avoir vidé toute la grille
  // 7×5 (35 cases) — la barre de progression suit désormais ce vrai total
  // (5 × nombre de finalistes), pas le nombre brut de cellules de la grille.
  const totalQuestions = (finalistIds.length || FINALIST_COLORS.length) * 5
  const progress = totalQuestions > 0 ? Math.round((matchedCells / totalQuestions) * 100) : 0
  const isCompleted = gridState?.memory_grid.is_completed || (totalQuestions > 0 && matchedCells >= totalQuestions)

  useEffect(() => {
    if (code && !initStarted.current) {
      initStarted.current = true
      initGrid()
    }
  }, [code])

  // C-003 AC4 : polling 2s pour que tous les finalistes voient converger
  // l'état de la grille sans action manuelle. S'arrête une fois la partie
  // terminée (plus rien à synchroniser, écran de résultats affiché).
  useEffect(() => {
    if (!gridId || isCompleted) return
    const interval = setInterval(refreshState, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [gridId, isCompleted])

  // Resynchronise le compte à rebours de mémorisation sur la valeur serveur
  // (source de vérité) à chaque poll, puis le décompte localement à la
  // seconde entre deux polls pour un affichage fluide.
  useEffect(() => {
    if (gridState) setMemorizeRemaining(gridState.memory_grid.memorize_seconds_remaining)
  }, [gridState])

  useEffect(() => {
    if (memorizeRemaining === null || memorizeRemaining <= 0) return
    const timer = setTimeout(() => setMemorizeRemaining((prev) => (prev !== null ? Math.max(0, prev - 1) : null)), 1000)
    return () => clearTimeout(timer)
  }, [memorizeRemaining])

  const isMemorizing = memorizeRemaining !== null && memorizeRemaining > 0

  // Playtest 2026-08-15 : le timer démarre quand la question apparaît
  // effectivement sur le client (selectedCell renseigné après révélation),
  // pas dès que c'est le tour du joueur — le temps pour choisir une case
  // reste libre, seul le temps de réponse est chronométré.
  useEffect(() => {
    if (!selectedCell || isCompleted || isMemorizing) {
      setTimeRemaining(null)
      return
    }
    setTimeRemaining(TURN_DURATION_SECONDS)
  }, [selectedCell?.id, isMemorizing])

  // C-003 AC4 : décompte du timer, un skip-turn déclenché une seule fois à 0.
  useEffect(() => {
    if (timeRemaining === null) return
    if (timeRemaining <= 0) {
      // BUG-401 (#32) : un spectateur ne pilote jamais le tour — laisse les
      // appareils actifs (host/finalistes) faire converger l'état, qu'il
      // suivra via le polling en lecture seule.
      // Le temps de réponse est écoulé : referme la modale de question sur
      // l'appareil du joueur concerné (la cellule redevient cachée côté
      // serveur, inutile de continuer à afficher sa question localement).
      setSelectedCell(null)
      setAnswerText('')
      if (!isSpectator && gridId && currentTurn !== null) {
        skipTurn(gridId, currentTurn)
          .then(refreshState)
          .catch(() => {
            // Échec réseau : le prochain poll resynchronisera l'état, mais on
            // retente une fois tout de suite pour ne pas rester bloqué à 0
            // jusqu'au prochain cycle de polling (jusqu'à 2s).
            setTimeout(() => {
              skipTurn(gridId, currentTurn).then(refreshState).catch(() => {
                setError("Impossible de passer le tour, nouvelle tentative au prochain rafraîchissement.")
              })
            }, 500)
          })
      }
      return
    }

    const timer = setTimeout(() => setTimeRemaining((prev) => (prev !== null ? prev - 1 : null)), 1000)
    return () => clearTimeout(timer)
  }, [timeRemaining, gridId])

  // Bug playtest 2026-08-16 : couleur réellement choisie par le finaliste
  // (attribut stable du joueur pour cette manche), plus une couleur
  // recalculée par rang — repli sur l'ancien comportement par index
  // uniquement si aucune couleur n'a été enregistrée (ne devrait plus
  // arriver une fois le setup passé).
  const colorFor = (playerId: number | null) => {
    if (playerId === null) return null
    const chosen = gridState?.player_colors?.[playerId]
    if (chosen && PLAYER_COLOR_STYLES[chosen]) return PLAYER_COLOR_STYLES[chosen]
    const index = standings.findIndex((s) => s.player_id === playerId)
    if (index === -1) return null
    return FINALIST_COLORS[index % FINALIST_COLORS.length]
  }

  const nameFor = (playerId: number | null) =>
    standings.find((s) => s.player_id === playerId)?.player_name ?? `Joueur ${playerId}`

  // Repère daltonisme (deutéranopie) : initiale du finaliste, en plus de la couleur.
  // [...name] (pas charAt) pour ne pas découper un caractère hors du plan de base (emoji).
  const initialFor = (name: string) => ([...name.trim()][0] ?? '?').toUpperCase()

  const initGrid = async () => {
    try {
      setInitStep('Chargement du jeu...')
      const gameData = await getGame(code!)
      setGame(gameData)

      // BUG-401 (#32) : déterminer les finalistes AVANT tout appel host-only
      // (advanceToPhase3/create-with-themes/start) — get_finalists_from_round2
      // ne dépend que des stats de Manche 2, jamais de current_round.
      setInitStep('Détermination des 4 finalistes...')
      const { finalists, game_session_id } = await getMemoryGridFinalists(code!)
      setGameSessionId(game_session_id)
      setFinalistIds(finalists)

      const qualified = await getRound2QualifiedPlayers(code!)
      const names: Record<number, string> = {}
      for (const p of qualified) {
        if (finalists.includes(p.id)) names[p.id] = p.name
      }
      setFinalistNames(names)

      // BUG-401 (#32) : identifier CE joueur via la même identité persistée
      // par joinTeam/Round2.tsx (BUG-501/#33, clé `quizkw_player_${code}`).
      // S'il est connu et n'est PAS dans les finalistes → spectateur lecture
      // seule, jamais d'appel aux endpoints host-only. Absence d'identité
      // sauvegardée (cas de l'écran hôte, qui n'a jamais sélectionné de
      // joueur) → comportement inchangé, flux finaliste/hôte normal.
      let savedPlayerId: number | null = null
      try {
        const savedPlayerRaw = localStorage.getItem(`quizkw_player_${code}`)
        if (savedPlayerRaw) savedPlayerId = JSON.parse(savedPlayerRaw)?.id ?? null
      } catch {
        // Identité illisible : on retombe sur le flux normal, pas spectateur.
      }
      // L'hôte prime toujours sur une identité de joueur non-finaliste
      // périmée dans son localStorage (ex. il a lui-même rejoint une équipe
      // en Manche 1 sur ce même appareil avant d'être éliminé) : il reste
      // orchestrateur, jamais spectateur — sinon la grille ne serait plus
      // jamais créée/démarrée par personne.
      if (!isHost && savedPlayerId !== null && !finalists.includes(savedPlayerId)) {
        setIsSpectator(true)
        await initSpectator()
        setLoading(false)
        return
      }

      // Comme en Manches 1 et 2, l'hôte peut aussi être l'un des joueurs :
      // isHost et « être ce finaliste » ne sont pas mutuellement exclusifs.
      // Ce device configure/joue pour CE joueur (s'il en a un), et orchestre
      // en plus la création/démarrage de la grille s'il porte le token hôte.
      if (savedPlayerId !== null && finalists.includes(savedPlayerId)) {
        setMyPlayerId(savedPlayerId)
      }

      if (isHost && gameData.current_round !== 'manche_3') {
        setInitStep('Manche 2 terminée — les 4 finalistes accèdent à la Manche 3...')
        await advanceToPhase3(code!)
      }

      setInitStep('Vérification du setup des finalistes (couleur + thèmes)...')
      const statuses = await fetchSetupStatuses(finalists, game_session_id)

      if (Object.values(statuses).some((s) => !s.setup_complete)) {
        setSetupStatuses(statuses)
        setSetupPhase(true)
        setLoading(false)
        return
      }

      if (isHost) {
        await createGridAndStart()
      } else {
        // create-with-themes/start sont host-gated côté serveur : un appareil
        // finaliste attend simplement que l'hôte les déclenche, puis rejoint
        // la grille déjà prête via l'endpoint public par code.
        setWaitingForGrid(true)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur initialisation grille')
    } finally {
      setLoading(false)
    }
  }

  // BUG-401 (#32) : tentative de récupération de la grille active en lecture
  // seule (endpoint public par code, aucun appel host-only). Si aucune grille
  // n'existe encore (Manche 3 pas démarrée par l'hôte), on échoue simplement
  // et le polling ci-dessous réessaiera — pas d'erreur affichée à l'utilisateur.
  const initSpectator = async () => {
    setInitStep("En attente du démarrage de la Manche 3 par l'hôte...")
    try {
      const state = await getMemoryGridStateByCode(code!)
      setGridId(state.memory_grid.id)
      setGridState(state)
      if (state.memory_grid.round_id) setRoundId(state.memory_grid.round_id)
      await refreshPlayers(state.memory_grid.id)
    } catch {
      // Pas encore de grille active — le polling de spectateur réessaiera.
    }
    setInitStep('')
  }

  // Un finaliste dont le setup personnel est terminé attend que l'hôte crée
  // et démarre la grille (host-gated), puis la rejoint dès qu'elle existe.
  useEffect(() => {
    if (!waitingForGrid || gridId) return
    const poll = async () => {
      try {
        const state = await getMemoryGridStateByCode(code!)
        setGridId(state.memory_grid.id)
        setGridState(state)
        if (state.memory_grid.round_id) setRoundId(state.memory_grid.round_id)
        await refreshPlayers(state.memory_grid.id)
        setWaitingForGrid(false)
      } catch {
        // L'hôte n'a pas encore créé/démarré la grille — on réessaiera.
      }
    }
    poll()
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [waitingForGrid, gridId, code])

  // Tant qu'un spectateur n'a pas encore de grille à suivre, on réessaie
  // périodiquement au lieu d'un polling en erreur silencieuse unique.
  useEffect(() => {
    if (!isSpectator || gridId) return
    const interval = setInterval(async () => {
      try {
        const state = await getMemoryGridStateByCode(code!)
        setGridId(state.memory_grid.id)
        setGridState(state)
        await refreshPlayers(state.memory_grid.id)
      } catch {
        // Toujours pas de grille active — on réessaiera au prochain tick.
      }
    }, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [isSpectator, gridId, code])

  const fetchSetupStatuses = async (ids: number[], sessionId: number) => {
    const results = await Promise.all(ids.map((id) => getPlayerSetupStatus(id, sessionId)))
    const map: Record<number, PlayerSetupStatus> = {}
    results.forEach((s) => { map[s.player_id] = s })
    return map
  }

  // Appelée une fois que tous les finalistes ont setup_complete === true,
  // que ce soit d'emblée (reconnexion) ou juste après le dernier picker.
  const createGridAndStart = async () => {
    setInitStep('Préparation de la grille mémoire 7×5 selon les thèmes choisis...')
    const grid = await createMemoryGridWithThemes(code!)
    setGridId(grid.id)

    setInitStep('Chargement des cellules...')
    setGridState(await getMemoryGridState(grid.id))

    setInitStep('Démarrage du tournoi final...')
    const round = await startMemoryGridRound(code!)
    setRoundId(round.round_id)

    setInitStep('Détermination du premier tour...')
    await refreshPlayers(grid.id)

    setInitStep('')
    setSetupPhase(false)
  }

  // Tant qu'on est en phase de setup, on poll l'avancement de TOUS les
  // finalistes (au même rythme que le reste de la Manche 3) pour savoir
  // quand débloquer la création de la grille — sans jamais exposer leurs
  // choix de couleur/thème avant que ce ne soit fait (BUG-303/304).
  useEffect(() => {
    if (!setupPhase || !gameSessionId || finalistIds.length === 0) return
    const interval = setInterval(async () => {
      try {
        const statuses = await fetchSetupStatuses(finalistIds, gameSessionId)
        setSetupStatuses(statuses)
        if (Object.values(statuses).every((s) => s.setup_complete)) {
          if (isHost) {
            await createGridAndStart()
          } else {
            setSetupPhase(false)
            setWaitingForGrid(true)
          }
        }
      } catch (err) {
        console.error('Erreur refresh (setup):', err)
      }
    }, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setupPhase, gameSessionId, finalistIds])

  const openPicker = async (playerId: number) => {
    // Chaque finaliste ne configure que SON propre setup, jamais celui d'un
    // autre joueur — l'appareil hôte, lui, n'en configure aucun.
    if (!gameSessionId || playerId !== myPlayerId) return
    setPickerError('')
    setPickerSelectedColor(null)
    setPickerSelectedThemeIds([])
    setConfiguringPlayerId(playerId)
    try {
      const [colorsRes, themesRes] = await Promise.all([
        getAvailableColors(gameSessionId),
        getAvailableThemesForSelection(gameSessionId),
      ])
      setPickerColors(colorsRes.available_colors)
      setPickerThemes(themesRes.available_themes)
    } catch (err) {
      setPickerError(err instanceof Error ? err.message : 'Erreur chargement des options')
    }
  }

  const closePicker = () => {
    setConfiguringPlayerId(null)
    setPickerError('')
  }

  const toggleThemeSelection = (themeId: number) => {
    setPickerSelectedThemeIds((prev) => {
      if (prev.includes(themeId)) return prev.filter((id) => id !== themeId)
      if (prev.length >= 3) return prev
      return [...prev, themeId]
    })
  }

  const submitPicker = async () => {
    if (!gameSessionId || configuringPlayerId === null || pickerSubmitting) return
    if (!pickerSelectedColor || pickerSelectedThemeIds.length !== 3) {
      setPickerError('Choisissez une couleur et exactement 3 thèmes.')
      return
    }

    setPickerSubmitting(true)
    setPickerError('')
    try {
      await selectPlayerColor(configuringPlayerId, gameSessionId, pickerSelectedColor)
      await selectPlayerThemes(configuringPlayerId, gameSessionId, pickerSelectedThemeIds)

      const statuses = await fetchSetupStatuses(finalistIds, gameSessionId)
      setSetupStatuses(statuses)
      closePicker()

      if (Object.values(statuses).every((s) => s.setup_complete)) {
        if (isHost) {
          await createGridAndStart()
        } else {
          setSetupPhase(false)
          setWaitingForGrid(true)
        }
      }
    } catch (err) {
      setPickerError(err instanceof Error ? err.message : 'Erreur lors de la sélection')
    } finally {
      setPickerSubmitting(false)
    }
  }

  const refreshPlayers = async (id: number) => {
    const [board, turn] = await Promise.all([
      getMemoryGridStandings(id),
      getCurrentPlayerTurn(id),
    ])
    setStandings(board.player_scores)
    setCurrentPlayerId(turn.current_player_id)
    setCurrentTurn(turn.current_turn)
  }

  const refreshState = async () => {
    if (!gridId) return
    // Chaque requête applique son propre résultat dès qu'il arrive (pas de
    // Promise.all groupé) pour ne pas retarder l'affichage de la grille
    // derrière les requêtes de classement/tour, qui sont moins urgentes.
    // Le garde de séquence évite seulement qu'une réponse issue d'un appel
    // plus ancien n'écrase un état plus récent.
    const seq = ++refreshSeq.current
    try {
      const state = await getMemoryGridState(gridId)
      if (seq === refreshSeq.current) {
        setGridState(state)
        if (state.memory_grid.round_id) setRoundId(state.memory_grid.round_id)
      }
    } catch (err) {
      console.error('Erreur refresh (state):', err)
    }
    try {
      const [board, turn] = await Promise.all([
        getMemoryGridStandings(gridId),
        getCurrentPlayerTurn(gridId),
      ])
      if (seq === refreshSeq.current) {
        setStandings(board.player_scores)
        setCurrentPlayerId(turn.current_player_id)
        setCurrentTurn(turn.current_turn)
      }
    } catch (err) {
      console.error('Erreur refresh (joueurs):', err)
    }
  }

  const handleCellClick = async (cell: GridCell) => {
    // Seul l'appareil du finaliste dont c'est le tour peut révéler une
    // cellule — jamais l'hôte, jamais un autre finaliste (spectateur inclus).
    if (isSpectator || cell.status !== 'hidden' || !roundId || myPlayerId === null || myPlayerId !== currentPlayerId) return

    try {
      await revealCell({
        round_id: roundId,
        player_id: myPlayerId,
        cell_id: cell.id,
      })

      const updatedState = await getMemoryGridState(gridId!)
      setGridState(updatedState)
      setSelectedCell(updatedState.cells.find((c) => c.id === cell.id) || cell)
      setAnswerText('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur révélation cellule')
    }
  }

  // AD-3 : on soumet la RÉPONSE du joueur ; le serveur seul juge.
  const handleSubmitAnswer = async () => {
    if (isSpectator || !selectedCell || !roundId || myPlayerId === null || myPlayerId !== currentPlayerId || submitting) return

    setSubmitting(true)
    try {
      const result = await answerCell({
        round_id: roundId,
        player_id: myPlayerId,
        cell_id: selectedCell.id,
        player_answer: answerText,
      })

      setAnswerFeedback({
        points: result.points_awarded,
        cellType: result.cell_type,
        isCorrect: result.is_correct,
        correctAnswer: result.correct_answer,
      })
      // C-004 Scenario 1 : effet visuel sur la cellule elle-même, en plus de
      // la modale de feedback ci-dessus.
      setLastCaptured({ cellId: selectedCell.id, isCorrect: result.is_correct })
      lastCapturedCellRef.current = selectedCell.id

      // On attend que l'état rafraîchi (score, progression) soit appliqué
      // AVANT de fermer la modale de la cellule : sinon le plateau affiché
      // derrière peut brièvement montrer l'ancien score pendant la requête.
      await refreshState()
      setSelectedCell(null)
      setAnswerText('')

      setTimeout(() => setAnswerFeedback(null), 3000)
      const capturedCellId = selectedCell.id
      setTimeout(() => {
        // Ne pas effacer une capture plus récente si une deuxième réponse est
        // arrivée entre-temps (moins de 1200ms d'écart entre deux captures).
        if (lastCapturedCellRef.current === capturedCellId) setLastCaptured(null)
      }, 1200)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur réponse')
    } finally {
      setSubmitting(false)
    }
  }

  const handleEndGame = () => navigate(`/results/${code}`)

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="text-2xl text-text animate-pulse mb-2">🧠 Manche 3</div>
          <p className="text-text-muted">{initStep}</p>
        </div>
      </div>
    )
  }

  if (setupPhase) {
    const configuringName = configuringPlayerId !== null ? finalistNames[configuringPlayerId] : null
    return (
      <div className="min-h-screen p-4">
        <div className="max-w-3xl mx-auto">
          <h1 className="text-2xl font-bold font-display mb-1">🎨 Manche 3 — Préparation</h1>
          <p className="text-text-muted text-sm mb-6">
            Chaque finaliste choisit sa couleur et 3 thèmes avant que la grille ne soit constituée.
          </p>

          {(() => {
            // Bug playtest 2026-08-16 : le tour par rôle (ordre du classement
            // Manche 2) est désormais imposé côté serveur — on le reflète ici
            // pour ne proposer "Configurer" qu'au bon joueur.
            const currentTurnPlayerId =
              Object.values(setupStatuses).find((s) => s.current_turn_player_id != null)
                ?.current_turn_player_id ?? null
            return (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
                {finalistIds.map((id) => {
                  const status = setupStatuses[id]
                  const ready = status?.setup_complete ?? false
                  const isMyTurn = currentTurnPlayerId === id
                  return (
                    <div key={id} className={`card flex items-center justify-between ${ready ? 'border-success' : ''}`}>
                      <div>
                        <p className="font-bold">{finalistNames[id] ?? `Joueur ${id}`}</p>
                        {/* BUG-303/304 : jamais la couleur/les thèmes des autres avant la fin du setup — juste prêt/pas prêt. */}
                        <p className="text-xs text-text-muted">
                          {ready ? '✅ Prêt' : isMyTurn ? '🎯 À son tour' : '⏳ En attente'}
                        </p>
                      </div>
                      {!ready && isMyTurn && id === myPlayerId && (
                        <button onClick={() => openPicker(id)} className="btn-secondary text-sm">
                          Configurer
                        </button>
                      )}
                      {!ready && !(isMyTurn && id === myPlayerId) && (
                        <p className="text-xs text-text-muted italic">
                          {id === myPlayerId
                            ? 'En attente de votre tour...'
                            : isHost ? 'Sur son propre appareil' : 'En attente...'}
                        </p>
                      )}
                    </div>
                  )
                })}
              </div>
            )
          })()}

          {configuringPlayerId !== null && (
            <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
              <div className="card max-w-lg w-full max-h-[90vh] overflow-y-auto">
                <h3 className="text-xl font-bold mb-4">Setup de {configuringName}</h3>

                <p className="text-sm font-semibold text-text-muted mb-2">Couleur</p>
                <div className="flex flex-wrap gap-2 mb-4">
                  {pickerColors.map((color) => (
                    <button
                      key={color}
                      onClick={() => setPickerSelectedColor(color)}
                      className={`px-3 py-1 rounded border-2 text-sm capitalize ${
                        pickerSelectedColor === color ? 'border-brand' : 'border-border'
                      }`}
                    >
                      {color}
                    </button>
                  ))}
                  {pickerColors.length === 0 && (
                    <p className="text-xs text-text-muted">Aucune couleur disponible.</p>
                  )}
                </div>

                <p className="text-sm font-semibold text-text-muted mb-2">
                  Thèmes ({pickerSelectedThemeIds.length}/3)
                </p>
                <div className="grid grid-cols-1 gap-2 mb-4">
                  {pickerThemes.map((theme) => {
                    const selected = pickerSelectedThemeIds.includes(theme.id)
                    return (
                      <button
                        key={theme.id}
                        onClick={() => toggleThemeSelection(theme.id)}
                        className={`text-left px-3 py-2 rounded border-2 text-sm ${
                          selected ? 'border-brand' : 'border-border'
                        }`}
                      >
                        <span className="font-semibold">{theme.name}</span>
                        <span className="text-text-muted"> — {theme.category}</span>
                      </button>
                    )
                  })}
                  {pickerThemes.length === 0 && (
                    <p className="text-xs text-text-muted">Aucun thème disponible.</p>
                  )}
                </div>

                {pickerError && <p className="text-sm text-danger mb-3">{pickerError}</p>}

                <div className="flex gap-2">
                  <button onClick={closePicker} className="btn-secondary flex-1">
                    Annuler
                  </button>
                  <button
                    onClick={submitPicker}
                    disabled={pickerSubmitting}
                    className="btn-primary flex-1"
                  >
                    {pickerSubmitting ? 'Validation...' : 'Valider'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {error && (
            <div className="fixed bottom-4 right-4 bg-danger/90 text-bg px-4 py-2 rounded-lg text-sm max-w-md">
              {error}
              <button onClick={() => setError('')} className="ml-2 text-bg/70 hover:text-bg">
                ✕
              </button>
            </div>
          )}
        </div>
      </div>
    )
  }

  // BUG-401 (#32) : un spectateur sans grille à suivre (Manche 3 pas encore
  // démarrée par l'hôte) attend, il ne doit jamais voir l'écran d'erreur
  // générique ci-dessous — le polling de spectateur (useEffect isSpectator)
  // réessaiera automatiquement dès que l'hôte aura créé la grille.
  if (isSpectator && !gridState) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <SpectatorView message="En attente du démarrage de la Manche 3 par l'hôte...">
          <div className="card text-center py-8">
            <div className="animate-spin h-8 w-8 border-4 border-text border-t-transparent rounded-full mx-auto"></div>
          </div>
        </SpectatorView>
      </div>
    )
  }

  // Setup personnel terminé côté finaliste, mais l'hôte n'a pas encore créé
  // et démarré la grille (host-gated) : on l'attend, sans écran d'erreur.
  if (waitingForGrid && !gridState) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="card text-center py-8 max-w-md">
          <div className="animate-spin h-8 w-8 border-4 border-text border-t-transparent rounded-full mx-auto mb-4"></div>
          <p className="text-text-muted">En attente que l'hôte lance la grille mémoire...</p>
        </div>
      </div>
    )
  }

  if (!game || !gridState) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="card text-center">
          <h2 className="text-2xl text-danger mb-4">Erreur</h2>
          <p className="text-text-muted mb-4">{error}</p>
          <button onClick={() => navigate(`/game/${code}/host`)} className="btn-primary">
            Retour au jeu
          </button>
        </div>
      </div>
    )
  }

  const cols = gridState.memory_grid.cols || gridState.memory_grid.grid_size || 5

  const getCellStyle = (cell: GridCell) => {
    // C-004 Scenario 1 : effet de capture, différencié bonne/mauvaise réponse.
    const captureEffect =
      lastCaptured?.cellId === cell.id
        ? lastCaptured.isCorrect
          ? 'animate-success-pulse'
          : 'animate-error-shake'
        : ''

    if (cell.status === 'matched') {
      const color = colorFor(cell.matched_by_player_id)
      return `${captureEffect} ${
        color
          ? `${color.bg} ${color.border} border-2 cursor-not-allowed`
          : 'bg-success/30 border-2 border-success cursor-not-allowed'
      }`
    }
    if (cell.status === 'revealed') {
      return 'bg-accent/30 border-2 border-accent animate-pulse cursor-not-allowed'
    }
    // BUG-304 : une cellule cachée ne doit rien révéler sur son propriétaire
    // (couleur ou bordure) avant d'être effectivement révélée par un joueur.
    return 'bg-surface-raised hover:bg-brand-muted cursor-pointer hover:scale-105 border-2 border-border'
  }

  const getCellContent = (cell: GridCell) => {
    if (cell.status === 'matched') {
      // Playtest 2026-08-15 : cellule perdue par expiration du temps de
      // réponse (skip-turn) — personne ne l'a « gagnée ».
      if (cell.matched_by_player_id === null) return '⏱'
      return initialFor(nameFor(cell.matched_by_player_id))
    }
    if (cell.status === 'revealed') return '❓'
    return '?'
  }

  return (
    <div className="min-h-screen p-4">
      <div className="max-w-6xl mx-auto">
        {isSpectator && (
          <div className="bg-surface-raised border border-border rounded-lg p-3 mb-4 text-center">
            <p className="text-sm text-text-muted">👁️ Vous suivez la partie en spectateur — lecture seule.</p>
          </div>
        )}

        {/* Bug playtest 2026-08-16 : ni le spectateur (éliminé) ni les AUTRES
            finalistes (qualifiés mais pas leur tour) ne voyaient la question
            que le joueur actif est en train de résoudre — selectedCell (qui
            alimente le modal de question plus bas) n'est renseigné que sur
            l'appareil du joueur qui a lui-même révélé la case. On dérive la
            même info en lecture seule depuis gridState, qui contient déjà le
            texte de la question dès que son statut n'est plus "hidden" (voir
            get_grid_state côté backend) — pour quiconque n'a pas la main
            (spectateur OU finaliste dont ce n'est pas le tour). */}
        {myPlayerId !== currentPlayerId && (() => {
          const revealedCell = gridState.cells.find((c) => c.status === 'revealed')
          if (!revealedCell) return null
          return (
            <div className="card mb-4">
              <h3 className="text-sm font-semibold text-text-muted mb-2">
                Question en cours — {nameFor(currentPlayerId)}
              </h3>
              {revealedCell.question ? (
                <>
                  <p className="text-lg text-text mb-1">{revealedCell.question.text}</p>
                  <p className="text-xs text-text-muted">
                    {revealedCell.question.category} • {revealedCell.question.points} pts
                  </p>
                </>
              ) : (
                <p className="text-text-muted">Question chargée...</p>
              )}
            </div>
          )
        })()}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold font-display">🧠 Manche 3 — Grille Mémoire</h1>
            <p className="text-text-muted text-sm">
              Code: <span className="font-mono font-bold text-brand">{game.code}</span>
              {' • '}Progression: {matchedCells}/{totalQuestions} ({progress}%)
              {' • '}4 finalistes
            </p>
          </div>
          {!isSpectator && !isCompleted && (
            <button onClick={handleEndGame} className="btn-secondary text-sm" title="La partie continue pour les autres finalistes — ceci ne fait que vous amener sur l'écran des résultats.">
              Quitter vers les résultats
            </button>
          )}
        </div>

        <div className="w-full bg-border rounded-full h-2 mb-6">
          <div
            className="bg-brand h-2 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>

        {isMemorizing ? (
          <div className="space-y-4">
            <div className="card text-center py-4">
              <p className="text-lg font-bold text-accent">🧠 Mémorisez la grille !</p>
              <p className="text-sm text-text-muted mt-1">
                Chaque case colorée appartient à son finaliste — retenez leur position avant qu'elles ne se cachent.
              </p>
              <p className={`text-2xl font-bold mt-2 ${memorizeRemaining! <= 10 ? 'text-danger animate-timer-pulse' : 'text-text'}`}>
                ⏱ {memorizeRemaining}s
              </p>
              <div className="h-2 bg-border rounded-full overflow-hidden mt-2 max-w-md mx-auto">
                <div
                  className="h-full bg-brand transition-all duration-1000 ease-linear"
                  style={{ width: `${((memorizeRemaining ?? 0) / 120) * 100}%` }}
                />
              </div>
            </div>

            <div className="card">
              <h3 className="text-sm font-semibold text-text-muted mb-2">Finalistes</h3>
              <div className="flex flex-wrap gap-3 mb-4">
                {standings.map((s, idx) => {
                  const color = colorFor(s.player_id) ?? FINALIST_COLORS[idx % FINALIST_COLORS.length]
                  return (
                    <span key={s.player_id} className={`px-3 py-1 rounded-full text-sm font-semibold ${color.bg} border ${color.border} ${color.text}`}>
                      {s.player_name}
                    </span>
                  )
                })}
              </div>
              <div
                className="grid gap-2"
                style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
              >
                {gridState.cells.map((cell) => {
                  const color = colorFor(cell.assigned_player_id)
                  return (
                    <div
                      key={cell.id}
                      className={`aspect-square rounded-lg border-2 ${
                        color ? `${color.bg} ${color.border}` : 'bg-surface-raised border-border'
                      }`}
                    />
                  )
                })}
              </div>
            </div>
          </div>
        ) : isCompleted ? (
          <div className="card text-center py-12">
            <div className="text-6xl mb-2 animate-bounce-once">🏆</div>
            <h2 className="text-4xl font-bold font-display text-accent mb-4 animate-fade-in">Partie terminée !</h2>
            <p className="text-text-muted mb-6">Toutes les cellules ont été découvertes.</p>
            <div className="max-w-lg mx-auto space-y-2">
              {standings.map((s, idx) => {
                const cellsControlled = (s.stolen_cells ?? 0) + (s.own_theme_cells ?? 0) + (s.unassigned_cells ?? 0)
                const controlPercent = Math.round((cellsControlled / TOTAL_GRID_CELLS) * 100)
                const color = colorFor(s.player_id) ?? FINALIST_COLORS[idx % FINALIST_COLORS.length]
                return (
                  <div key={s.player_id} className="card py-2 px-4 text-left">
                    <div className="flex justify-between items-center">
                      <span className={color.text}>
                        {idx === 0 ? '🏆 ' : `${idx + 1}. `}
                        {s.player_name}
                      </span>
                      <span className="font-bold">{s.total_score} pts</span>
                    </div>
                    <p className="text-xs text-text-muted mt-1">
                      {cellsControlled}/{TOTAL_GRID_CELLS} cellules contrôlées ({controlPercent}%)
                      {' — '}
                      {s.own_theme_cells ?? 0} propres, {s.stolen_cells ?? 0} volées, {s.unassigned_cells ?? 0} neutres
                    </p>
                  </div>
                )
              })}
            </div>
            <button onClick={handleEndGame} className="btn-primary mt-6 text-lg px-8 py-3">
              Voir les résultats →
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            <div className="lg:col-span-1 space-y-4">
              {/* Classement des finalistes — AD-1 : score de Manche 3 seul */}
              <div className="card">
                <h3 className="text-sm font-semibold text-text-muted mb-2">Finalistes</h3>
                {standings.map((s, idx) => {
                  const color = colorFor(s.player_id) ?? FINALIST_COLORS[idx % FINALIST_COLORS.length]
                  const isTurn = s.player_id === currentPlayerId
                  return (
                    <div
                      key={s.player_id}
                      className={`flex items-center justify-between gap-2 text-sm mb-1 px-2 py-1 rounded ${
                        isTurn ? 'bg-accent/20 ring-1 ring-accent' : ''
                      }`}
                    >
                      <span className="flex items-center gap-2">
                        {/* Repère daltonisme (deutéranopie) : initiale en plus de la couleur, cf. EXPERIENCE.md Accessibility Floor */}
                        <div
                          aria-hidden="true"
                          className={`w-6 h-6 rounded flex items-center justify-center text-xs font-bold ${color.bg} border ${color.border} ${color.text}`}
                        >
                          {initialFor(s.player_name)}
                        </div>
                        <span className={color.text}>{s.player_name}</span>
                      </span>
                      <span className="font-bold">{s.total_score}</span>
                    </div>
                  )
                })}
              </div>
            </div>

            <div className="lg:col-span-3 space-y-4">
              <div className="card text-center">
                <p className="text-sm text-text-muted">C'est au tour de</p>
                <p className="text-2xl font-bold text-accent">
                  {nameFor(currentPlayerId)}
                </p>
                <p className="text-xs text-text-muted mt-1">
                  {myPlayerId !== null && myPlayerId === currentPlayerId
                    ? 'Cliquez sur une cellule cachée pour la révéler'
                    : isHost
                      ? "Vous suivez la partie — le joueur agit depuis son propre appareil"
                      : "En attente de votre tour..."}
                </p>
                {timeRemaining !== null && (
                  <div className="mt-3">
                    <p className={`text-sm font-bold ${timeRemaining <= 5 ? 'text-danger animate-timer-pulse' : 'text-text'}`}>
                      ⏱ {timeRemaining}s
                    </p>
                    <div className="h-2 bg-border rounded-full overflow-hidden mt-1">
                      <div
                        className={`h-full transition-all duration-1000 ease-linear ${
                          timeRemaining <= 5 ? 'bg-danger' : timeRemaining <= 10 ? 'bg-brand-600' : 'bg-success'
                        }`}
                        style={{ width: `${(timeRemaining / TURN_DURATION_SECONDS) * 100}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>

              {answerFeedback && (
                <div
                  className={`card text-center ${
                    answerFeedback.isCorrect ? 'border-success' : 'border-danger'
                  }`}
                >
                  {answerFeedback.isCorrect ? (
                    <>
                      <span className="text-3xl">✅</span>
                      <p className="text-xl font-bold text-success">
                        +{answerFeedback.points} points !
                      </p>
                      <p className="text-sm text-text-muted">
                        {answerFeedback.cellType === 'unassigned' && '(Case neutre — 1 pt)'}
                        {answerFeedback.cellType === 'own' && '(Votre thème — 2 pts)'}
                        {answerFeedback.cellType === 'stolen' && '(Case volée — 3 pts)'}
                      </p>
                    </>
                  ) : (
                    <>
                      <span className="text-3xl">❌</span>
                      <p className="text-xl font-bold text-danger">Mauvaise réponse</p>
                      <p className="text-sm text-text-muted">
                        Réponse attendue : {answerFeedback.correctAnswer}
                      </p>
                    </>
                  )}
                </div>
              )}

              <div
                className="grid gap-2"
                style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
              >
                {gridState.cells.map((cell) => {
                  const myTurn = myPlayerId !== null && myPlayerId === currentPlayerId
                  return (
                  <button
                    key={cell.id}
                    onClick={() => handleCellClick(cell)}
                    disabled={cell.status !== 'hidden' || !!selectedCell || !myTurn}
                    className={`
                      aspect-square rounded-lg font-bold text-sm transition-all duration-200
                      ${getCellStyle(cell)}
                      ${cell.status !== 'hidden' || selectedCell || !myTurn ? '' : 'active:scale-95'}
                    `}
                    title={
                      // BUG-303 : ne pas fuiter le propriétaire au survol avant révélation.
                      cell.status === 'matched' && cell.assigned_player_id
                        ? `Cellule de ${nameFor(cell.assigned_player_id)}`
                        : ''
                    }
                  >
                    {getCellContent(cell)}
                  </button>
                  )
                })}
              </div>

              <div className="flex gap-2">
                <button onClick={refreshState} className="btn-secondary text-sm">
                  🔄 Rafraîchir
                </button>
              </div>
            </div>
          </div>
        )}

        {selectedCell && (
          <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
            <div className="card max-w-lg w-full text-center">
              <h3 className="text-xl font-bold mb-2">Cellule révélée !</h3>

              {selectedCell.question ? (
                <div className="mb-4">
                  <p className="text-lg text-text mb-2">{selectedCell.question.text}</p>
                  <p className="text-xs text-text-muted">
                    {selectedCell.question.category} • {selectedCell.question.points} pts
                  </p>
                </div>
              ) : (
                <p className="text-text-muted mb-4">Question chargée...</p>
              )}

              <p className="text-sm text-text-muted mb-4">
                {selectedCell.assigned_player_id === null
                  ? '⬜ Case neutre (1 pt si bonne réponse)'
                  : selectedCell.assigned_player_id === currentPlayerId
                    ? '🏠 Votre thème ! (2 pts si bonne réponse)'
                    : `⚔️ Cellule de ${nameFor(selectedCell.assigned_player_id)} (3 pts si volée)`}
              </p>

              {timeRemaining !== null && (
                <div className="mb-4">
                  <p className={`text-sm font-bold ${timeRemaining <= 10 ? 'text-danger animate-timer-pulse' : 'text-text'}`}>
                    ⏱ {timeRemaining}s
                  </p>
                  <div className="h-2 bg-border rounded-full overflow-hidden mt-1">
                    <div
                      className={`h-full transition-all duration-1000 ease-linear ${
                        timeRemaining <= 10 ? 'bg-danger' : timeRemaining <= 20 ? 'bg-brand-600' : 'bg-success'
                      }`}
                      style={{ width: `${(timeRemaining / TURN_DURATION_SECONDS) * 100}%` }}
                    />
                  </div>
                </div>
              )}

              <p className="text-text-muted mb-2">
                Réponse de{' '}
                <span className="text-accent font-bold">{nameFor(currentPlayerId)}</span>
              </p>
              <input
                type="text"
                value={answerText}
                onChange={(e) => setAnswerText(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSubmitAnswer()}
                placeholder="Saisir la réponse..."
                autoFocus
                className="input-field w-full mb-3 text-center"
              />
              <button
                onClick={handleSubmitAnswer}
                disabled={submitting}
                className="btn-primary w-full text-lg py-3"
              >
                {submitting ? 'Validation...' : 'Valider la réponse'}
              </button>
              <p className="text-xs text-text-muted mt-2">
                La correction est vérifiée par le serveur.
              </p>
            </div>
          </div>
        )}

        {error && (
          <div className="fixed bottom-4 right-4 bg-danger/90 text-bg px-4 py-2 rounded-lg text-sm max-w-md">
            {error}
            <button onClick={() => setError('')} className="ml-2 text-bg/70 hover:text-bg">
              ✕
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default MemoryGrid

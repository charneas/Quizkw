import type {
  MemoryGridState,
  MemoryGridCreateResponse,
  SelectCellRequest,
  AnswerCellRequest,
  AnswerCellResponse,
  Theme,
  QualificationStatus,
} from '../types'

const API_BASE = '/api'

// BUG-103 : le host_token est reçu à la création de la partie (createGame) et
// stocké ici, côté navigateur du créateur uniquement — jamais transmis aux
// joueurs. Il prouve l'identité host sur les endpoints de contrôle de partie.
function hostTokenStorageKey(gameCode: string) {
  return `quizkw_host_token_${gameCode}`
}

export function storeHostToken(gameCode: string, hostToken: string) {
  localStorage.setItem(hostTokenStorageKey(gameCode), hostToken)
}

export function getHostToken(gameCode: string): string | null {
  return localStorage.getItem(hostTokenStorageKey(gameCode))
}

function hostHeaders(gameCode: string): Record<string, string> {
  const token = getHostToken(gameCode)
  return token ? { 'X-Host-Token': token } : {}
}

// BUG-101d : team_token est reçu à la création de l'équipe (createTeam) et à
// chaque adhésion (joinTeam), stocké ici par équipe (les ids d'équipe sont
// uniques tous jeux confondus, pas besoin de le préfixer par gameCode). Il
// prouve l'appartenance à l'équipe sur /tokens/use — seul endpoint couvert
// pour l'instant, voir #55.
function teamTokenStorageKey(teamId: number) {
  return `quizkw_team_token_${teamId}`
}

export function storeTeamToken(teamId: number, teamToken: string) {
  localStorage.setItem(teamTokenStorageKey(teamId), teamToken)
}

export function getTeamToken(teamId: number): string | null {
  return localStorage.getItem(teamTokenStorageKey(teamId))
}

function teamHeaders(teamId: number): Record<string, string> {
  const token = getTeamToken(teamId)
  return token ? { 'X-Team-Token': token } : {}
}

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  // ...options DOIT venir avant `headers`, sinon un appelant qui passe ses
  // propres `headers` (ex. useToken avec X-Team-Token) écrase entièrement
  // l'objet headers construit ci-dessous — y compris Content-Type, ce qui
  // fait échouer silencieusement toute requête avec un corps JSON (le body
  // part comme text/plain, FastAPI ne le parse plus). Bug détecté en revue
  // de code indépendante avant que le premier appelant réel (useToken,
  // BUG-101d) ne le déclenche.
  const response = await fetch(`${API_BASE}${endpoint}`, {
    credentials: 'include',
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })

  if (!response.ok) {
    // Session admin absente/expirée sur un écran protégé : rediriger vers le
    // login plutôt que laisser chaque page admin afficher un message d'erreur
    // générique sans indiquer qu'il faut se reconnecter.
    if (
      response.status === 401 &&
      window.location.pathname.startsWith('/admin') &&
      window.location.pathname !== '/admin/login'
    ) {
      window.location.href = '/admin/login'
    }
    const error = await response.json().catch(() => ({ detail: 'Erreur réseau' }))
    throw new Error(error.detail || `Erreur ${response.status}`)
  }

  return response.json()
}

// === Sessions de jeu ===

export async function createGame(data: any) {
  return fetchApi<any>('/games/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getGame(code: string) {
  return fetchApi<any>(`/games/${code}`)
}

export async function startGame(code: string) {
  return fetchApi<any>(`/games/${code}/start`, {
    method: 'POST',
    headers: hostHeaders(code),
  })
}

export async function advanceToPhase3(code: string) {
  return fetchApi<any>(`/games/${code}/advance-to-phase3`, {
    method: 'POST',
    headers: hostHeaders(code),
  })
}

// === Équipes et Joueurs ===

export async function createTeam(gameCode: string, data: any) {
  const team = await fetchApi<any>(`/games/${gameCode}/teams/`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  if (team?.id && team?.team_token) {
    storeTeamToken(team.id, team.team_token)
  }
  return team
}

export async function createPlayer(gameCode: string, data: { name: string }) {
  return fetchApi<any>(`/games/${gameCode}/players/`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function joinTeam(gameCode: string, teamId: number, data: { name: string }) {
  const player = await fetchApi<{ id: number; name: string; team_id: number; team_token?: string }>(`/games/${gameCode}/teams/${teamId}/players/`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  if (player?.team_token) {
    storeTeamToken(teamId, player.team_token)
  }
  return player
}

export interface Round2QualifiedPlayer {
  id: number
  name: string
  team_id: number | null
  team_name: string | null
  // BUG-207 : présent dès qu'un thème a été choisi, pour permettre au front
  // de restaurer selectedTheme/currentQuestion au reconnect.
  round2_stats: {
    theme_id: number | null
    theme: Theme | null
    score: number
    questions_answered: number
    correct_answers: number
    current_question_index: number
    qualification_status: QualificationStatus
    completed_at: string | null
  } | null
}

export async function getRound2QualifiedPlayers(gameCode: string) {
  return fetchApi<Round2QualifiedPlayer[]>(`/round2/${gameCode}/players`)
}

// === Jetons (Tokens) ===

export async function getTeamTokens(teamId: number) {
  const data = await fetchApi<any>(`/teams/${teamId}/tokens`)
  if (data && data.tokens) {
    return data.tokens
  }
  return data
}

export async function useToken(data: { team_id: number; token_type: string; target_team_id?: number }) {
  return fetchApi<any>('/tokens/use', {
    method: 'POST',
    body: JSON.stringify(data),
    headers: teamHeaders(data.team_id),
  })
}

// === Déroulement du jeu (Manche 1) ===

export async function getRandomQuestion() {
  return fetchApi<any>('/questions/random')
}

export async function setCurrentQuestion(gameCode: string, questionId: number) {
  return fetchApi<any>(`/games/${gameCode}/set-current-question`, {
    method: 'POST',
    body: JSON.stringify({ question_id: questionId }),
    headers: hostHeaders(gameCode),
  })
}

export async function getCurrentQuestion(gameCode: string) {
  return fetchApi<any>(`/games/${gameCode}/current-question`)
}

export async function getAnswersStatus(gameCode: string) {
  return fetchApi<any>(`/games/${gameCode}/answers-status`)
}

export async function submitAnswer(data: any) {
  return fetchApi<any>('/answers/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// === Roue Bonus/Malus ===

export async function spinWheel(teamId: number) {
  return fetchApi<any>('/wheel/spin', {
    method: 'POST',
    body: JSON.stringify({ team_id: teamId }),
  })
}

// === Grille Mémoire ===

export async function createMemoryGrid(code: string) {
  return fetchApi<MemoryGridCreateResponse>(`/games/${code}/memory-grid/create`, {
    method: 'POST',
    headers: hostHeaders(code),
  })
}

// H.011 (BUG-302) : variante de création de grille pilotée par les couleurs
// et thèmes choisis par chaque finaliste (au lieu d'une attribution aléatoire).
export async function createMemoryGridWithThemes(code: string) {
  return fetchApi<MemoryGridCreateResponse>(`/games/${code}/memory-grid/create-with-themes`, {
    method: 'POST',
    headers: hostHeaders(code),
  })
}

export interface AvailableColorsResponse {
  available_colors: string[]
  game_session_id: number
}

export async function getAvailableColors(gameSessionId: number) {
  return fetchApi<AvailableColorsResponse>(`/memory-grid/colors/available/${gameSessionId}`)
}

export interface AvailableTheme {
  id: number
  name: string
  category: string
  difficulty_level: number
  description: string
}

export interface AvailableThemesResponse {
  available_themes: AvailableTheme[]
  count: number
  message: string
}

export async function getAvailableThemesForSelection(gameSessionId: number) {
  return fetchApi<AvailableThemesResponse>(`/memory-grid/themes/available/${gameSessionId}`)
}

export async function selectPlayerColor(playerId: number, gameSessionId: number, color: string) {
  return fetchApi<{ success: boolean; player_id: number; color: string; message: string }>(
    '/memory-grid/color/select',
    {
      method: 'POST',
      body: JSON.stringify({ player_id: playerId, game_session_id: gameSessionId, color }),
    }
  )
}

export async function selectPlayerThemes(playerId: number, gameSessionId: number, themeIds: number[]) {
  return fetchApi<{ success: boolean; player_id: number; theme_ids: number[]; theme_names: string[]; message: string }>(
    '/memory-grid/theme/select',
    {
      method: 'POST',
      body: JSON.stringify({ player_id: playerId, game_session_id: gameSessionId, theme_ids: themeIds }),
    }
  )
}

export interface PlayerSetupStatus {
  player_id: number
  color_selected: boolean
  themes_selected: boolean
  selected_color: string | null
  selected_themes: number[] | null
  setup_complete: boolean
}

export async function getPlayerSetupStatus(playerId: number, gameSessionId: number) {
  return fetchApi<PlayerSetupStatus>(`/memory-grid/player/${playerId}/setup-status/${gameSessionId}`)
}

export async function startMemoryGridRound(code: string) {
  return fetchApi<{ round_id: number; message: string }>(`/games/${code}/memory-grid/start`, {
    method: 'POST',
    headers: hostHeaders(code),
  })
}

export async function getMemoryGridState(memoryGridId: number) {
  return fetchApi<MemoryGridState>(`/memory-grid/${memoryGridId}/state`)
}

export async function revealCell(data: SelectCellRequest) {
  return fetchApi<{ status: string; cell: unknown }>('/memory-grid/reveal-cell', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function answerCell(data: AnswerCellRequest) {
  return fetchApi<AnswerCellResponse>('/memory-grid/answer-cell', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// C-003 : fait passer au tour suivant quand le timer client arrive à 0.
// expectedTurn permet un compare-and-set côté serveur : si un autre client
// (ou une réponse) a déjà fait avancer le tour, l'appel est ignoré au lieu
// de sauter un tour supplémentaire.
export async function skipTurn(memoryGridId: number, expectedTurn: number) {
  return fetchApi<{ memory_grid_id: number; current_turn: number }>(
    `/memory-grid/${memoryGridId}/skip-turn?expected_turn=${expectedTurn}`,
    { method: 'POST' }
  )
}

// AD-0 : les 4 finalistes de la Manche 3, classés par score de Manche 2.
export async function getMemoryGridFinalists(code: string) {
  return fetchApi<{ finalists: number[]; game_session_id: number }>(
    `/games/${code}/memory-grid/finalists`
  )
}

export interface MemoryGridStandings {
  is_completed: boolean
  player_scores: Array<{
    player_id: number
    player_name: string
    stolen_cells: number
    own_theme_cells: number
    unassigned_cells: number
    total_score: number
  }>
  winner: { player_id: number; player_name: string; total_score: number } | null
  is_tie: boolean
  message: string
}

// Classement final adressé par code de partie (AD-1 : Manche 3 seule).
export async function getFinalStandings(code: string) {
  return fetchApi<MemoryGridStandings>(`/games/${code}/memory-grid/standings`)
}

// Classement courant des finalistes (AD-1 : score de Manche 3 uniquement).
export async function getMemoryGridStandings(memoryGridId: number) {
  return fetchApi<{
    is_completed: boolean
    player_scores: Array<{
      player_id: number
      player_name: string
      stolen_cells: number
      own_theme_cells: number
      unassigned_cells: number
      total_score: number
    }>
    winner: { player_id: number; player_name: string; total_score: number } | null
    is_tie: boolean
    message: string
  }>(`/memory-grid/${memoryGridId}/winner`)
}

export async function getCurrentPlayerTurn(memoryGridId: number) {
  return fetchApi<{
    memory_grid_id: number
    current_turn: number
    finalists: number[]
    current_player_id: number | null
  }>(`/memory-grid/${memoryGridId}/current-player-turn`)
}

// === Round 2 (16→8→4 Tournament) ===

// CORRECTION DES EXPORTS POUR S'ALIGNER AVEC ROUND2.TSX
export async function getRound2Themes(gameCode: string) {
  return fetchApi<any>(`/round2/${gameCode}/themes`)
}
export { getRound2Themes as getThemes }

export async function selectRound2Theme(gameCode: string, data: { player_id: number; theme_id: number }) {
  return fetchApi<any>(`/round2/${gameCode}/select-theme`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}
export { selectRound2Theme as selectTheme }

export async function getRound2Question(gameCode: string, playerId: number) {
  return fetchApi<any>(`/round2/${gameCode}/question?player_id=${playerId}`)
}
export { getRound2Question as getRound2QuestionData }

export async function submitRound2Answer(gameCode: string, data: { player_id: number; question_id: number; player_answer: string }) {
  return fetchApi<any>(`/round2/${gameCode}/answer`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}
export { submitRound2Answer as submitAnswerRound2 }

export async function getRound2Leaderboard(gameCode: string) {
  return fetchApi<any>(`/round2/${gameCode}/leaderboard`)
}
export { getRound2Leaderboard as getLeaderboard }

export async function advanceRound2Phase(gameCode: string) {
  return fetchApi<any>(`/round2/${gameCode}/advance`, {
    method: 'POST',
    headers: hostHeaders(gameCode),
  })
}
export { advanceRound2Phase as advancePhase }

export async function getRound2Progress(gameCode: string) {
  return fetchApi<any>(`/round2/${gameCode}/progress`)
}
export { getRound2Progress as getProgress }

// === Ping-Pong Duel ===

export async function getRandomPingPongTheme() {
  return fetchApi<{
    id: number
    title: string
    description: string | null
    correct_answers: string[]
    min_answers_to_win: number
    created_at: string
  }>('/ping-pong/random-theme')
}

// === Multi-screen Team State ===

interface DuelState {
  duel_id: number
  theme: {
    id: number
    title: string
    description: string | null
    correct_answers: string[]
    min_answers_to_win: number
  }
  team1: { id: number; name: string }
  team2: { id: number; name: string }
  current_turn_team_id: number
  current_turn_team_name: string
  turn_number: number
  answers_used: string[]
  is_completed: boolean
  winner_team_id: number | null
  is_my_turn_in_duel: boolean
}

export async function getTeamState(gameCode: string, teamId: number) {
  return fetchApi<{
    team_id: number
    team_name: string
    team_score: number
    game_session_id: number
    game_started: boolean
    game_phase: string
    is_my_turn: boolean
    has_answered: boolean
    answer_locked: boolean
    current_question: {
      id: number
      text: string
      category: string
      difficulty: string
      points: number
      correct_answer: string | null
      options: string[]
      answer_locked: boolean
      current_team_answer: string | null
    } | null
    active_duel: DuelState | null
    // BUG-104 / Story J.001 : duel d'une AUTRE équipe, exposé en lecture
    // seule à une équipe qui n'a pas de active_duel (voir TeamScreen.tsx).
    spectator_duel: DuelState | null
    tokens: { id: number; token_type: string; is_used: boolean }[]
    other_teams: { team_id: number; team_name: string; team_score: number; has_answered: boolean }[]
    all_answered: boolean
    validation_result: {
      correct_answer: string
      teams: { team_name: string; is_correct: boolean; points_earned: number }[]
    } | null
    last_wheel_event: {
      id: number
      effect_type: string
      value: number | null
      target_team_id: number
      target_team_name: string
      message: string
    } | null
    last_token_event: {
      id: number
      token_type: string
      using_team_id: number
      using_team_name: string
      target_team_id: number | null
      target_team_name: string | null
      message: string
    } | null
  }>(`/game/${gameCode}/team/${teamId}/state`)
}

export async function startPingPongDuel(data: {
  game_session_id: number
  theme_id: number
  team1_id: number
  team2_id: number
}) {
  return fetchApi<{
    duel_id: number
    theme: {
      id: number
      title: string
      description: string | null
      correct_answers: string[]
      min_answers_to_win: number
      created_at: string
    }
    team1: { id: number; name: string }
    team2: { id: number; name: string }
    current_turn_team_id: number
    turn_number: number
    answers_used: string[]
    is_completed: boolean
    winner_team_id: number | null
  }>('/ping-pong/duel/start', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function submitPingPongDuelAnswer(data: {
  duel_id: number
  team_id: number
  answer: string
}) {
  return fetchApi<{
    is_correct: boolean
    answer: string
    turn_number: number
    duel_continues: boolean
    winner_team_id: number | null
    winner_team_name: string | null
    next_turn_team_id: number | null
    message: string
  }>('/ping-pong/duel/answer', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getPingPongDuelState(duelId: number) {
  return fetchApi<{
    duel_id: number
    theme: {
      id: number
      title: string
      description: string | null
      correct_answers: string[]
      min_answers_to_win: number
    }
    team1: { id: number; name: string }
    team2: { id: number; name: string }
    current_turn_team_id: number
    current_turn_team_name: string
    turn_number: number
    answers_used: string[]
    is_completed: boolean
    winner_team_id: number | null
  }>(`/ping-pong/duel/${duelId}`)
}

export async function nextQuestion(gameCode: string) {
  return fetchApi<{ message: string; question_id: number; question_text: string }>(`/games/${gameCode}/next-question`, {
    method: 'POST',
    headers: hostHeaders(gameCode),
  })
}

// === Admin content (Epic F, story F.1) ===

import type {
  Question,
  ThemeCreateRequest,
  ThemeUpdateRequest,
  QuestionCreateRequest,
  QuestionUpdateRequest,
  ThemeDeleteResponse,
  QuestionDeleteResponse,
  ContentExport,
  ContentImportRequest,
  ContentImportResponse,
  QuestionStatsResponse,
  PropositionUpdateRequest,
} from '../types'

export async function adminLogin(email: string, password: string) {
  return fetchApi<{ message: string }>('/admin/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export async function adminLogout() {
  return fetchApi<{ message: string }>('/admin/logout', { method: 'POST' })
}

export async function adminListPendingPropositions() {
  return fetchApi<Proposition[]>('/admin/propositions/pending')
}

export async function adminUpdateProposition(propositionId: number, data: PropositionUpdateRequest) {
  return fetchApi<Proposition>(`/admin/propositions/${propositionId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function adminAcceptProposition(propositionId: number) {
  return fetchApi<{ proposition_id: number; question_id: number; message: string }>(
    `/admin/propositions/${propositionId}/accept`,
    { method: 'POST' }
  )
}

export async function adminRejectProposition(propositionId: number, reason: string) {
  return fetchApi<Proposition>(`/admin/propositions/${propositionId}/reject`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  })
}

export async function adminListRejectedPropositions() {
  return fetchApi<Proposition[]>('/admin/propositions/rejected')
}

export async function adminListThemes() {
  return fetchApi<Theme[]>('/admin/themes')
}

export async function adminCreateTheme(data: ThemeCreateRequest) {
  return fetchApi<Theme>('/admin/themes', { method: 'POST', body: JSON.stringify(data) })
}

export async function adminUpdateTheme(themeId: number, data: ThemeUpdateRequest) {
  return fetchApi<Theme>(`/admin/themes/${themeId}`, { method: 'PUT', body: JSON.stringify(data) })
}

export async function adminDeleteTheme(themeId: number) {
  return fetchApi<ThemeDeleteResponse>(`/admin/themes/${themeId}`, { method: 'DELETE' })
}

export async function adminListQuestions(themeId?: number) {
  const query = themeId !== undefined ? `?theme_id=${themeId}` : ''
  return fetchApi<Question[]>(`/admin/questions${query}`)
}

export async function adminCreateQuestion(data: QuestionCreateRequest) {
  return fetchApi<Question>('/admin/questions', { method: 'POST', body: JSON.stringify(data) })
}

export async function adminUpdateQuestion(questionId: number, data: QuestionUpdateRequest) {
  return fetchApi<Question>(`/admin/questions/${questionId}`, { method: 'PUT', body: JSON.stringify(data) })
}

export async function adminDeleteQuestion(questionId: number) {
  return fetchApi<QuestionDeleteResponse>(`/admin/questions/${questionId}`, { method: 'DELETE' })
}

export async function adminGetQuestionStats(questionId: number) {
  return fetchApi<QuestionStatsResponse>(`/admin/questions/${questionId}/stats`)
}

export async function adminExportContent() {
  return fetchApi<ContentExport>('/admin/content/export')
}

export async function adminImportContent(data: ContentImportRequest) {
  return fetchApi<ContentImportResponse>('/admin/content/import', { method: 'POST', body: JSON.stringify(data) })
}

export async function getPingPongDuelResults(duelId: number) {
  return fetchApi<{
    duel_id: number
    theme: {
      id: number
      title: string
      description: string | null
      correct_answers: string[]
      min_answers_to_win: number
    }
    team1: {
      id: number
      name: string
      turns: number
      correct_answers: string[]
    }
    team2: {
      id: number
      name: string
      turns: number
      correct_answers: string[]
    }
    winner_team_id: number
    winner_team_name: string
    total_turns: number
    answers_used: string[]
  }>(`/ping-pong/duel/${duelId}/results`)
}

// === Génération de contenu (Epic F, story F.2) ===

import type {
  ContentSuggestion,
  GenerateContentRequest,
  ApproveSuggestionResponse,
  RejectSuggestionResponse,
  CategoryMixResponse,
  FlagQuestionResponse,
  ContentFlag,
  ContentHistoryEntry,
} from '../types'

export async function adminGenerateContent(data: GenerateContentRequest) {
  return fetchApi<ContentSuggestion>('/admin/content/generate', { method: 'POST', body: JSON.stringify(data) })
}

export async function adminListSuggestions(status?: string) {
  const query = status ? `?status=${status}` : ''
  return fetchApi<ContentSuggestion[]>(`/admin/content/suggestions${query}`)
}

export async function adminApproveSuggestion(suggestionId: number) {
  return fetchApi<ApproveSuggestionResponse>(`/admin/content/suggestions/${suggestionId}/approve`, { method: 'POST' })
}

export async function adminRejectSuggestion(suggestionId: number, reason: string) {
  return fetchApi<RejectSuggestionResponse>(`/admin/content/suggestions/${suggestionId}/reject`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  })
}

export async function adminGetCategoryMix() {
  return fetchApi<CategoryMixResponse>('/admin/content/category-mix')
}

export async function adminListFlags(resolved?: boolean) {
  const query = resolved !== undefined ? `?resolved=${resolved}` : ''
  return fetchApi<ContentFlag[]>(`/admin/content/flags${query}`)
}

export async function adminResolveFlag(flagId: number, note?: string) {
  return fetchApi<ContentFlag>(`/admin/content/flags/${flagId}/resolve`, {
    method: 'POST',
    body: JSON.stringify({ note: note ?? null }),
  })
}

export async function adminGetHistory(params?: { entity_type?: string; entity_id?: number; limit?: number }) {
  const query = new URLSearchParams()
  if (params?.entity_type) query.set('entity_type', params.entity_type)
  if (params?.entity_id !== undefined) query.set('entity_id', String(params.entity_id))
  if (params?.limit !== undefined) query.set('limit', String(params.limit))
  const qs = query.toString() ? `?${query.toString()}` : ''
  return fetchApi<ContentHistoryEntry[]>(`/admin/content/history${qs}`)
}

export async function flagQuestion(questionId: number, reason: string) {
  return fetchApi<FlagQuestionResponse>(`/questions/${questionId}/flag`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  })
}

// === Propositions publiques (Epic F-ext, story F-ext-1.2) ===

import type { PropositionCreateRequest, Proposition } from '../types'

export async function submitProposition(data: PropositionCreateRequest) {
  return fetchApi<Proposition>('/propositions', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function listThemesForProposition() {
  return fetchApi<Theme[]>('/propositions/themes')
}

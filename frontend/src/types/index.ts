// Types correspondant aux schémas du backend

export interface Player {
  id: number
  name: string
  team_id: number | null  // Allow null for Round 2 individual play
}

export interface Team {
  id: number
  name: string
  icon?: string | null
  game_session_id: number
  score: number
  players: Player[]
}

export interface Token {
  id: number
  team_id: number
  token_type: TokenType
  is_used: boolean
}

export interface GameSession {
  id: number
  code: string
  total_players: number
  players_per_team: number
  manche1_question_count: number
  wheel_frequency: number
  current_round: RoundType
  current_question_id: number | null
  is_active: boolean
  started: boolean
  created_at: string
  teams: Team[]
}

export interface Question {
  id: number
  text: string
  category: string
  difficulty: Difficulty
  points: number
  correct_answer: string
  wrong_answers: string[]
  theme_id: number | null
  question_number: number | null
  image_url: string | null
  created_at: string
}

export interface QuestionResponse {
  question: Question
  options: string[]
}

export interface AnswerResponse {
  is_correct: boolean
  correct_answer: string
  points_earned: number
  team_score: number
}

export interface WheelSpinResponse {
  effect_type: 'malus' | 'ping_pong' | 'bonus'
  value: number | null
  message: string
}

// AD-0 : la Manche 3 est individuelle — les cellules appartiennent à des
// joueurs finalistes, pas à des équipes.
export interface GridCell {
  id: number
  memory_grid_id: number
  row: number
  col: number
  status: GridCellStatus
  assigned_player_id: number | null
  matched_by_player_id: number | null
  points_awarded: number
  question: GridQuestion | null
}

// AD-13 : le type reflète ce que le serveur envoie réellement pour une
// cellule — il n'expédie ni wrong_answers ni created_at ici.
export interface GridQuestion {
  id: number
  text: string
  category: string
  difficulty: Difficulty
  points: number
  correct_answer: string
}

export interface MemoryGridData {
  id: number
  game_session_id: number
  rows: number
  cols: number
  grid_size: number
  current_turn: number
  is_completed: boolean
}

export interface MemoryGridState {
  memory_grid: MemoryGridData
  cells: GridCell[]
}

// AD-13 : réponse de POST /games/:code/memory-grid/create telle que le serveur
// la sérialise — il envoie grid_size, pas rows/cols.
export interface MemoryGridCreateResponse {
  id: number
  game_session_id: number
  grid_size: number
  current_turn: number
  is_completed: boolean
}

export interface AnswerCellResponse {
  status: string
  is_correct: boolean
  correct_answer: string
  points_awarded: number
  cell_type: 'own' | 'stolen' | 'unassigned'
}

// Enums
export type Difficulty = 'easy' | 'medium' | 'hard'
export type TokenType = 'swap' | 'penalty' | 'bonus'
export type RoundType = 'manche_1' | 'manche_2' | 'manche_3'
export type GridCellStatus = 'hidden' | 'revealed' | 'matched'

// Request types
export interface CreateGameRequest {
  total_players: number
  players_per_team: number
  manche1_question_count: number
  wheel_frequency: number
}

export interface CreateTeamRequest {
  name: string
}

export interface SubmitAnswerRequest {
  question_id: number
  team_id: number
  player_answer: string
}

export interface UseTokenRequest {
  token_type: TokenType
  team_id: number
}

export interface SelectCellRequest {
  round_id: number
  player_id: number
  cell_id: number
}

export interface AnswerCellRequest {
  round_id: number
  player_id: number
  cell_id: number
  // AD-3 : on envoie la réponse du joueur ; le serveur seul décide si elle
  // est juste. Le front ne transmet plus de verdict.
  player_answer: string
}

// Round 2 Types (16→8→4 Tournament)
export type ThemeCategory = 'serious' | 'pop_culture' | 'whimsical'
export type QualificationStatus = 'playing' | 'qualified' | 'eliminated' | 'finalist'

export interface Theme {
  id: number
  name: string
  category: ThemeCategory
  difficulty_level: number
  description?: string
  created_at: string
}


export interface PlayerRound2Stats {
  id: number
  player_id: number
  game_session_id: number
  theme_id?: number
  score: number
  questions_answered: number
  correct_answers: number
  current_question_index: number
  qualification_status: QualificationStatus
  theme_selected_at?: string
  completed_at?: string
}

export interface ThemeSelectionRequest {
  player_id: number
  theme_id: number
}

export interface ThemeSelectionResponse {
  theme: Theme
  player_stats: PlayerRound2Stats
  message: string
}

export interface Round2QuestionRequest {
  player_id: number
}

export interface Round2QuestionResponse {
  question: Question
  question_number: number
  difficulty: number
  options: string[]
  time_limit: number
}

export interface Round2AnswerRequest {
  player_id: number
  question_id: number
  player_answer: string
}

export interface Round2AnswerResponse {
  is_correct: boolean
  points_awarded: number
  player_score: number
  correct_answer: string
  next_question_available: boolean
  qualification_status: string
}

export interface TournamentProgress {
  phase: string  // "16_players", "8_qualified", "4_finalists"
  players_total: number
  players_remaining: number
  players_eliminated: number
  top_players: {
    player_id: number
    player_name: string
    score: number
    status: QualificationStatus
  }[]
  current_turn_player_id?: number
  current_turn_player_name?: string
}

export interface IntermediateLeaderboardResponse {
  qualified_players: PlayerRound2Stats[]
  eliminated_players: PlayerRound2Stats[]
  cutoff_score: number
  message: string
}

export interface Round2AdvanceRequest {
  game_session_id: number
}

export interface Round2AdvanceResponse {
  new_phase: string
  qualified_count: number
  eliminated_count: number
  message: string
}

// === Admin content (Epic F, story F.1) ===

export interface ThemeCreateRequest {
  name: string
  category: ThemeCategory
  difficulty_level: number
  description?: string | null
}

export interface ThemeUpdateRequest {
  name?: string
  category?: ThemeCategory
  difficulty_level?: number
  description?: string | null
}

// `source_id` : id du thème dans le fichier exporté, utilisé par le serveur
// uniquement pour remapper les theme_id des questions du même import vers le
// nouvel id attribué (jamais persisté). Sans lui, réimporter un export
// rattache les questions à un id de thème périmé.
export interface ThemeImportEntry extends ThemeCreateRequest {
  source_id?: number | null
}

// Propositions (Epic F-ext, AD-13/AD-18) — reflète schemas.PropositionCreate/Proposition
export interface PropositionCreateRequest {
  text: string
  correct_answer: string
  wrong_answers: string[]
  theme_id?: number | null
  difficulty: Difficulty
}

export interface Proposition {
  id: number
  text: string
  correct_answer: string
  wrong_answers: string[]
  theme_id?: number | null
  difficulty: Difficulty
  status: 'pending' | 'accepted' | 'rejected'
  rejection_reason?: string | null
  created_at: string
}

export interface PropositionUpdateRequest {
  text?: string
  correct_answer?: string
  wrong_answers?: string[]
  theme_id?: number | null
  new_theme?: ThemeCreateRequest
  difficulty?: Difficulty
}

export interface QuestionCreateRequest {
  text: string
  category: string
  difficulty: Difficulty
  points: number
  correct_answer: string
  wrong_answers: string[]
  theme_id?: number | null
  question_number?: number | null
}

export interface QuestionUpdateRequest {
  text?: string
  category?: string
  difficulty?: Difficulty
  points?: number
  correct_answer?: string
  wrong_answers?: string[]
  theme_id?: number | null
  question_number?: number | null
}

export interface ThemeDeleteWarning {
  theme_id: number
  theme_name: string
  question_count: number
  message: string
}

export interface ThemeDeleteResponse {
  deleted_theme_id: number
  warning: ThemeDeleteWarning | null
  message: string
}

export interface QuestionDeleteResponse {
  deleted_question_id: number
  warning: ThemeDeleteWarning | null
  message: string
}

export interface ContentExport {
  themes: Theme[]
  questions: Question[]
}

export interface ContentImportRequest {
  themes: ThemeImportEntry[]
  questions: QuestionCreateRequest[]
}

export interface ContentImportResponse {
  themes_created: number
  questions_created: number
  message: string
}

export interface QuestionStatsResponse {
  question_id: number
  times_answered: number
  correct_answers: number
  success_rate: number
}

// === Génération de contenu (Epic F, story F.2) ===

export interface GeneratedQuestion {
  text: string
  correct_answer: string
  wrong_answers: string[]
  difficulty: Difficulty
}

export type SuggestionStatus = 'pending' | 'approved' | 'rejected'

export interface ContentSuggestion {
  id: number
  topic: string
  wikipedia_extract: string
  generated_theme_name: string
  generated_category: ThemeCategory
  generated_questions: GeneratedQuestion[]
  status: SuggestionStatus
  created_at: string
  reviewed_at: string | null
  rejection_reason: string | null
  created_theme_id: number | null
}

export interface GenerateContentRequest {
  topic: string
  category?: ThemeCategory | null
}

export interface ApproveSuggestionResponse {
  suggestion_id: number
  theme_id: number
  questions_created: number
  message: string
}

export interface RejectSuggestionResponse {
  suggestion_id: number
  message: string
}

export interface CategoryMixEntry {
  category: ThemeCategory
  current_count: number
  current_ratio: number
  target_ratio: number
}

export interface CategoryMixResponse {
  total_themes: number
  mix: CategoryMixEntry[]
  recommended_category: ThemeCategory
}

export interface FlagQuestionResponse {
  flag_id: number
  question_id: number
  message: string
}

export interface ContentFlag {
  id: number
  question_id: number
  reason: string
  flagged_at: string
  resolved: boolean
  resolved_at: string | null
  resolution_note: string | null
}

export interface ContentHistoryEntry {
  id: number
  entity_type: string
  entity_id: number
  action: string
  detail: string | null
  actor: string
  created_at: string
}

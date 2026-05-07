// Types correspondant aux schémas du backend

export interface Player {
  id: number
  name: string
  team_id: number | null  // Allow null for Round 2 individual play
}

export interface Team {
  id: number
  name: string
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
  current_round: RoundType
  current_question_id: number | null
  is_active: boolean
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
  effect_type: 'malus' | 'choice' | 'ping_pong' | 'bonus'
  value: number | null
  message: string
}

export interface GridCell {
  id: number
  memory_grid_id: number
  row: number
  col: number
  status: GridCellStatus
  matched_by_team_id: number | null
  question: Question | null
}

export interface MemoryGridData {
  id: number
  game_session_id: number
  grid_size: number
  current_turn: number
  is_completed: boolean
}

export interface MemoryGridState {
  memory_grid: MemoryGridData
  cells: GridCell[]
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
  team_id: number
  cell_id: number
}

export interface AnswerCellRequest {
  round_id: number
  team_id: number
  cell_id: number
  is_correct: boolean
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
  question_id: number
  player_answer: string
}

export interface Round2AnswerResponse {
  is_correct: boolean
  points_awarded: number
  player_score: number
  correct_answer: string
  next_question_available: boolean
}

export interface TournamentProgress {
  phase: string  // "16_players", "8_qualified", "4_finalists"
  players_total: number
  players_remaining: number
  players_eliminated: number
  top_players: {
    player_id: number
    score: number
    status: QualificationStatus
  }[]
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

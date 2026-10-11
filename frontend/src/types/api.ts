export interface HealthResponse {
  status: string
  version: string
}

export type ProviderKind = 'ollama' | 'openai_compat'

export interface ModelInfo {
  /** Namespaced: "{provider_id}:{name}" */
  id: string
  name: string
  provider_id: string
  provider_name: string
  provider_kind: ProviderKind
}

export interface ProviderStatus {
  id: string
  name: string
  kind: ProviderKind
  ok: boolean
  error: string | null
}

export interface ModelsResponse {
  models: ModelInfo[]
  providers: ProviderStatus[]
}

export type Role = 'system' | 'user' | 'assistant'

export interface Conversation {
  id: string
  title: string
  pinned: boolean
  archived: boolean
  shared: boolean
  /** Search results only: excerpt of the first matching message. */
  snippet?: string | null
  created_at: string
  updated_at: string
}

export interface ConversationPatch {
  title?: string
  /** "" clears it. */
  system_prompt?: string
  pinned?: boolean
  archived?: boolean
}

export type Rating = 1 | -1

export interface Message {
  id: number
  role: Role
  content: string
  model_id: string | null
  rating?: Rating | null
  rating_comment?: string | null
  created_at: string
}

export interface ConversationDetail extends Conversation {
  system_prompt: string | null
  share_id: string | null
  messages: Message[]
}

export interface ShareInfo {
  share_id: string
  created_at: string
  updated_at: string
}

export interface SharedChat {
  title: string
  messages: { role: Role; content: string; model_id: string | null }[]
  updated_at: string
}

export interface Usage {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
}

export type StreamEvent =
  | { delta: string }
  | { done: true; usage: Usage | null; message_id: number | null }
  | { error: string }

export interface ChatStreamRequest {
  conversation_id: string
  model_id: string
  action?: 'send' | 'regenerate' | 'edit'
  message?: string
  message_id?: number
}

export interface Provider {
  id: string
  name: string
  kind: ProviderKind
  base_url: string
  enabled: boolean
  has_key: boolean
  created_at: string
  updated_at: string
}

export interface ProviderInput {
  name: string
  kind: ProviderKind
  base_url: string
  api_key?: string | null
  enabled?: boolean
}

/** api_key: omit to keep the stored key, "" to remove it. */
export type ProviderPatch = Partial<Omit<ProviderInput, 'kind'>>

export interface ProviderHealth {
  ok: boolean
  latency_ms: number | null
  model_count: number | null
  error: string | null
}

export interface AppConfig {
  encryption_configured: boolean
  in_docker: boolean
  default_model: string | null
  /** False until the first account exists; that sign-up becomes the admin. */
  has_users: boolean
  signup_enabled: boolean
  guest_access: boolean
  oauth_providers: string[]
}

export type UserRole = 'admin' | 'user' | 'pending'

export interface User {
  id: string
  email: string | null
  name: string
  role: UserRole
  is_guest: boolean
  has_password: boolean
  created_at: string
  last_active_at: string
}

export interface AdminSettings {
  enable_signup: boolean
  default_user_role: 'user' | 'pending'
}

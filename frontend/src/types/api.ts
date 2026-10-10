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
  created_at: string
  updated_at: string
}

export interface Message {
  id: number
  role: Role
  content: string
  model_id: string | null
  created_at: string
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
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
  message: string
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
  providers_read_only: boolean
  encryption_configured: boolean
}

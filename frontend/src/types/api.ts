export interface HealthResponse {
  status: string
  version: string
}

export type ProviderKind = 'ollama' | 'openai_compat' | 'anthropic'

/** Groups in the model menu: real providers, plus saved custom models. */
export type CatalogKind = ProviderKind | 'custom'

export interface ModelInfo {
  /** Namespaced: "{provider_id}:{name}"; custom models are "persona:{id}" */
  id: string
  name: string
  provider_id: string
  provider_name: string
  provider_kind: CatalogKind
  /** Custom models only. */
  description?: string | null
  emoji?: string | null
  base_model_id?: string | null
}

export interface ProviderStatus {
  id: string
  name: string
  kind: CatalogKind
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
  /** Document passages the reply was grounded in. */
  sources?: Source[] | null
  /** Tools the model ran while writing the reply. */
  tools?: ToolTrace[] | null
  created_at: string
}

export interface ToolTrace {
  id: string
  name: string
  arguments: unknown
  /** Absent while the tool is still running. */
  output?: string
  error?: boolean
}

export interface ToolInfo {
  id: string
  label: string
  emoji: string
  summary: string
}

export interface Source {
  n: number
  /** Null for a web page. */
  document_id: string | null
  /** File name, or a web page's title. */
  filename: string
  page: number | null
  text: string
  url?: string | null
}

export type WebSearchEngine = '' | 'duckduckgo' | 'searxng' | 'brave' | 'tavily'

export interface WebSearchSettings {
  engine: WebSearchEngine
  base_url: string
  result_count: number
  has_key: boolean
}

export interface WebSearchTestResult {
  ok: boolean
  error?: string
  results: { title: string; url: string; snippet: string }[]
}

export interface Attachment {
  kind: 'collection' | 'document'
  id: string
  name: string
}

export interface AttachmentRefs {
  collection_ids: string[]
  document_ids: string[]
}

export interface KnowledgeDocument {
  id: string
  collection_id: string | null
  filename: string
  size_bytes: number
  page_count: number | null
  chunk_count: number
  warning: string | null
  created_at: string
}

export interface Collection {
  id: string
  name: string
  description: string
  document_count: number
  created_at: string
  updated_at: string
}

export interface CollectionDetail extends Collection {
  documents: KnowledgeDocument[]
}

export type EmbeddingEngine = '' | 'ollama' | 'openai'

export interface EmbeddingSettings {
  engine: EmbeddingEngine
  base_url: string
  model: string
  has_key: boolean
  embedded_chunks: number
  total_chunks: number
}

export interface ConversationDetail extends Conversation {
  system_prompt: string | null
  share_id: string | null
  attachments: Attachment[]
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
  /** Sent first when the reply draws on documents. */
  | { sources: Source[] }
  | { tool_call: { id: string; name: string; arguments: unknown } }
  | { tool_result: { id: string; output: string; error: boolean } }
  | { delta: string }
  /** model_id is set when a different model answered (refusal fallback). */
  | { done: true; usage: Usage | null; message_id: number | null; model_id?: string }
  /** discard: the model declined; throw away the partial text already shown. */
  | { error: string; discard?: boolean }

export interface ChatStreamRequest {
  conversation_id: string
  model_id: string
  action?: 'send' | 'regenerate' | 'edit'
  message?: string
  message_id?: number
  tools?: string[]
  web_search?: boolean
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
  max_upload_mb: number
  /** A search engine is set up, so chats can search the web. */
  web_search?: boolean
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
  enabled_tools?: string[]
}

export interface AdminModel {
  id: string
  name: string
  display_name: string | null
  hidden: boolean
  provider_id: string
  provider_name: string
  provider_ok: boolean
}

export interface CustomModelInput {
  name: string
  description: string
  emoji: string
  base_model_id: string
  system_prompt: string
  knowledge_ids: string[]
  tool_ids: string[]
  visibility: 'private' | 'public'
}

export interface CustomModel extends Omit<CustomModelInput, 'knowledge_ids'> {
  id: string
  model_id: string
  knowledge: Attachment[]
  is_owner: boolean
  created_at: string
  updated_at: string
}

export interface MemoryItem {
  id: number
  content: string
  created_at: string
  updated_at: string
}

export interface MemoryList {
  /** Memories are used in this user's chats. */
  enabled: boolean
  memories: MemoryItem[]
}

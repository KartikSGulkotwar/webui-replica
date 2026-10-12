import { apiFetch, apiUrl, toApiError } from './client'
import type {
  Attachment,
  AttachmentRefs,
  Collection,
  CollectionDetail,
  EmbeddingEngine,
  EmbeddingSettings,
  KnowledgeDocument,
} from '../types/api'

const col = (id: string) => `/api/knowledge/collections/${encodeURIComponent(id)}`

export const listCollections = () => apiFetch<Collection[]>('/api/knowledge/collections')

export const getCollection = (id: string) => apiFetch<CollectionDetail>(col(id))

export const createCollection = (body: { name: string; description?: string }) =>
  apiFetch<Collection>('/api/knowledge/collections', { method: 'POST', body: JSON.stringify(body) })

export const updateCollection = (id: string, body: { name?: string; description?: string }) =>
  apiFetch<Collection>(col(id), { method: 'PATCH', body: JSON.stringify(body) })

export const deleteCollection = (id: string) => apiFetch<void>(col(id), { method: 'DELETE' })

/** Multipart upload; extraction and indexing happen before it returns. */
export async function uploadDocument(
  file: File,
  collectionId?: string,
): Promise<KnowledgeDocument> {
  const form = new FormData()
  form.append('file', file)
  if (collectionId) form.append('collection_id', collectionId)
  const resp = await fetch(apiUrl('/api/knowledge/documents'), { method: 'POST', body: form })
  if (!resp.ok) throw await toApiError(resp)
  return resp.json()
}

export const deleteDocument = (id: string) =>
  apiFetch<void>(`/api/knowledge/documents/${encodeURIComponent(id)}`, { method: 'DELETE' })

export const setAttachments = (conversationId: string, refs: AttachmentRefs) =>
  apiFetch<Attachment[]>(`/api/conversations/${encodeURIComponent(conversationId)}/attachments`, {
    method: 'PUT',
    body: JSON.stringify(refs),
  })

export const getEmbeddingSettings = () => apiFetch<EmbeddingSettings>('/api/admin/embeddings')

export const saveEmbeddingSettings = (body: {
  engine: EmbeddingEngine
  base_url: string
  model: string
  api_key?: string
}) =>
  apiFetch<EmbeddingSettings>('/api/admin/embeddings', {
    method: 'PUT',
    body: JSON.stringify(body),
  })

export const testEmbeddings = () =>
  apiFetch<{ ok: boolean; dimensions?: number; error?: string }>('/api/admin/embeddings/test', {
    method: 'POST',
  })

export const reindexEmbeddings = () =>
  apiFetch<{ reindexed_chunks: number }>('/api/admin/embeddings/reindex', { method: 'POST' })

export const ACCEPTED_FILES =
  '.pdf,.docx,.txt,.md,.markdown,.csv,.json,.html,.htm,.rst,.log,.py,.js,.ts,.tsx,.java,.go,.sql,.yaml,.yml,.toml,.ini,.xml'

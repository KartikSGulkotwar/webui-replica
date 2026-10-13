import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { createConversation, deleteConversation } from '../api/conversations'
import { streamChat } from '../api/stream'
import {
  ARENA_MODEL_ID,
  type Attachment,
  type ChatStreamRequest,
  type ConversationDetail,
  type ImageRef,
  type Source,
  type ToolTrace,
} from '../types/api'
import { conversationKey } from './useConversation'

export type StreamStatus = 'streaming' | 'done' | 'stopped' | 'error'

export type ChatAction =
  | { kind: 'send'; content: string }
  /** Replace the replies to the last message (optionally with other models),
   * or just reply `messageId`. */
  | { kind: 'regenerate'; messageId?: number }
  /** Change an earlier message; everything after it is dropped. */
  | { kind: 'edit'; messageId: number; content: string }

/** One reply being written (several when models answer side by side). */
export interface PendingReply {
  /** Null for a hidden arena model. */
  modelId: string | null
  /** Column of a side-by-side reply; null for a single reply. */
  slot: number | null
  text: string
  status: StreamStatus
  error?: string
  /** Document passages this reply draws on (arrive before the text). */
  sources?: Source[]
  /** Tools run so far, updated as calls start and finish. */
  tools?: ToolTrace[]
  /** Images made for this reply. */
  images?: ImageRef[]
}

/** The in-flight exchange, shown until the saved messages come back from the server. */
export interface PendingExchange {
  conversationId: string
  kind: ChatAction['kind']
  /** Server messages kept before this exchange (after regenerate/edit trimmed the rest). */
  baseCount: number
  /** The new user message (send only). */
  userContent: string
  replies: PendingReply[]
  /** Arena: the models stay hidden until the user votes. */
  blind: boolean
  /** The whole exchange (every reply). */
  status: StreamStatus
  error?: string
  /** A send rejected before the backend stored it (rate limit, bad model…): the text goes back to the composer. */
  notSent?: boolean
}

/** Settings for a chat that doesn't exist yet; applied when the first message creates it. */
export interface NewChatOptions {
  systemPrompt?: string
  attachments?: Attachment[]
}

export interface RunOptions {
  /** Tools the model may call for this message. */
  tools?: string[]
  /** Search the web before answering. */
  webSearch?: boolean
  /** Make an image from the message, then reply. */
  image?: boolean
}

/** How many server messages there will be once this exchange is saved (replies
 * that produced nothing aren't saved). */
export const expectedCount = (p: PendingExchange) =>
  p.baseCount +
  (p.kind === 'send' ? 1 : 0) +
  p.replies.filter((r) => r.text !== '' || !!r.tools?.length || !!r.images?.length).length

const newReply = (modelId: string | null, slot: number | null): PendingReply => ({
  modelId,
  slot,
  text: '',
  status: 'streaming',
})

export function useChatStream(conversationId: string | undefined) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [pending, setPending] = useState<PendingExchange | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const streamingConvRef = useRef<string | null>(null)

  // Leaving the conversation (e.g. "New chat") stops its stream; the backend
  // keeps whatever was generated so far.
  useEffect(() => {
    if (abortRef.current && streamingConvRef.current !== conversationId) {
      abortRef.current.abort()
    }
  }, [conversationId])

  const run = useCallback(
    async (
      action: ChatAction,
      /** One model; several answer side by side; ARENA_MODEL_ID for a blind pair. */
      modelIds: string[],
      newChat: NewChatOptions = {},
      options: RunOptions = {},
    ) => {
      const [modelId, ...others] = modelIds
      const blind = modelId === ARENA_MODEL_ID
      const initialReplies = blind
        ? [newReply(null, 0), newReply(null, 1)]
        : modelIds.length > 1
          ? modelIds.map((m, i) => newReply(m, i))
          : [newReply(modelId, null)]
      if (abortRef.current) return
      if (!conversationId && action.kind !== 'send') return
      const controller = new AbortController()
      abortRef.current = controller
      const userContent = action.kind === 'send' ? action.content : ''

      let convId = conversationId
      try {
        if (!convId) {
          const attachments = newChat.attachments ?? []
          const conv = await createConversation({
            system_prompt: newChat.systemPrompt || undefined,
            attachments: attachments.length
              ? {
                  collection_ids: attachments
                    .filter((a) => a.kind === 'collection')
                    .map((a) => a.id),
                  document_ids: attachments.filter((a) => a.kind === 'document').map((a) => a.id),
                }
              : undefined,
          })
          convId = conv.id
          queryClient.setQueryData<ConversationDetail>(conversationKey(conv.id), {
            ...conv,
            system_prompt: newChat.systemPrompt || null,
            share_id: null,
            attachments,
            messages: [],
          })
          streamingConvRef.current = conv.id
          navigate(`/c/${conv.id}`)
        }
      } catch (err) {
        abortRef.current = null
        setPending({
          conversationId: '',
          kind: 'send',
          baseCount: 0,
          userContent,
          replies: [],
          blind,
          status: 'error',
          error: errorMessage(err),
          notSent: true,
        })
        return
      }

      const createdHere = !conversationId
      let opened = false
      const id = convId
      streamingConvRef.current = id

      // Regenerate/edit: trim the cached conversation the same way the server
      // will, so the old reply disappears immediately.
      const before = queryClient.getQueryData<ConversationDetail>(conversationKey(id))
      let kept = before?.messages ?? []
      if (action.kind === 'regenerate') {
        if (action.messageId !== undefined) {
          kept = kept.filter((m) => m.id !== action.messageId)
        } else {
          while (kept.at(-1)?.role === 'assistant') kept = kept.slice(0, -1)
        }
      }
      if (action.kind === 'edit') {
        const i = kept.findIndex((m) => m.id === action.messageId)
        if (i >= 0) kept = [...kept.slice(0, i), { ...kept[i], content: action.content }]
      }
      if (before && action.kind !== 'send') {
        queryClient.setQueryData<ConversationDetail>(conversationKey(id), {
          ...before,
          messages: kept,
        })
      }
      const baseCount = kept.length
      // Regenerating one of several replies keeps its column.
      const regenerated =
        action.kind === 'regenerate' && action.messageId !== undefined
          ? before?.messages.find((m) => m.id === action.messageId)
          : undefined
      if (regenerated?.slot != null) initialReplies[0].slot = regenerated.slot
      setPending({
        conversationId: id,
        kind: action.kind,
        baseCount,
        userContent,
        replies: initialReplies,
        blind,
        status: 'streaming',
      })

      const body: ChatStreamRequest = { conversation_id: id, model_id: modelId }
      if (others.length) body.model_ids = others
      if (options.tools?.length) body.tools = options.tools
      if (options.webSearch) body.web_search = true
      if (options.image) body.image_generation = true
      if (action.kind === 'send') body.message = action.content
      if (action.kind === 'regenerate') {
        body.action = 'regenerate'
        if (action.messageId !== undefined) body.message_id = action.messageId
      }
      if (action.kind === 'edit') {
        body.action = 'edit'
        body.message_id = action.messageId
        body.message = action.content
      }

      let final: { status: StreamStatus; error?: string } | null = null
      const update = (patch: Partial<PendingExchange>) =>
        setPending((p) => (p && p.conversationId === id ? { ...p, ...patch } : p))
      const side = initialReplies.length > 1
      // Untagged events belong to the only reply; side-by-side ones name theirs.
      const updateReply = (i: number, change: (r: PendingReply) => Partial<PendingReply>) =>
        setPending((p) =>
          p && p.conversationId === id
            ? {
                ...p,
                replies: p.replies.map((r, k) => (k === i ? { ...r, ...change(r) } : r)),
              }
            : p,
        )

      try {
        await streamChat(body, {
          signal: controller.signal,
          // The backend has saved the message and set the title; show it in the sidebar now.
          onOpen: () => {
            opened = true
            queryClient.invalidateQueries({ queryKey: ['conversations'] })
          },
          onEvent: (event) => {
            const i = event.reply ?? 0
            const turnEvent = side && event.reply === undefined
            if ('replies' in event) {
              update({
                blind: event.blind,
                replies: event.replies.map((r) => newReply(r.model_id, r.slot)),
              })
            } else if ('sources' in event) {
              updateReply(i, () => ({ sources: event.sources }))
            } else if ('tool_call' in event) {
              updateReply(i, (r) => ({ tools: [...(r.tools ?? []), { ...event.tool_call }] }))
            } else if ('tool_result' in event) {
              const result = event.tool_result
              // The model may have saved a memory: keep the Memory page current.
              if (!result.error) queryClient.invalidateQueries({ queryKey: ['memories'] })
              updateReply(i, (r) => ({
                tools: (r.tools ?? []).map((t) =>
                  t.id === result.id ? { ...t, output: result.output, error: result.error } : t,
                ),
              }))
            } else if ('images' in event) {
              updateReply(i, (r) => ({ images: [...(r.images ?? []), ...event.images] }))
            } else if ('delta' in event) {
              updateReply(i, (r) => ({ text: r.text + event.delta }))
            } else if ('error' in event) {
              if (turnEvent) {
                final = { status: 'error', error: event.error }
              } else {
                // A declined reply isn't an answer: hide what was already shown.
                updateReply(i, () => ({
                  status: 'error',
                  error: event.error,
                  ...(event.discard ? { text: '', tools: [] } : {}),
                }))
                if (!side) final = { status: 'error', error: event.error }
              }
            } else if ('done' in event) {
              if (turnEvent) {
                final = { status: 'done' }
              } else {
                // A fallback model answered: label the reply with it.
                updateReply(i, () => ({
                  status: 'done',
                  ...(event.model_id ? { modelId: event.model_id } : {}),
                }))
                if (!side) final = { status: 'done' }
              }
            }
          },
        })
        final ??= { status: 'error', error: 'The connection closed before the reply finished' }
      } catch (err) {
        final = controller.signal.aborted
          ? { status: 'stopped' }
          : { status: 'error', error: errorMessage(err) }
      }

      abortRef.current = null
      streamingConvRef.current = null

      if (!opened && final.status === 'error') {
        if (createdHere) {
          // Don't leave an empty "New chat" behind for a message that never got in.
          deleteConversation(id).catch(() => {})
          queryClient.removeQueries({ queryKey: conversationKey(id) })
          navigate('/', { replace: true })
        } else if (action.kind !== 'send') {
          // Nothing changed on the server: bring back what we trimmed.
          await queryClient.invalidateQueries({ queryKey: conversationKey(id) })
        }
        setPending({
          conversationId: createdHere ? '' : id,
          kind: action.kind,
          baseCount: action.kind === 'send' ? baseCount : (before?.messages.length ?? 0),
          userContent,
          replies: [],
          blind,
          status: 'error',
          error: final.error,
          notSent: action.kind === 'send',
        })
        queryClient.invalidateQueries({ queryKey: ['conversations'] })
        return
      }

      // Replies still marked as streaming ended with the exchange (stopped, or cut off).
      const ended = final
      setPending((p) =>
        p && p.conversationId === id
          ? {
              ...p,
              ...ended,
              replies: p.replies.map((r) =>
                r.status === 'streaming'
                  ? { ...r, status: ended.status === 'done' ? 'done' : ended.status }
                  : r,
              ),
            }
          : p,
      )

      await queryClient.invalidateQueries({ queryKey: conversationKey(id) })
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      if (final.status === 'stopped') {
        // The backend saves a stopped reply as soon as it notices the disconnect,
        // which can land just after the refetch above.
        setTimeout(() => queryClient.invalidateQueries({ queryKey: conversationKey(id) }), 800)
      }
    },
    [conversationId, navigate, queryClient],
  )

  const stop = useCallback(() => abortRef.current?.abort(), [])

  return { pending, run, stop, isStreaming: pending?.status === 'streaming' }
}

import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { createConversation, deleteConversation } from '../api/conversations'
import { streamChat } from '../api/stream'
import type { ChatStreamRequest, ConversationDetail } from '../types/api'
import { conversationKey } from './useConversation'

export type StreamStatus = 'streaming' | 'done' | 'stopped' | 'error'

export type ChatAction =
  | { kind: 'send'; content: string }
  /** Replace the last reply (optionally with another model). */
  | { kind: 'regenerate' }
  /** Change an earlier message; everything after it is dropped. */
  | { kind: 'edit'; messageId: number; content: string }

/** The in-flight exchange, shown until the saved messages come back from the server. */
export interface PendingExchange {
  conversationId: string
  kind: ChatAction['kind']
  /** Server messages kept before this exchange (after regenerate/edit trimmed the rest). */
  baseCount: number
  /** The new user message (send only). */
  userContent: string
  modelId: string
  text: string
  status: StreamStatus
  error?: string
  /** A send rejected before the backend stored it (rate limit, bad model…): the text goes back to the composer. */
  notSent?: boolean
}

/** How many server messages there will be once this exchange is saved. */
export const expectedCount = (p: PendingExchange) => p.baseCount + (p.kind === 'send' ? 2 : 1)

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
    async (action: ChatAction, modelId: string, newChatSystemPrompt?: string) => {
      if (abortRef.current) return
      if (!conversationId && action.kind !== 'send') return
      const controller = new AbortController()
      abortRef.current = controller
      const userContent = action.kind === 'send' ? action.content : ''

      let convId = conversationId
      try {
        if (!convId) {
          const conv = await createConversation({ system_prompt: newChatSystemPrompt || undefined })
          convId = conv.id
          queryClient.setQueryData<ConversationDetail>(conversationKey(conv.id), {
            ...conv,
            system_prompt: newChatSystemPrompt || null,
            share_id: null,
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
          modelId,
          text: '',
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
      if (action.kind === 'regenerate' && kept.at(-1)?.role === 'assistant')
        kept = kept.slice(0, -1)
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
      setPending({
        conversationId: id,
        kind: action.kind,
        baseCount,
        userContent,
        modelId,
        text: '',
        status: 'streaming',
      })

      const body: ChatStreamRequest = { conversation_id: id, model_id: modelId }
      if (action.kind === 'send') body.message = action.content
      if (action.kind === 'regenerate') body.action = 'regenerate'
      if (action.kind === 'edit') {
        body.action = 'edit'
        body.message_id = action.messageId
        body.message = action.content
      }

      let final: { status: StreamStatus; error?: string } | null = null
      const update = (patch: Partial<PendingExchange>) =>
        setPending((p) => (p && p.conversationId === id ? { ...p, ...patch } : p))

      try {
        await streamChat(body, {
          signal: controller.signal,
          // The backend has saved the message and set the title; show it in the sidebar now.
          onOpen: () => {
            opened = true
            queryClient.invalidateQueries({ queryKey: ['conversations'] })
          },
          onEvent: (event) => {
            if ('delta' in event) {
              setPending((p) =>
                p && p.conversationId === id ? { ...p, text: p.text + event.delta } : p,
              )
            } else if ('error' in event) {
              final = { status: 'error', error: event.error }
              // A declined reply isn't an answer: hide what was already shown.
              if (event.discard) update({ text: '' })
            } else if ('done' in event) {
              final = { status: 'done' }
              // A fallback model answered: label the reply with it.
              if (event.model_id) update({ modelId: event.model_id })
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
          modelId,
          text: '',
          status: 'error',
          error: final.error,
          notSent: action.kind === 'send',
        })
        queryClient.invalidateQueries({ queryKey: ['conversations'] })
        return
      }

      update(final)

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

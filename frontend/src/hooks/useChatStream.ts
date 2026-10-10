import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { createConversation } from '../api/conversations'
import { streamChat } from '../api/stream'
import type { ConversationDetail } from '../types/api'
import { conversationKey } from './useConversation'

export type StreamStatus = 'streaming' | 'done' | 'stopped' | 'error'

/** The in-flight exchange, shown until the saved messages come back from the server. */
export interface PendingExchange {
  conversationId: string
  /** Server message count when this exchange started. */
  baseCount: number
  userContent: string
  modelId: string
  text: string
  status: StreamStatus
  error?: string
}

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

  const send = useCallback(
    async (content: string, modelId: string) => {
      if (abortRef.current) return
      const controller = new AbortController()
      abortRef.current = controller

      let convId = conversationId
      try {
        if (!convId) {
          const conv = await createConversation()
          convId = conv.id
          queryClient.setQueryData<ConversationDetail>(conversationKey(conv.id), {
            ...conv,
            messages: [],
          })
          streamingConvRef.current = conv.id
          navigate(`/c/${conv.id}`)
        }
      } catch (err) {
        abortRef.current = null
        setPending({
          conversationId: '',
          baseCount: 0,
          userContent: content,
          modelId,
          text: '',
          status: 'error',
          error: errorMessage(err),
        })
        return
      }

      const id = convId
      streamingConvRef.current = id
      const baseCount =
        queryClient.getQueryData<ConversationDetail>(conversationKey(id))?.messages.length ?? 0
      setPending({
        conversationId: id,
        baseCount,
        userContent: content,
        modelId,
        text: '',
        status: 'streaming',
      })

      let final: { status: StreamStatus; error?: string } | null = null
      const update = (patch: Partial<PendingExchange>) =>
        setPending((p) => (p && p.conversationId === id ? { ...p, ...patch } : p))

      try {
        await streamChat(
          { conversation_id: id, model_id: modelId, message: content },
          {
            signal: controller.signal,
            // The backend has saved the message and set the title; show it in the sidebar now.
            onOpen: () => queryClient.invalidateQueries({ queryKey: ['conversations'] }),
            onEvent: (event) => {
              if ('delta' in event) {
                setPending((p) =>
                  p && p.conversationId === id ? { ...p, text: p.text + event.delta } : p,
                )
              } else if ('error' in event) {
                final = { status: 'error', error: event.error }
              } else if ('done' in event) {
                final = { status: 'done' }
              }
            },
          },
        )
        final ??= { status: 'error', error: 'The connection closed before the reply finished' }
      } catch (err) {
        final = controller.signal.aborted
          ? { status: 'stopped' }
          : { status: 'error', error: errorMessage(err) }
      }

      abortRef.current = null
      streamingConvRef.current = null
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

  return { pending, send, stop, isStreaming: pending?.status === 'streaming' }
}

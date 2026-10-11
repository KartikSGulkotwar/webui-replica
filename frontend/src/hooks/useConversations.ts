import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteConversation, listConversations, updateConversation } from '../api/conversations'
import type { Conversation, ConversationDetail, ConversationPatch } from '../types/api'
import { conversationKey } from './useConversation'

export const conversationsKey = ['conversations'] as const

/** The sidebar list (archived=false), archived chats, or search results (q). */
export function useConversations(params: { q?: string; archived?: boolean } = {}) {
  return useQuery({
    queryKey: [...conversationsKey, params.archived ? 'archived' : 'active', params.q ?? ''],
    queryFn: () => listConversations(params),
    placeholderData: (prev) => prev,
  })
}

/** Patch a conversation, updating every cached list and its detail right away. */
export function useUpdateConversation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: ConversationPatch }) =>
      updateConversation(id, patch),
    onMutate: async ({ id, patch }) => {
      await queryClient.cancelQueries({ queryKey: conversationsKey })
      const previous = queryClient.getQueriesData<Conversation[]>({ queryKey: conversationsKey })
      // The list doesn't carry the system prompt, so only copy the other fields.
      const listPatch = Object.fromEntries(
        Object.entries(patch).filter(
          ([key, value]) => key !== 'system_prompt' && value !== undefined,
        ),
      ) as Partial<Conversation>
      queryClient.setQueriesData<Conversation[]>({ queryKey: conversationsKey }, (list) =>
        list?.map((c) => (c.id === id ? { ...c, ...listPatch } : c)),
      )
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      ctx?.previous.forEach(([key, data]) => queryClient.setQueryData(key, data))
    },
    onSuccess: (_data, { id, patch }) => {
      queryClient.setQueryData<ConversationDetail>(conversationKey(id), (d) =>
        d
          ? {
              ...d,
              ...patch,
              system_prompt:
                patch.system_prompt === undefined ? d.system_prompt : patch.system_prompt || null,
            }
          : d,
      )
    },
    // Pinning or archiving moves chats between lists, so refetch them all.
    onSettled: () => queryClient.invalidateQueries({ queryKey: conversationsKey }),
  })
}

export function useDeleteConversation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteConversation(id),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: conversationsKey })
      const previous = queryClient.getQueriesData<Conversation[]>({ queryKey: conversationsKey })
      queryClient.setQueriesData<Conversation[]>({ queryKey: conversationsKey }, (list) =>
        list?.filter((c) => c.id !== id),
      )
      return { previous }
    },
    onError: (_err, _id, ctx) => {
      ctx?.previous.forEach(([key, data]) => queryClient.setQueryData(key, data))
    },
    onSuccess: (_data, id) => queryClient.removeQueries({ queryKey: conversationKey(id) }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: conversationsKey }),
  })
}

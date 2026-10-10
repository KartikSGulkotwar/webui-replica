import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteConversation, listConversations, renameConversation } from '../api/conversations'
import type { Conversation, ConversationDetail } from '../types/api'
import { conversationKey } from './useConversation'

export const conversationsKey = ['conversations'] as const

export function useConversations() {
  return useQuery({ queryKey: conversationsKey, queryFn: listConversations })
}

/** Optimistically apply `change` to the list; roll back if the request fails. */
function useListMutation<V>(
  mutationFn: (vars: V) => Promise<unknown>,
  change: (list: Conversation[], vars: V) => Conversation[],
  onSuccess?: (vars: V) => void,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onMutate: async (vars: V) => {
      await queryClient.cancelQueries({ queryKey: conversationsKey })
      const previous = queryClient.getQueryData<Conversation[]>(conversationsKey)
      if (previous) queryClient.setQueryData(conversationsKey, change(previous, vars))
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(conversationsKey, ctx.previous)
    },
    onSuccess: (_data, vars) => onSuccess?.(vars),
    onSettled: () => queryClient.invalidateQueries({ queryKey: conversationsKey }),
  })
}

export function useRenameConversation() {
  const queryClient = useQueryClient()
  return useListMutation(
    ({ id, title }: { id: string; title: string }) => renameConversation(id, title),
    (list, { id, title }) => list.map((c) => (c.id === id ? { ...c, title } : c)),
    ({ id, title }) =>
      queryClient.setQueryData<ConversationDetail>(conversationKey(id), (d) =>
        d ? { ...d, title } : d,
      ),
  )
}

export function useDeleteConversation() {
  const queryClient = useQueryClient()
  return useListMutation(
    (id: string) => deleteConversation(id),
    (list, id) => list.filter((c) => c.id !== id),
    (id) => queryClient.removeQueries({ queryKey: conversationKey(id) }),
  )
}

import { useQuery } from '@tanstack/react-query'
import { getConversation } from '../api/conversations'

export const conversationKey = (id: string) => ['conversation', id] as const

export function useConversation(id: string | undefined) {
  return useQuery({
    queryKey: conversationKey(id ?? ''),
    queryFn: () => getConversation(id!),
    enabled: !!id,
  })
}

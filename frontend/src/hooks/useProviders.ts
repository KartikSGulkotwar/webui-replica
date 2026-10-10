import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createProvider,
  deleteProvider,
  getConfig,
  listProviders,
  updateProvider,
} from '../api/providers'
import type { ProviderInput, ProviderPatch } from '../types/api'

export const providersKey = ['providers'] as const

export function useAppConfig() {
  return useQuery({ queryKey: ['config'], queryFn: getConfig, staleTime: Infinity })
}

export function useProviders() {
  return useQuery({ queryKey: providersKey, queryFn: listProviders })
}

/** Provider changes affect the model list, so refresh both. */
function useProviderMutation<V, R>(mutationFn: (vars: V) => Promise<R>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: providersKey })
      queryClient.invalidateQueries({ queryKey: ['models'] })
    },
  })
}

export const useCreateProvider = () =>
  useProviderMutation((body: ProviderInput) => createProvider(body))

export const useUpdateProvider = () =>
  useProviderMutation(({ id, patch }: { id: string; patch: ProviderPatch }) =>
    updateProvider(id, patch),
  )

export const useDeleteProvider = () => useProviderMutation((id: string) => deleteProvider(id))

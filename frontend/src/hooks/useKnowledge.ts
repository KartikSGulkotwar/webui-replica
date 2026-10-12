import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createCollection,
  deleteCollection,
  deleteDocument,
  getCollection,
  listCollections,
  updateCollection,
} from '../api/knowledge'

export const collectionsKey = ['knowledge', 'collections'] as const
export const collectionKey = (id: string) => ['knowledge', 'collection', id] as const

export const useCollections = () => useQuery({ queryKey: collectionsKey, queryFn: listCollections })

export const useCollection = (id: string | undefined) =>
  useQuery({ queryKey: collectionKey(id ?? ''), queryFn: () => getCollection(id!), enabled: !!id })

function useKnowledgeMutation<V, R>(fn: (vars: V) => Promise<R>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['knowledge'] }),
  })
}

export const useCreateCollection = () =>
  useKnowledgeMutation((body: { name: string; description?: string }) => createCollection(body))

export const useUpdateCollection = () =>
  useKnowledgeMutation(({ id, ...body }: { id: string; name?: string; description?: string }) =>
    updateCollection(id, body),
  )

export const useDeleteCollection = () => useKnowledgeMutation((id: string) => deleteCollection(id))

export const useDeleteDocument = () => useKnowledgeMutation((id: string) => deleteDocument(id))

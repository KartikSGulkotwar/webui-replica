import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  deleteUser,
  getAdminSettings,
  listUsers,
  saveAdminSettings,
  setUserRole,
} from '../api/admin'
import type { AdminSettings, UserRole } from '../types/api'

const usersKey = ['admin', 'users'] as const
const settingsKey = ['admin', 'settings'] as const

export const useUsers = () => useQuery({ queryKey: usersKey, queryFn: listUsers })

export function useSetUserRole() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, role }: { id: string; role: UserRole }) => setUserRole(id, role),
    onSettled: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  })
}

export function useDeleteUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: deleteUser,
    onSettled: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  })
}

export const useAdminSettings = () => useQuery({ queryKey: settingsKey, queryFn: getAdminSettings })

export function useSaveAdminSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: AdminSettings) => saveAdminSettings(body),
    onSuccess: (data) => {
      queryClient.setQueryData(settingsKey, data)
      queryClient.invalidateQueries({ queryKey: ['config'] })
    },
  })
}

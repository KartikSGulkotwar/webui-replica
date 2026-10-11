import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { continueAsGuest, getMe, login, logout, signup, updateMe } from '../api/auth'
import type { User } from '../types/api'

export const meKey = ['me'] as const

export function useMe() {
  return useQuery({ queryKey: meKey, queryFn: getMe, staleTime: 60_000, retry: false })
}

/** Not tied to who is signed in, so kept across sign-in/out. */
const SHARED_KEYS = new Set(['me', 'config'])

/** Signing in or out swaps the whole data set. */
function useSessionChange<V>(fn: (vars: V) => Promise<User | void>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (user) => {
      // Update "me" in place first: its observers (the auth gate) must see the
      // change. Wiping the whole cache would leave them watching a dead query.
      queryClient.setQueryData(meKey, user ?? null)
      // Then drop the previous user's data so nothing leaks into the next session.
      queryClient.removeQueries({
        predicate: (q) => !SHARED_KEYS.has(String(q.queryKey[0])),
      })
      // Whether any account exists yet (first-run screen) may have changed.
      queryClient.invalidateQueries({ queryKey: ['config'] })
    },
  })
}

export const useLogin = () => useSessionChange(login)
export const useSignup = () => useSessionChange(signup)
export const useGuest = () => useSessionChange(() => continueAsGuest())
export const useLogout = () => useSessionChange(() => logout())

export function useUpdateMe() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: updateMe,
    onSuccess: (user) => queryClient.setQueryData(meKey, user),
  })
}

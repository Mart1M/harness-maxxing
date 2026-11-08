import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import type { Worktree } from '../types'
import { qk } from './keys'

/** The git worktrees of a topic (its repository's own working tree first); [] when the topic holds no repository. */
export function useWorktrees(path: string, enabled = true) {
  return useQuery({ queryKey: qk.worktrees(path), queryFn: () => api.get<Worktree[]>('/api/worktrees', { path }), enabled, staleTime: 10_000 })
}

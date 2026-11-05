import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import type { ClaudeAuthBody, ClaudeAuthResult, ClaudeSettingsBody, ClaudeStatus, ClaudeTestResult, Ok, ProviderModel, ProviderTestResult, ProvidersStatus } from '../types'
import { qk } from './keys'
import { useMut } from './util'

export const claudeStatusQuery = () => ({ queryKey: qk.claude, queryFn: () => api.get<ClaudeStatus>('/api/claude/status') })
export function useClaudeStatus() {
  return useQuery(claudeStatusQuery())
}

/** Which agent CLIs (Claude Code, Codex, Cursor) are installed and signed in on this server. */
export function useProviders() {
  return useQuery({ queryKey: qk.providers, queryFn: () => api.get<ProvidersStatus>('/api/claude/providers'), staleTime: 30_000 })
}

/** Models a Codex / Cursor session can use (read from the CLI on the server). */
export function useProviderModels(id: string, enabled = true) {
  return useQuery({ queryKey: qk.providerModels(id), queryFn: () => api.get<{ models: ProviderModel[] }>(`/api/claude/providers/${id}/models`).then((r) => r.models), enabled: enabled && id !== 'claude', staleTime: 5 * 60_000 })
}

export function useProviderKey() {
  return useMut(({ id, value }: { id: string; value: string }) => api.post<Ok>(`/api/claude/providers/${id}/key`, { value }), { invalidate: [qk.providers], errorToast: false })
}
export function useProviderKeyRemove() {
  return useMut((id: string) => api.del<Ok>(`/api/claude/providers/${id}/key`), { invalidate: [qk.providers] })
}
export function useProviderTest() {
  return useMut((id: string) => api.post<ProviderTestResult>(`/api/claude/providers/${id}/test`), { invalidate: [qk.providers], errorToast: false })
}

export function useClaudeAuth() {
  return useMut((b: ClaudeAuthBody) => api.post<ClaudeAuthResult>('/api/claude/auth', b), {
    invalidate: [qk.claude, qk.onboarding, qk.health],
    errorToast: false,
  })
}

export function useClaudeAuthRemove() {
  return useMut(() => api.del<Ok>('/api/claude/auth'), { invalidate: [qk.claude, qk.onboarding, qk.health] })
}

export function useClaudeTest() {
  return useMut(() => api.post<ClaudeTestResult>('/api/claude/test'), { invalidate: [qk.claude], errorToast: false })
}

export function useClaudeSettings() {
  return useMut((b: ClaudeSettingsBody) => api.put<Ok>('/api/claude/settings', b), {
    optimistic: (b) => [
      {
        key: qk.claude,
        update: (s: ClaudeStatus) => {
          const { claude_auto_update: on, ...rest } = b
          return { ...s, ...rest, ...(on !== undefined && s.auto_update ? { auto_update: { ...s.auto_update, enabled: on } } : {}) }
        },
      },
    ],
    invalidate: [qk.claude],
  })
}

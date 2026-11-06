import { useQuery } from '@tanstack/react-query'
import { api, seg } from '../api'
import type { Ok, ProcessCreateBody, ProcessCredentials, ProcessInfo } from '../types'
import { qk } from './keys'
import { useMut } from './util'

/** Processes with their live state (polled while the page is open). */
export function useProcesses(enabled = true) {
  return useQuery({ queryKey: qk.processes, queryFn: () => api.get<ProcessInfo[]>('/api/processes'), enabled, refetchInterval: 4000, staleTime: 2000 })
}
export function useProcessLogs(name: string, enabled: boolean) {
  return useQuery({ queryKey: qk.processLogs(name), queryFn: () => api.get<{ lines: string[] }>(`/api/processes/${seg(name)}/logs?lines=300`).then((r) => r.lines), enabled, refetchInterval: 3000 })
}
export function useCreateProcess() {
  return useMut((b: ProcessCreateBody) => api.post<ProcessInfo>('/api/processes', b), { invalidate: [qk.processes], errorToast: false })
}
export function useProcessAction() {
  return useMut(({ name, action }: { name: string; action: 'start' | 'stop' | 'restart' }) => api.post<ProcessInfo>(`/api/processes/${seg(name)}/${action}`), { invalidate: [qk.processes] })
}
export function useDeleteProcess() {
  return useMut((name: string) => api.del<Ok>(`/api/processes/${seg(name)}`), { invalidate: [qk.processes] })
}
export function usePublishProcess() {
  return useMut(({ name, host }: { name: string; host?: string }) => api.post<ProcessCredentials>(`/api/processes/${seg(name)}/publish`, { host: host || null }), { invalidate: [qk.processes], errorToast: false })
}
export function useUnpublishProcess() {
  return useMut((name: string) => api.del<Ok>(`/api/processes/${seg(name)}/publish`), { invalidate: [qk.processes] })
}
export function fetchProcessCredentials(name: string) {
  return api.get<ProcessCredentials>(`/api/processes/${seg(name)}/credentials`)
}

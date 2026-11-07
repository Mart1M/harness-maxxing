import { useQuery } from '@tanstack/react-query'
import { api, seg } from '../api'
import type { PushDevice, PushState, PushTestResult } from '../types'
import { qk } from './keys'
import { useMut } from './util'

/** iPhone push: settings, Apple key (never returned), registered devices. */
export function usePush() {
  return useQuery({ queryKey: qk.push, queryFn: () => api.get<PushState>('/api/push'), staleTime: 15_000 })
}


export function usePushSettings() {
  return useMut((b: Partial<PushState['settings']>) => api.put<PushState>('/api/push/settings', b), { invalidate: [qk.push] })
}
export function usePushCredentials() {
  return useMut((b: { key?: string; key_id?: string; team_id?: string; topic?: string }) => api.put<PushState>('/api/push/credentials', b), { invalidate: [qk.push], errorToast: false })
}
export function usePushCredentialsRemove() {
  return useMut(() => api.del<PushState>('/api/push/credentials'), { invalidate: [qk.push] })
}
export function usePushDeviceRemove() {
  return useMut((id: string) => api.del<PushState>(`/api/push/devices/${seg(id)}`), { invalidate: [qk.push] })
}
export function usePushTest() {
  return useMut(() => api.post<PushTestResult>('/api/push/test'), { invalidate: [qk.push], errorToast: false })
}
/** The iOS app gives its device token to the page; the page registers it (idempotent). */
export function usePushDeviceAdd() {
  return useMut((b: PushDevice) => api.post<{ id: string; registered: boolean }>('/api/push/devices', b), { invalidate: [qk.push], errorToast: false })
}

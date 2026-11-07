import * as React from 'react'
import { usePushDeviceAdd } from '@/lib/queries'

/** The iOS app (user agent "HarnessiOS") puts its APNs device token on `window.__wuitbotPush` and fires
 *  `wuitbot-push` when it changes. The signed-in page hands it to the server, once per token and page load. */
export type NativePush = { token: string; env: 'production' | 'sandbox'; name?: string }

declare global {
  interface Window {
    __wuitbotPush?: NativePush
  }
}

export const isNativeApp = () => typeof navigator !== 'undefined' && navigator.userAgent.includes('HarnessiOS')

export function usePushRegistration() {
  const add = usePushDeviceAdd()
  const sent = React.useRef('')
  const { mutate } = add
  React.useEffect(() => {
    if (!isNativeApp()) return
    const send = (p?: NativePush) => {
      if (!p?.token || sent.current === p.token) return
      sent.current = p.token
      mutate({ token: p.token, env: p.env, name: p.name }, { onError: () => { sent.current = '' } })
    }
    send(window.__wuitbotPush)
    const on = (e: Event) => send((e as CustomEvent<NativePush>).detail)
    window.addEventListener('wuitbot-push', on)
    return () => window.removeEventListener('wuitbot-push', on)
  }, [mutate])
}

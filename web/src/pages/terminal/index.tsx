// Terminal page: an authenticated Bash command console rooted in the configured workspace.
import * as React from 'react'
import { Page } from '@/components/shell/Page'
import { useT } from '@/i18n'

const ansi = /\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]/g
const clean = (text: string) => text.replace(ansi, '').replace(/\r(?!\n)/g, '')

export default function TerminalPage() {
  const t = useT()
  const [command, setCommand] = React.useState('')
  const [output, setOutput] = React.useState('')
  const [connected, setConnected] = React.useState(false)
  const input = React.useRef<HTMLInputElement | null>(null)
  const socket = React.useRef<WebSocket | null>(null)

  React.useEffect(() => {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${location.host}/api/terminal/ws`)
    socket.current = ws
    ws.onopen = () => { setConnected(true); input.current?.focus() }
    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as { t?: string; data?: string }
        if (message.t === 'out' && typeof message.data === 'string') {
          const data = message.data
          setOutput((old) => (old + clean(data)).slice(-256_000))
        }
      } catch { /* invalid terminal output is ignored */ }
    }
    ws.onclose = () => setConnected(false)
    return () => ws.close()
  }, [])

  const run = () => {
    if (!command || !connected) return
    socket.current?.send(JSON.stringify({ data: command + '\n' }))
    setCommand('')
  }

  return (
    <Page title={t('terminal.title')} description={t('terminal.description')} width="wide" bodyClassName="flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-0 flex-1 flex-col gap-4">
        <p className="text-sm text-muted-foreground">{t('terminal.warning')}</p>
        <div
          className="min-h-[18rem] flex-1 cursor-text select-text overflow-auto rounded-xl border bg-zinc-950 p-4 font-mono text-[13px] leading-relaxed text-zinc-100 shadow-xs dark:bg-black"
          aria-live="polite"
          onClick={() => {
            // A drag ends with a click too: preserve the selection so terminal output can be copied.
            if (!window.getSelection()?.toString()) input.current?.focus()
          }}
        >
          <pre className="min-h-[1.5rem] whitespace-pre-wrap break-words">{output || t('terminal.empty')}</pre>
          <form
            className="flex items-center gap-2 text-emerald-400"
            onSubmit={(e) => { e.preventDefault(); run() }}
          >
            <span aria-hidden="true">$</span>
            <input
            ref={input}
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            onKeyDown={(e) => {
              if (e.ctrlKey && e.key.toLowerCase() === 'c' && !command) { e.preventDefault(); socket.current?.send(JSON.stringify({ data: '\u0003' })) }
              else if (e.key === 'Tab') { e.preventDefault(); socket.current?.send(JSON.stringify({ data: '\t' })) }
            }}
            placeholder={t('terminal.placeholder')}
            aria-label={t('terminal.input')}
            className="min-w-0 flex-1 bg-transparent text-zinc-100 outline-none placeholder:text-zinc-600"
            disabled={!connected}
            autoFocus
          />
            <span className="shrink-0 text-[11px] text-zinc-600">{connected ? t('terminal.hint') : t('terminal.connecting')}</span>
          </form>
        </div>
      </div>
    </Page>
  )
}

// Terminal page: an authenticated Bash command console rooted in the configured workspace.
import * as React from 'react'
import { Page } from '@/components/shell/Page'
import { api, errorMessage } from '@/lib/api'
import { useT } from '@/i18n'

type Result = { stdout: string; stderr: string; code: number; timed_out: boolean; truncated: boolean; cwd: string; duration_s: number }
type Entry = { command: string; result?: Result; error?: string }

export default function TerminalPage() {
  const t = useT()
  const [command, setCommand] = React.useState('')
  const [entries, setEntries] = React.useState<Entry[]>([])
  const [running, setRunning] = React.useState(false)
  const input = React.useRef<HTMLInputElement | null>(null)

  const run = async () => {
    const value = command.trim()
    if (!value || running) return
    setRunning(true)
    setCommand('')
    const index = entries.length
    setEntries((old) => [...old, { command: value }])
    try {
      const result = await api.post<Result>('/api/terminal/run', { command: value })
      setEntries((old) => old.map((entry, i) => (i === index ? { ...entry, result } : entry)))
    } catch (e) {
      setEntries((old) => old.map((entry, i) => (i === index ? { ...entry, error: errorMessage(e) } : entry)))
    } finally {
      setRunning(false)
      input.current?.focus()
    }
  }

  return (
    <Page title={t('terminal.title')} description={t('terminal.description')} width="wide" bodyClassName="flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-0 flex-1 flex-col gap-4">
        <p className="text-sm text-muted-foreground">{t('terminal.warning')}</p>
        <div
          className="min-h-[18rem] flex-1 cursor-text overflow-auto rounded-xl border bg-zinc-950 p-4 font-mono text-[13px] leading-relaxed text-zinc-100 shadow-xs dark:bg-black"
          aria-live="polite"
          onClick={() => input.current?.focus()}
        >
          {entries.length === 0 && <span className="text-zinc-500">{t('terminal.empty')}</span>}
          {entries.map((entry, i) => (
            <div key={i} className="mb-5 last:mb-0">
              <div className="whitespace-pre-wrap text-emerald-400">$ {entry.command}</div>
              {entry.error && <pre className="mt-1 whitespace-pre-wrap break-words text-red-300">{entry.error}</pre>}
              {entry.result && <>
                {entry.result.stdout && <pre className="mt-1 whitespace-pre-wrap break-words">{entry.result.stdout}</pre>}
                {entry.result.stderr && <pre className="mt-1 whitespace-pre-wrap break-words text-amber-300">{entry.result.stderr}</pre>}
                <div className={entry.result.code === 0 ? 'mt-1 text-zinc-500' : 'mt-1 text-red-300'}>
                  {t('terminal.status', { code: entry.result.code, duration: entry.result.duration_s })}
                  {entry.result.timed_out ? ` · ${t('terminal.timedOut')}` : ''}
                  {entry.result.truncated ? ` · ${t('terminal.truncated')}` : ''}
                </div>
              </>}
              {!entry.result && !entry.error && <span className="text-zinc-500">{t('terminal.running')}</span>}
            </div>
          ))}
          <form
            className="flex items-center gap-2 text-emerald-400"
            onSubmit={(e) => { e.preventDefault(); void run() }}
          >
            <span aria-hidden="true">$</span>
            <input
            ref={input}
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            placeholder={t('terminal.placeholder')}
            aria-label={t('terminal.input')}
            className="min-w-0 flex-1 bg-transparent text-zinc-100 outline-none placeholder:text-zinc-600"
            disabled={running}
            autoFocus
          />
            <span className="shrink-0 text-[11px] text-zinc-600">{running ? t('terminal.running') : t('terminal.hint')}</span>
          </form>
        </div>
      </div>
    </Page>
  )
}

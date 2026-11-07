// Terminal page: an authenticated Bash command console rooted in the configured workspace.
import * as React from 'react'
import { Play, SquareTerminal } from 'lucide-react'
import { Page } from '@/components/shell/Page'
import { Button, Textarea } from '@/components/ui'
import { api, errorMessage } from '@/lib/api'
import { useT } from '@/i18n'

type Result = { stdout: string; stderr: string; code: number; timed_out: boolean; truncated: boolean; cwd: string; duration_s: number }
type Entry = { command: string; result?: Result; error?: string }

export default function TerminalPage() {
  const t = useT()
  const [command, setCommand] = React.useState('')
  const [entries, setEntries] = React.useState<Entry[]>([])
  const [running, setRunning] = React.useState(false)
  const input = React.useRef<HTMLTextAreaElement | null>(null)

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
        <div className="min-h-[18rem] flex-1 overflow-auto rounded-xl border bg-zinc-950 p-4 font-mono text-[13px] leading-relaxed text-zinc-100 shadow-xs dark:bg-black" aria-live="polite">
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
        </div>
        <div className="rounded-xl border bg-card p-2 shadow-xs focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/20">
          <Textarea
            ref={input}
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void run() } }}
            placeholder={t('terminal.placeholder')}
            aria-label={t('terminal.input')}
            minRows={2}
            maxRows={8}
            className="border-0 bg-transparent font-mono shadow-none focus-visible:ring-0 dark:bg-transparent"
            disabled={running}
          />
          <div className="flex items-center justify-between gap-3 px-1 pt-1">
            <span className="text-xs text-muted-foreground">{t('terminal.hint')}</span>
            <Button onClick={() => void run()} disabled={!command.trim()} loading={running} className="gap-1.5">
              {running ? <SquareTerminal /> : <Play />} {t('terminal.run')}
            </Button>
          </div>
        </div>
      </div>
    </Page>
  )
}

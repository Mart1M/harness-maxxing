// /process - commands running in repositories: state, logs, start / stop, and a password-protected URL.
import * as React from 'react'
import { Copy, ExternalLink, Eye, Globe, GlobeLock, Play, Plus, RotateCw, ScrollText, Square, Terminal, Trash2 } from 'lucide-react'
import { fetchProcessCredentials, useCreateProcess, useDeleteProcess, useProcessAction, useProcessLogs, useProcesses, usePublishProcess, useUnpublishProcess } from '@/lib/queries'
import { errorMessage } from '@/lib/api'
import { copyText } from '@/lib/utils'
import type { ProcessCredentials, ProcessInfo } from '@/lib/types'
import { useT } from '@/i18n'
import { Badge, Button, Card, CodeBlock, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, EmptyState, FormField, Input, Skeleton, StatusDot, confirm, toast } from '@/components/ui'
import { Page } from '@/components/shell/Page'

function fmtUptime(s: number | null): string {
  if (s == null) return '–'
  if (s < 90) return `${s}s`
  if (s < 5400) return `${Math.round(s / 60)} min`
  if (s < 172800) return `${Math.round(s / 3600)} h`
  return `${Math.round(s / 86400)} d`
}

export default function ProcessPage() {
  const t = useT()
  const { data, isPending } = useProcesses()
  const [creating, setCreating] = React.useState(false)
  const list = data ?? []
  return (
    <Page
      title={t('process.title')}
      description={t('process.desc')}
      actions={
        <Button size="sm" onClick={() => setCreating(true)} data-testid="process-new">
          <Plus /> <span className="max-sm:hidden">{t('process.new')}</span>
        </Button>
      }
    >
      <div className="grid gap-3">
        {isPending ? (
          <Skeleton className="h-28 rounded-lg" />
        ) : !list.length ? (
          <EmptyState
            icon={Terminal}
            title={t('process.empty')}
            description={t('process.emptyDesc')}
            action={
              <Button onClick={() => setCreating(true)}>
                <Plus /> {t('process.new')}
              </Button>
            }
            className="py-16"
          />
        ) : (
          list.map((p) => <ProcessCard key={p.id} p={p} />)
        )}
      </div>
      <NewProcessDialog open={creating} onOpenChange={setCreating} />
    </Page>
  )
}

function ProcessCard({ p }: { p: ProcessInfo }) {
  const t = useT()
  const act = useProcessAction()
  const del = useDeleteProcess()
  const unpublish = useUnpublishProcess()
  const [logs, setLogs] = React.useState(false)
  const [share, setShare] = React.useState(false)
  const running = p.state === 'running'
  return (
    <Card className="gap-3 p-4" data-testid="process-card">
      <div className="flex flex-wrap items-center gap-2">
        <StatusDot tone={running ? 'ok' : p.state === 'failed' ? 'error' : 'idle'} pulse={running} label={t(`process.state.${p.state}`)} />
        <span className="text-base font-medium">{p.name}</span>
        <Badge variant="outline">{t(`process.state.${p.state}`)}</Badge>
        {p.published && (
          <Badge variant="outline">
            <GlobeLock className="size-3" /> {t('process.protected')}
          </Badge>
        )}
        <div className="ml-auto flex flex-wrap items-center gap-1">
          {running ? (
            <>
              <Button variant="outline" size="sm" loading={act.isPending} onClick={() => act.mutate({ name: p.name, action: 'restart' })}>
                <RotateCw /> <span className="max-sm:hidden">{t('process.restart')}</span>
              </Button>
              <Button variant="outline" size="sm" loading={act.isPending} onClick={() => act.mutate({ name: p.name, action: 'stop' })}>
                <Square /> <span className="max-sm:hidden">{t('process.stop')}</span>
              </Button>
            </>
          ) : (
            <Button variant="outline" size="sm" loading={act.isPending} onClick={() => act.mutate({ name: p.name, action: 'start' })}>
              <Play /> <span className="max-sm:hidden">{t('process.start')}</span>
            </Button>
          )}
          <Button variant={logs ? 'secondary' : 'ghost'} size="sm" onClick={() => setLogs((v) => !v)}>
            <ScrollText /> <span className="max-sm:hidden">{t('process.logs')}</span>
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            className="text-destructive hover:text-destructive"
            aria-label={t('common.remove')}
            loading={del.isPending}
            onClick={async () => {
              if (await confirm({ title: t('process.deleteTitle', { name: p.name }), description: t('process.deleteDesc'), destructive: true, confirmText: t('common.remove') })) del.mutate(p.name)
            }}
          >
            <Trash2 />
          </Button>
        </div>
      </div>
      <div className="grid gap-1 text-[13px] text-muted-foreground">
        <span className="truncate font-mono" title={p.repo}>
          {p.repo}
        </span>
        <span className="truncate font-mono text-foreground/80" title={p.command}>
          $ {p.command}
        </span>
        <span className="flex flex-wrap gap-x-4 gap-y-0.5 tabular-nums">
          <span>
            {t('process.port')} {p.port}
          </span>
          <span>
            {t('process.uptime')} {fmtUptime(p.uptime_s)}
          </span>
          {p.cpu_pct != null && <span>CPU {p.cpu_pct}%</span>}
          {p.memory_mb != null && <span>RAM {Math.round(p.memory_mb)} MB</span>}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {p.published && p.url ? (
          <>
            <a href={p.url} target="_blank" rel="noopener noreferrer" className="inline-flex min-w-0 items-center gap-1.5 text-sm text-primary hover:underline">
              <ExternalLink className="size-3.5 shrink-0" /> <span className="truncate">{p.url}</span>
            </a>
            <Button variant="outline" size="sm" onClick={() => setShare(true)}>
              <Eye /> {t('process.password')}
            </Button>
            <Button variant="ghost" size="sm" loading={unpublish.isPending} onClick={() => unpublish.mutate(p.name)}>
              {t('process.unpublish')}
            </Button>
          </>
        ) : (
          <Button variant="outline" size="sm" onClick={() => setShare(true)}>
            <Globe /> {t('process.publish')}
          </Button>
        )}
      </div>
      {logs && <LogView name={p.name} />}
      <ShareDialog p={p} open={share} onOpenChange={setShare} />
    </Card>
  )
}

function LogView({ name }: { name: string }) {
  const t = useT()
  const { data = [] } = useProcessLogs(name, true)
  const ref = React.useRef<HTMLPreElement>(null)
  React.useEffect(() => {
    const el = ref.current
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 80) el.scrollTop = el.scrollHeight
  }, [data])
  return (
    <pre ref={ref} className="max-h-72 overflow-auto rounded-md border bg-muted/40 p-3 font-mono text-xs leading-relaxed break-all whitespace-pre-wrap" data-testid="process-logs">
      {data.length ? data.join('\n') : t('process.noLogs')}
    </pre>
  )
}

function NewProcessDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const t = useT()
  const create = useCreateProcess()
  const [name, setName] = React.useState('')
  const [repo, setRepo] = React.useState('')
  const [command, setCommand] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    create.mutate(
      { name: name.trim().toLowerCase(), repo: repo.trim(), command: command.trim() },
      {
        onSuccess: () => {
          onOpenChange(false)
          setName('')
          setRepo('')
          setCommand('')
        },
        onError: (err) => setError(errorMessage(err)),
      },
    )
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4" noValidate>
          <DialogHeader>
            <DialogTitle>{t('process.new')}</DialogTitle>
            <DialogDescription>{t('process.newDesc')}</DialogDescription>
          </DialogHeader>
          <FormField label={t('process.name')} hint={t('process.nameHint')}>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="my-app" maxLength={40} autoComplete="off" autoFocus />
          </FormField>
          <FormField label={t('process.repo')} hint={t('process.repoHint')}>
            <Input value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="/root/maxxing/projects/acme/repo" autoComplete="off" spellCheck={false} />
          </FormField>
          <FormField label={t('process.command')} hint={t('process.commandHint')}>
            <Input value={command} onChange={(e) => setCommand(e.target.value)} placeholder="npm run dev -- --port $PORT" autoComplete="off" spellCheck={false} />
          </FormField>
          {error && <p className="text-[13px] text-destructive">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={create.isPending} disabled={!name.trim() || !repo.trim() || !command.trim()}>
              {t('process.create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Publish (host optional), then the address and the password: loaded on request, copied, never in the list. */
function ShareDialog({ p, open, onOpenChange }: { p: ProcessInfo; open: boolean; onOpenChange: (v: boolean) => void }) {
  const t = useT()
  const publish = usePublishProcess()
  const [host, setHost] = React.useState('')
  const [creds, setCreds] = React.useState<ProcessCredentials | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  React.useEffect(() => {
    if (!open) {
      setCreds(null)
      setError(null)
      return
    }
    if (p.published) fetchProcessCredentials(p.name).then(setCreds).catch((e) => setError(errorMessage(e)))
  }, [open, p.published, p.name])
  const copy = async (text: string) => {
    if (await copyText(text)) toast.success(t('process.copied'))
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{p.published ? t('process.access') : t('process.publishTitle', { name: p.name })}</DialogTitle>
          <DialogDescription>{p.published ? t('process.accessDesc') : t('process.publishDesc')}</DialogDescription>
        </DialogHeader>
        {creds ? (
          <div className="grid gap-3 text-sm">
            <div className="grid gap-1">
              <span className="text-muted-foreground">URL</span>
              <CodeBlock inline code={creds.url} />
            </div>
            <div className="grid gap-1">
              <span className="text-muted-foreground">{t('process.user')}</span>
              <CodeBlock inline code={creds.user} />
            </div>
            <div className="grid gap-1">
              <span className="text-muted-foreground">{t('process.passwordLabel')}</span>
              <div className="flex items-center gap-2">
                <div className="min-w-0 flex-1">
                  <CodeBlock inline code={creds.password} />
                </div>
                <Button variant="outline" size="icon-sm" onClick={() => copy(creds.password)} aria-label={t('common.copy')}>
                  <Copy />
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <div className="grid gap-3">
            {!p.published && (
              <FormField label={t('process.hostLabel')} hint={t('process.hostHint')}>
                <Input value={host} onChange={(e) => setHost(e.target.value)} placeholder="app.example.com" autoComplete="off" spellCheck={false} />
              </FormField>
            )}
            {error && <p className="text-[13px] text-destructive">{error}</p>}
          </div>
        )}
        <DialogFooter>
          {creds ? (
            <Button onClick={() => onOpenChange(false)}>{t('common.close')}</Button>
          ) : !p.published ? (
            <Button
              loading={publish.isPending}
              onClick={() => {
                setError(null)
                publish.mutate({ name: p.name, host: host.trim() || undefined }, { onSuccess: setCreds, onError: (e) => setError(errorMessage(e)) })
              }}
            >
              <GlobeLock /> {t('process.publish')}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

import * as React from 'react'
import { KeyRound, PlugZap, Trash2 } from 'lucide-react'
import { useProviderKey, useProviderKeyRemove, useProviders, useProviderTest } from '@/lib/queries'
import { errorMessage } from '@/lib/api'
import type { ProviderInfo, ProviderTestResult } from '@/lib/types'
import { useT } from '@/i18n'
import { Badge, Button, CodeBlock, SecretInput, Skeleton, confirm } from '@/components/ui'
import { Callout } from '../common'

/** Codex CLI and Cursor CLI: installed? signed in? How to install, sign in or use an API key, and a real test call.
 *  (Claude Code has its own card above.) */
export function AgentsCard() {
  const t = useT()
  const { data, isLoading } = useProviders()
  if (isLoading || !data) return <Skeleton className="h-40 rounded-lg" />
  return (
    <div className="grid gap-4">
      {data.providers.filter((p) => p.id !== 'claude').map((p) => (
        <AgentRow key={p.id} p={p} />
      ))}
      <p className="text-[13px] text-muted-foreground">{t('agents.footer')}</p>
    </div>
  )
}

function AgentRow({ p }: { p: ProviderInfo }) {
  const t = useT()
  const test = useProviderTest()
  const save = useProviderKey()
  const remove = useProviderKeyRemove()
  const [key, setKey] = React.useState('')
  const [result, setResult] = React.useState<ProviderTestResult | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const ready = p.installed && p.signed_in === true
  const runTest = () =>
    test.mutate(p.id, { onSuccess: setResult, onError: (e) => setResult({ ok: false, ms: 0, error: errorMessage(e) }) })
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const v = key.trim()
    if (!v) return setError(t('claude.pasteFirst'))
    setError(null)
    save.mutate({ id: p.id, value: v }, { onSuccess: () => { setKey(''); runTest() }, onError: (err) => setError(errorMessage(err)) })
  }
  return (
    <div className="grid gap-3 rounded-lg border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{p.label}</span>
        {!p.installed ? (
          <Badge variant="outline">{t('sessions.provider.notInstalled')}</Badge>
        ) : ready ? (
          <Badge variant="success">{t('agents.ready')}</Badge>
        ) : (
          <Badge variant="outline">{t('sessions.provider.signedOut')}</Badge>
        )}
        {p.version && <span className="text-[13px] text-muted-foreground">{p.version}</span>}
        {p.key_set && <Badge variant="outline"><KeyRound className="size-3" /> {t('agents.keyStored')}</Badge>}
        {p.installed && (
          <Button variant="outline" size="sm" className="ml-auto" loading={test.isPending} onClick={runTest}>
            <PlugZap /> {t('claude.test')}
          </Button>
        )}
      </div>
      {!p.installed && p.install && (
        <div className="grid gap-2 text-sm">
          <span>{t('agents.installOnServer')}</span>
          <CodeBlock inline code={p.install} />
        </div>
      )}
      {p.installed && !ready && p.login && (
        <div className="grid gap-2 text-sm">
          <span>{t('agents.loginOnServer')}</span>
          <CodeBlock inline code={p.login} />
        </div>
      )}
      {p.installed && (
        <form onSubmit={submit} className="grid gap-2" noValidate>
          <span className="text-sm text-muted-foreground">{t('agents.orKey')}</span>
          <div className="flex flex-wrap items-start gap-2">
            <div className="min-w-0 flex-1 sm:max-w-sm">
              <SecretInput value={key} onChange={(e) => setKey(e.target.value)} placeholder={p.key_hint || ''} aria-label={t('agents.keyLabel', { provider: p.label })} />
            </div>
            <Button type="submit" size="sm" loading={save.isPending}>{t('agents.saveTest')}</Button>
            {p.key_set && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive"
                loading={remove.isPending}
                onClick={async () => {
                  if (await confirm({ title: t('agents.removeKeyTitle', { provider: p.label }), description: t('agents.removeKeyDesc'), destructive: true, confirmText: t('common.remove') })) remove.mutate(p.id)
                }}
              >
                <Trash2 /> {t('claude.remove')}
              </Button>
            )}
          </div>
          {error && <span className="text-[13px] text-destructive">{error}</span>}
        </form>
      )}
      {result && (
        <Callout tone={result.ok ? 'success' : 'error'} title={result.ok ? t('claude.testOk') : t('claude.testFailed')}>
          {result.ok ? t('agents.testOkDesc', { ms: Math.round(result.ms) }) : result.error}
        </Callout>
      )}
    </div>
  )
}

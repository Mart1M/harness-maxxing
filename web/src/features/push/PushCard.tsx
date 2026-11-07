import * as React from 'react'
import { BellRing, Smartphone, Trash2 } from 'lucide-react'
import { usePush, usePushCredentials, usePushCredentialsRemove, usePushDeviceRemove, usePushSettings, usePushTest } from '@/lib/queries'
import { errorMessage } from '@/lib/api'
import type { PushTurns } from '@/lib/types'
import { useT } from '@/i18n'
import { Badge, Button, FormField, Input, SecretInput, Select, Skeleton, Switch, confirm, toast } from '@/components/ui'
import { Callout, SettingRow } from '../common'

/** Push notifications to the iPhone app: the Apple key, what is sent, the registered phones. */
export function PushCard() {
  const t = useT()
  const { data, isLoading } = usePush()
  const save = usePushSettings()
  const test = usePushTest()
  const removeDevice = usePushDeviceRemove()
  if (isLoading || !data) return <Skeleton className="h-40 rounded-lg" />
  const { settings: s, credentials: c, devices } = data
  const ready = c.configured && devices.length > 0
  const runTest = () =>
    test.mutate(undefined, {
      onSuccess: (r) => (r.sent > 0 ? toast.success(t('push.testOk'), t('push.testOkDesc', { n: r.sent })) : toast.error(t('push.testFailed'), r.failed ? t('push.testFailedDesc') : t('push.testNone'))),
      onError: (e) => toast.error(t('push.testFailed'), errorMessage(e)),
    })
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center gap-2">
        {ready ? <Badge variant="success">{t('push.ready')}</Badge> : <Badge variant="outline">{c.configured ? t('push.noDevice') : t('push.noKey')}</Badge>}
        <Button variant="outline" size="sm" className="ml-auto" loading={test.isPending} disabled={!ready} onClick={runTest}>
          <BellRing /> {t('push.test')}
        </Button>
      </div>
      <div className="divide-y">
        <SettingRow label={t('push.enabled')} description={t('push.enabledDesc')} htmlFor="mx-push-enabled">
          <Switch id="mx-push-enabled" checked={s.enabled} onCheckedChange={(v) => save.mutate({ enabled: v })} />
        </SettingRow>
        <SettingRow label={t('push.turns')} description={t('push.turnsDesc')}>
          <Select
            value={s.turns}
            onValueChange={(v) => save.mutate({ turns: v as PushTurns })}
            disabled={!s.enabled}
            options={[
              { value: 'all', label: t('push.turns.all') },
              { value: 'notify', label: t('push.turns.notify') },
              { value: 'off', label: t('push.turns.off') },
            ]}
            className="w-56"
          />
        </SettingRow>
        <SettingRow label={t('push.errors')} description={t('push.errorsDesc')} htmlFor="mx-push-errors">
          <Switch id="mx-push-errors" checked={s.errors} disabled={!s.enabled} onCheckedChange={(v) => save.mutate({ errors: v })} />
        </SettingRow>
        <SettingRow label={t('push.crons')} description={t('push.cronsDesc')} htmlFor="mx-push-crons">
          <Switch id="mx-push-crons" checked={s.crons} disabled={!s.enabled} onCheckedChange={(v) => save.mutate({ crons: v })} />
        </SettingRow>
      </div>
      <div className="grid gap-2">
        <h3 className="text-sm font-medium">{t('push.devices')}</h3>
        {devices.length === 0 ? (
          <Callout tone="info">{t('push.devicesEmpty')}</Callout>
        ) : (
          devices.map((d) => (
            <div key={d.id} className="flex flex-wrap items-center gap-2 rounded-lg border p-3 text-sm">
              <Smartphone className="size-4 text-muted-foreground" />
              <span className="font-medium">{d.name || t('push.device')}</span>
              {d.env === 'sandbox' && <Badge variant="outline">{t('push.sandbox')}</Badge>}
              {d.last_error ? <span className="text-[13px] text-destructive">{d.last_error}</span> : d.last_ok ? <span className="text-[13px] text-muted-foreground">{t('push.lastOk', { at: new Date(d.last_ok * 1000).toLocaleString() })}</span> : null}
              <Button
                variant="ghost"
                size="icon"
                className="ml-auto"
                aria-label={t('push.removeDevice')}
                onClick={async () => {
                  if (await confirm({ title: t('push.removeTitle'), description: t('push.removeDesc'), confirmText: t('common.remove'), destructive: true })) removeDevice.mutate(d.id)
                }}
              >
                <Trash2 />
              </Button>
            </div>
          ))
        )}
      </div>
      <KeyForm />
    </div>
  )
}

function KeyForm() {
  const t = useT()
  const { data } = usePush()
  const save = usePushCredentials()
  const remove = usePushCredentialsRemove()
  const c = data?.credentials
  const [key, setKey] = React.useState('')
  const [keyId, setKeyId] = React.useState('')
  const [teamId, setTeamId] = React.useState('')
  const [topic, setTopic] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  React.useEffect(() => {
    if (!c) return
    setKeyId((v) => v || c.key_id)
    setTeamId((v) => v || c.team_id)
    setTopic((v) => v || c.topic)
  }, [c])
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    save.mutate(
      { key: key.trim() || undefined, key_id: keyId.trim(), team_id: teamId.trim(), topic: topic.trim() },
      { onSuccess: () => { setKey(''); toast.success(t('push.saved')) }, onError: (err) => setError(errorMessage(err)) },
    )
  }
  return (
    <form onSubmit={submit} className="grid gap-3 rounded-lg border p-4" noValidate>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-medium">{t('push.apple')}</h3>
        {c?.key_set && <Badge variant="outline">{t('push.keyStored')}</Badge>}
      </div>
      <p className="text-[13px] text-muted-foreground">{t('push.appleHelp')}</p>
      <FormField label={t('push.key')} hint={t('push.keyHint')}>
        <SecretInput value={key} onValueChange={setKey} placeholder={c?.key_set ? '••••••••' : '-----BEGIN PRIVATE KEY-----'} />
      </FormField>
      <div className="grid gap-3 sm:grid-cols-3">
        <FormField label={t('push.keyId')}>
          <Input value={keyId} onChange={(e) => setKeyId(e.target.value.toUpperCase())} placeholder="ABCDE12345" maxLength={10} />
        </FormField>
        <FormField label={t('push.teamId')}>
          <Input value={teamId} onChange={(e) => setTeamId(e.target.value.toUpperCase())} placeholder="TEAM123456" maxLength={10} />
        </FormField>
        <FormField label={t('push.topic')}>
          <Input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="com.example.app" />
        </FormField>
      </div>
      {error && <Callout tone="error">{error}</Callout>}
      <div className="flex gap-2">
        <Button type="submit" loading={save.isPending}>{t('common.save')}</Button>
        {c?.key_set && (
          <Button
            type="button"
            variant="outline"
            onClick={async () => {
              if (await confirm({ title: t('push.removeKeyTitle'), description: t('push.removeKeyDesc'), confirmText: t('common.remove'), destructive: true })) remove.mutate()
            }}
          >
            {t('push.removeKey')}
          </Button>
        )}
      </div>
    </form>
  )
}

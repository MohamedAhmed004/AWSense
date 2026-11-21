import { useMemo, useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { getResources } from '../services/api.js'
import { Async, Card, Pill, useAsync, money } from '../components/ui.jsx'

const BACKUP = {
  protected: { label: 'Protected', cls: 'bg-low/15 text-low ring-low/30' },
  stale: { label: 'Backup stale', cls: 'bg-med/15 text-med ring-med/30' },
  missing: { label: 'No recent backup', cls: 'bg-crit/15 text-crit ring-crit/30' },
  'n/a': { label: 'Not applicable', cls: 'bg-raised text-muted ring-line' },
}
const STATUS = { running: 'text-low', available: 'text-low', active: 'text-low', 'in-use': 'text-low', unattached: 'text-high' }
const input = 'rounded-md border border-line bg-ink px-3 py-2 text-sm text-text'

export default function Resources() {
  const state = useAsync(getResources)
  const [q, setQ] = useState('')
  const [type, setType] = useState('all')
  const [backup, setBackup] = useState('all')

  return (
    <Async state={state}>
      {(all) => {
        const rows = all.filter(
          (r) =>
            (type === 'all' || r.type === type) &&
            (backup === 'all' || r.backup === backup) &&
            `${r.name} ${r.id} ${r.region}`.toLowerCase().includes(q.toLowerCase()),
        )
        const gaps = all.filter((r) => r.backup === 'missing' || r.backup === 'stale').length
        return (
          <div className="space-y-5">
            {gaps > 0 && (
              <div className="flex items-start gap-3 rounded-lg border border-high/30 bg-high/10 p-4 text-sm" role="status">
                <AlertTriangle size={18} className="mt-0.5 shrink-0 text-high" aria-hidden />
                <p>{gaps} resources have a backup gap. Back them up before changing or deleting them.</p>
              </div>
            )}
            <Card
              title={`Resource inventory (${rows.length})`}
              aside={
                <div className="flex flex-wrap gap-2">
                  <input className={input} placeholder="Search name, ID or region" aria-label="Search resources" value={q} onChange={(e) => setQ(e.target.value)} />
                  <select className={input} aria-label="Filter by type" value={type} onChange={(e) => setType(e.target.value)}>
                    <option value="all">All types</option>
                    {['ec2', 'ebs', 'rds', 's3'].map((t) => <option key={t} value={t}>{t.toUpperCase()}</option>)}
                  </select>
                  <select className={input} aria-label="Filter by backup status" value={backup} onChange={(e) => setBackup(e.target.value)}>
                    <option value="all">All backup states</option>
                    {Object.entries(BACKUP).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                  </select>
                </div>
              }
            >
              <div className="-m-5 overflow-x-auto">
                <table className="w-full min-w-[860px] text-left text-sm">
                  <thead className="text-muted">
                    <tr className="border-b border-line">
                      {['Resource', 'Type', 'Region', 'Status', 'CPU', 'Backup', 'Monthly cost', 'Finding'].map((h) => (
                        <th key={h} className="px-5 py-3 font-medium">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.id} className="border-b border-line/60 last:border-0 hover:bg-raised/40">
                        <td className="px-5 py-3"><p className="font-medium">{r.name}</p><p className="text-xs text-muted">{r.id}</p></td>
                        <td className="px-5 py-3">{r.type.toUpperCase()}</td>
                        <td className="px-5 py-3">{r.region}</td>
                        <td className={`px-5 py-3 ${STATUS[r.status]}`}>{r.status}</td>
                        <td className="px-5 py-3">
                          {r.cpu == null ? <span className="text-muted">n/a</span> : (
                            <div className="flex items-center gap-2">
                              <div className="h-1.5 w-16 rounded-full bg-raised"><div className={`h-1.5 rounded-full ${r.cpu > 85 ? 'bg-crit' : r.cpu < 10 ? 'bg-med' : 'bg-accent'}`} style={{ width: `${r.cpu}%` }} /></div>
                              {r.cpu}%
                            </div>
                          )}
                        </td>
                        <td className="px-5 py-3">
                          <Pill className={BACKUP[r.backup].cls}>{BACKUP[r.backup].label}</Pill>
                          {r.lastBackup && <p className="mt-1 text-xs text-muted">Last: {r.lastBackup}</p>}
                        </td>
                        <td className="px-5 py-3">{money(r.monthlyCost)}</td>
                        <td className="max-w-xs px-5 py-3 text-muted">{r.finding || '—'}</td>
                      </tr>
                    ))}
                    {rows.length === 0 && (
                      <tr><td colSpan={8} className="px-5 py-8 text-center text-muted">No resources match these filters. Clear the search or choose All types.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        )
      }}
    </Async>
  )
}

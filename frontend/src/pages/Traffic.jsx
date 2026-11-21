import { ResponsiveContainer, ComposedChart, Area, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid } from 'recharts'
import { getTraffic } from '../services/api.js'
import { Async, Card, Pill, Stat, useAsync, compact, money, chartTooltip } from '../components/ui.jsx'

export default function Traffic() {
  const state = useAsync(getTraffic)
  return (
    <Async state={state}>
      {(d) => (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-3">
            <Stat label="Requests in 24 hours" value={compact(d.totalRequests)} note="About 5K per hour is normal" />
            <Stat label="Share from bots" value={`${Math.round(d.botShare * 100)}%`} valueClass="text-high" note="Across 3 flagged IP ranges" />
            <Stat label="Extra cost from bot load" value={money(d.costImpact)} valueClass="text-crit" note="Scaling and data transfer today" />
          </div>

          <Card title="Request volume against CPU and cost">
            <div className="h-80" role="img" aria-label="Hourly requests, CPU percentage and hourly cost over 24 hours">
              <ResponsiveContainer>
                <ComposedChart data={d.timeline} margin={{ left: -10, right: 8, top: 8 }}>
                  <CartesianGrid stroke="#26374D" vertical={false} />
                  <XAxis dataKey="time" stroke="#8B9BB0" fontSize={12} interval={2} tickLine={false} />
                  <YAxis yAxisId="r" stroke="#8B9BB0" fontSize={12} tickFormatter={compact} tickLine={false} axisLine={false} />
                  <YAxis yAxisId="p" orientation="right" stroke="#8B9BB0" fontSize={12} tickFormatter={(v) => `${v}`} tickLine={false} axisLine={false} />
                  <Tooltip {...chartTooltip} />
                  <Legend wrapperStyle={{ fontSize: 13 }} />
                  <Area yAxisId="r" type="monotone" dataKey="requests" name="Requests per hour" stroke="#5AA9FF" fill="#5AA9FF" fillOpacity={0.15} strokeWidth={2} />
                  <Line yAxisId="p" type="monotone" dataKey="cpu" name="CPU %" stroke="#F29A4B" dot={false} strokeWidth={2} />
                  <Line yAxisId="p" type="monotone" dataKey="cost" name="Cost per hour ($)" stroke="#F0645A" dot={false} strokeWidth={2} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card title="Endpoint patterns">
            <div className="-m-5 overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="text-muted">
                  <tr className="border-b border-line">
                    {['Endpoint', 'Requests', 'Source', 'User agent', 'Verdict'].map((h) => <th key={h} className="px-5 py-3 font-medium">{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {d.patterns.map((p) => (
                    <tr key={p.endpoint} className="border-b border-line/60 last:border-0">
                      <td className="px-5 py-3 font-medium">{p.endpoint}</td>
                      <td className="px-5 py-3">{compact(p.requests)}</td>
                      <td className="px-5 py-3">{p.ip}</td>
                      <td className="px-5 py-3 text-muted">{p.userAgent}</td>
                      <td className="px-5 py-3">
                        {p.bot
                          ? <Pill className="bg-high/15 text-high ring-high/30">Bot, {Math.round(p.confidence * 100)}% sure</Pill>
                          : <Pill className="bg-low/15 text-low ring-low/30">Normal users</Pill>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </Async>
  )
}

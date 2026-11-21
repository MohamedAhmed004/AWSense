import { ResponsiveContainer, ComposedChart, Line, Area, XAxis, YAxis, Tooltip, Legend, CartesianGrid } from 'recharts'
import { getOverview } from '../services/api.js'
import { Async, Card, Stat, SEVERITY_TEXT, SEVERITY_BAR, useAsync, money, chartTooltip } from '../components/ui.jsx'

export default function Overview() {
  const state = useAsync(getOverview)
  return (
    <Async state={state}>
      {(d) => {
        const total = Object.values(d.activeAlerts).reduce((a, b) => a + b, 0)
        return (
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Stat label="Cloud health" value={`${d.healthScore}/100`} note="Down from 91 last week" />
              <Stat label="Active alerts" value={total} note={`${d.activeAlerts.CRITICAL} critical, ${d.activeAlerts.HIGH} high`} />
              <Stat label="Monthly savings available" value={money(d.monthlySavings)} note="From pending recommendations" valueClass="text-low" />
              <Stat label="Risk level" value={d.riskLevel[0] + d.riskLevel.slice(1).toLowerCase()} valueClass={SEVERITY_TEXT[d.riskLevel]} note="Driven by ALT-1042" />
            </div>

            <div className="grid gap-6 xl:grid-cols-3">
              <Card title="Daily cost and CPU, last 30 days" className="xl:col-span-2">
                <div className="h-72" role="img" aria-label="Daily cost compared with expected cost, plus average CPU">
                  <ResponsiveContainer>
                    <ComposedChart data={d.trend} margin={{ left: -10, right: 8, top: 8 }}>
                      <CartesianGrid stroke="#26374D" vertical={false} />
                      <XAxis dataKey="date" stroke="#8B9BB0" fontSize={12} interval={4} tickLine={false} />
                      <YAxis yAxisId="c" stroke="#8B9BB0" fontSize={12} tickFormatter={(v) => `$${v}`} tickLine={false} axisLine={false} />
                      <YAxis yAxisId="p" orientation="right" stroke="#8B9BB0" fontSize={12} tickFormatter={(v) => `${v}%`} tickLine={false} axisLine={false} domain={[0, 100]} />
                      <Tooltip {...chartTooltip} />
                      <Legend wrapperStyle={{ fontSize: 13 }} />
                      <Area yAxisId="c" type="monotone" dataKey="cost" name="Cost" stroke="#5AA9FF" fill="#5AA9FF" fillOpacity={0.15} strokeWidth={2} />
                      <Line yAxisId="c" type="monotone" dataKey="expected" name="Expected cost" stroke="#8B9BB0" strokeDasharray="4 4" dot={false} />
                      <Line yAxisId="p" type="monotone" dataKey="cpu" name="Avg CPU" stroke="#F29A4B" dot={false} strokeWidth={2} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </Card>

              <Card title="Alerts by severity">
                <ul className="space-y-4">
                  {Object.entries(d.activeAlerts).map(([level, n]) => (
                    <li key={level}>
                      <div className="mb-1 flex justify-between text-sm">
                        <span>{level[0] + level.slice(1).toLowerCase()}</span>
                        <span className={SEVERITY_TEXT[level]}>{n}</span>
                      </div>
                      <div className="h-2 rounded-full bg-raised">
                        <div className={`h-2 rounded-full ${SEVERITY_BAR[level]}`} style={{ width: `${total ? (n / total) * 100 : 0}%` }} />
                      </div>
                    </li>
                  ))}
                </ul>
              </Card>
            </div>
          </div>
        )
      }}
    </Async>
  )
}

const labels = Array.from({ length: 30 }, (_, i) => {
  const d = new Date(Date.UTC(2026, 9, 23 + i))
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })
})

// 27 steady days, then a cost and CPU jump from the burst-fleet incident
const trend = labels.map((date, i) => {
  const wave = Math.sin(i / 2.2)
  const spike = i >= 28 ? (i === 28 ? 31 : 84) : 0
  return {
    date,
    expected: +(8.2 + wave * 0.4).toFixed(2),
    cost: +(8.2 + wave * 0.6 + spike).toFixed(2),
    cpu: Math.round(24 + wave * 4 + (i >= 28 ? (i === 28 ? 28 : 51) : 0)),
  }
})

export const overview = {
  healthScore: 72,
  riskLevel: 'HIGH',
  monthlySavings: 1842,
  activeAlerts: { CRITICAL: 1, HIGH: 2, MEDIUM: 1, LOW: 0 },
  trend,
}

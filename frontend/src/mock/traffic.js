const spike = { 12: 90000, 13: 310000, 14: 420000, 15: 480000, 16: 450000, 17: 380000, 18: 190000, 19: 60000 }
let running = 0
const timeline = Array.from({ length: 24 }, (_, h) => {
  const requests = Math.round(5000 + Math.sin(h / 3) * 1500 + (spike[h] || 0))
  const cpu = Math.min(97, Math.round(14 + requests / 5600))
  const cost = +(0.32 + (spike[h] || 0) / 9000).toFixed(2)
  running += cost
  return { time: `${String(h).padStart(2, '0')}:00`, requests, cpu, cost, cumulativeCost: +running.toFixed(2) }
})

export const traffic = {
  totalRequests: timeline.reduce((s, p) => s + p.requests, 0),
  botShare: 0.91,
  costImpact: 318,
  timeline,
  patterns: [
    { endpoint: '/api/products?page=*', requests: 1120000, ip: '45.134.x.x range', userAgent: 'python-requests/2.31', bot: true, confidence: 0.97 },
    { endpoint: '/api/search?q=*', requests: 820000, ip: '185.220.x.x range', userAgent: 'Go-http-client/1.1', bot: true, confidence: 0.94 },
    { endpoint: '/api/prices/export', requests: 310000, ip: '91.92.x.x range', userAgent: 'curl/8.4', bot: true, confidence: 0.88 },
    { endpoint: '/checkout', requests: 9400, ip: 'Many addresses', userAgent: 'Browsers', bot: false, confidence: 0.12 },
    { endpoint: '/login', requests: 6100, ip: 'Many addresses', userAgent: 'Browsers', bot: false, confidence: 0.09 },
  ],
}

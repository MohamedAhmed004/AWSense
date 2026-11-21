// Deterministic helpers so fixtures look the same on every load.
export function rng(seed = 7) {
  let a = seed
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
const HOUR = 3600 * 1000
export const hoursAgo = (h) => new Date(Date.now() - h * HOUR).toISOString()
export const minutesAfter = (iso, m) => new Date(new Date(iso).getTime() + m * 60000).toISOString()
export const dayLabel = (daysBack) => {
  const d = new Date(Date.now() - daysBack * 24 * HOUR)
  return d.toISOString().slice(0, 10)
}
export const round = (n, d = 1) => Math.round(n * 10 ** d) / 10 ** d

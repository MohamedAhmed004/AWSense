import * as mock from '../mock'
import {
  adaptAlerts,
  adaptOverview,
  adaptRecommendationAction,
  adaptRecommendations,
  adaptResources,
  adaptTraffic,
} from './adapters.js'

// Flip VITE_USE_MOCK=false in .env to call the FastAPI backend
const USE_MOCK = (import.meta.env.VITE_USE_MOCK ?? 'true') !== 'false'
const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'

const local = (value, ms = 250) =>
  new Promise((resolve) => setTimeout(() => resolve(structuredClone(value)), ms))

async function http(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = ''
    try {
      const data = await res.json()
      const d = data?.detail
      if (typeof d === 'string') detail = `: ${d}`
      else if (Array.isArray(d)) detail = `: ${d.map((x) => x?.msg).filter(Boolean).join('; ')}`
    } catch {
      // response had no JSON body
    }
    throw new Error(`Request to ${path} failed (${res.status})${detail}`)
  }
  return res.json()
}

export const getOverview = () =>
  USE_MOCK ? local(mock.overview) : http('/overview').then(adaptOverview)
export const getResources = () =>
  USE_MOCK ? local(mock.resources) : http('/resources').then(adaptResources)
export const getAlerts = () =>
  USE_MOCK ? local(mock.alerts) : http('/alerts').then(adaptAlerts)
export const getTraffic = () =>
  USE_MOCK ? local(mock.traffic) : http('/traffic').then(adaptTraffic)
export const getRecommendations = () =>
  USE_MOCK ? local(mock.recommendations) : http('/recommendations').then(adaptRecommendations)

// action: 'pending' | 'approved' | 'dismissed'
export const actOnRecommendation = (id, action) =>
  USE_MOCK
    ? local({ id, state: action })
    : http(`/recommendations/${id}/action`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      }).then(adaptRecommendationAction)

// status: 'open' | 'investigating' | 'resolved' | 'dismissed'
export const updateAlertStatus = (id, status) => {
  if (USE_MOCK) {
    const found = mock.alerts.find((x) => x.id === id)
    if (!found) throw new Error(`Alert ${id} not found`)
    found.status = status
    return local({ id, status })
  }
  return http(`/alerts/${encodeURIComponent(id)}/status`, {
    method: 'POST',
    body: JSON.stringify({ status }),
  })
}

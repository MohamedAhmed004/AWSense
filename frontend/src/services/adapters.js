const VALID_SEVERITIES = new Set(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'])

const BACKUP_MAP = {
  protected: 'protected',
  outdated: 'stale',
  stale: 'stale',
  missing: 'missing',
  not_applicable: 'n/a',
  'n/a': 'n/a',
}

const CONFIDENCE_MAP = {
  high: 0.9,
  medium: 0.7,
  low: 0.5,
}

const BREAKDOWN_WEIGHTS = {
  ml: 0.3,
  iam: 0.25,
  resource: 0.2,
  cost: 0.15,
  traffic: 0.1,
}

const clamp = (value, min, max) => Math.min(max, Math.max(min, value))

const round = (value, decimals = 2) => {
  const factor = 10 ** decimals
  return Math.round((Number(value) || 0) * factor) / factor
}

function normalizeSeverity(value, fallback = 'LOW') {
  const upper = String(value ?? '').trim().toUpperCase()
  return VALID_SEVERITIES.has(upper) ? upper : fallback
}

function toIsoTimestamp(value) {
  if (value == null || value === '') return '1970-01-01T00:00:00.000Z'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '1970-01-01T00:00:00.000Z' : parsed.toISOString()
}

function formatTrendDate(value) {
  if (value == null || value === '') return ''
  const raw = String(value).trim()
  const parsed = /^\d{4}-\d{2}-\d{2}$/.test(raw) ? new Date(`${raw}T00:00:00Z`) : new Date(raw)
  if (Number.isNaN(parsed.getTime())) return raw
  return parsed.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
}

function formatLastBackup(value) {
  if (value == null || value === '') return null
  const raw = String(value).trim()
  if (!/^\d{4}-\d{2}-\d{2}/.test(raw)) return raw
  const parsed = new Date(raw)
  if (Number.isNaN(parsed.getTime())) return raw
  const day = parsed.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
  const hhmm = parsed.toISOString().slice(11, 16)
  return `${day}, ${hhmm} UTC`
}

function median(values) {
  if (!values.length) return 0
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid]
}

function toScore100(value, isUnitRatio = false) {
  if (value == null || value === '') return 0
  const num = Number(value)
  if (Number.isNaN(num)) return 0
  if ((isUnitRatio && num <= 1) || (num > 0 && num <= 1)) {
    return Math.round(clamp(num * 100, 0, 100))
  }
  return Math.round(clamp(num, 0, 100))
}

function inferEventSource(eventId) {
  const id = String(eventId ?? '').toLowerCase()
  if (id.startsWith('ct')) return 'CloudTrail'
  if (id.startsWith('cw')) return 'CloudWatch'
  if (id.startsWith('ce') || id.startsWith('cost')) return 'Cost Explorer'
  if (id.startsWith('tr') || id.startsWith('waf') || id.startsWith('bot')) return 'Traffic logs'
  if (id.startsWith('bk') || id.startsWith('backup')) return 'AWS Backup'
  return 'Telemetry'
}

function deriveResourceFinding(resource, type, status, cpu, backup) {
  const explicit = resource?.finding ?? resource?.metadata?.finding
  if (explicit != null && explicit !== '') return String(explicit)
  if (backup === 'missing') return 'No recent backup or snapshot'
  if (backup === 'stale') return 'Backup snapshot is outdated'
  if ((type === 'ec2' || type === 'rds') && cpu != null && cpu < 15) {
    return `Underutilized: ${cpu}% average CPU`
  }
  if (
    type === 'ebs' &&
    (status === 'available' || status === 'unattached' || resource?.metadata?.attached === false)
  ) {
    return 'Unattached EBS volume'
  }
  return null
}

function normalizeConfidence(value) {
  if (typeof value === 'number' && !Number.isNaN(value)) {
    return round(clamp(value > 1 ? value / 100 : value, 0, 1), 2)
  }
  const key = String(value ?? '').trim().toLowerCase()
  if (key in CONFIDENCE_MAP) return CONFIDENCE_MAP[key]
  const parsed = Number(key)
  if (!Number.isNaN(parsed) && key !== '') {
    return round(clamp(parsed > 1 ? parsed / 100 : parsed, 0, 1), 2)
  }
  return 0.5
}

export function adaptOverview(raw) {
  const data = raw ?? {}
  const alertsRaw = data.active_alerts ?? {}
  const rawTrend = Array.isArray(data.cost_usage_trend) ? data.cost_usage_trend : []
  const costs = rawTrend.map((p) => Number(p?.daily_cost_usd ?? p?.cost ?? 0) || 0)
  const baselineCost = round(median(costs), 2)

  return {
    healthScore: Math.round(clamp(Number(data.health_score ?? 0) || 0, 0, 100)),
    riskLevel: normalizeSeverity(data.risk_level, 'LOW'),
    monthlySavings: round(Number(data.total_monthly_savings_usd ?? 0) || 0, 2),
    activeAlerts: {
      CRITICAL: Number(alertsRaw.critical ?? alertsRaw.CRITICAL ?? 0) || 0,
      HIGH: Number(alertsRaw.high ?? alertsRaw.HIGH ?? 0) || 0,
      MEDIUM: Number(alertsRaw.medium ?? alertsRaw.MEDIUM ?? 0) || 0,
      LOW: Number(alertsRaw.low ?? alertsRaw.LOW ?? 0) || 0,
    },
    trend: rawTrend.map((point) => {
      const hasExpected = point?.expected_cost_usd != null || point?.expected != null
      return {
        date: formatTrendDate(point?.date),
        expected: hasExpected
          ? round(Number(point.expected_cost_usd ?? point.expected) || 0, 2)
          : baselineCost,
        cost: round(Number(point?.daily_cost_usd ?? point?.cost ?? 0) || 0, 2),
        cpu: Math.round(Number(point?.avg_cpu_pct ?? point?.cpu ?? 0) || 0),
      }
    }),
  }
}

export function adaptResources(raw) {
  const list = Array.isArray(raw) ? raw : Array.isArray(raw?.resources) ? raw.resources : []
  return list.map((r) => {
    const id = String(r?.resource_id ?? r?.id ?? '')
    const type = String(r?.resource_type ?? r?.type ?? 'ec2').toLowerCase()
    const status = String(r?.status ?? 'unknown').toLowerCase()
    const rawUtil = r?.utilization_pct ?? r?.cpu
    const cpu =
      type === 'ebs' || type === 's3' || rawUtil == null
        ? null
        : round(clamp(Number(rawUtil) || 0, 0, 100), 1)
    const rawBackup = String(r?.backup_status ?? r?.backup ?? 'not_applicable')
      .trim()
      .toLowerCase()
    const backup = BACKUP_MAP[rawBackup] ?? 'n/a'

    return {
      id,
      name: r?.name || id,
      type,
      region: r?.region || 'unknown',
      status,
      cpu,
      backup,
      lastBackup: formatLastBackup(r?.last_backup_at ?? r?.lastBackup),
      monthlyCost: round(Number(r?.monthly_cost_usd ?? r?.monthlyCost ?? 0) || 0, 2),
      finding: deriveResourceFinding(r, type, status, cpu, backup),
    }
  })
}

export function adaptAlerts(raw) {
  const list = Array.isArray(raw) ? raw : Array.isArray(raw?.alerts) ? raw.alerts : []
  return list.map((a) => {
    const timestamp = toIsoTimestamp(a?.created_at ?? a?.timestamp)
    const sb = a?.signal_breakdown ?? {}
    const eventTime = timestamp.slice(11, 16)

    const breakdown = Array.isArray(a?.breakdown)
      ? a.breakdown
      : [
          {
            key: 'ml',
            label: 'Behavior anomaly (ML)',
            value: toScore100(a?.ml_score ?? sb.ml_score, true),
            weight: BREAKDOWN_WEIGHTS.ml,
          },
          {
            key: 'iam',
            label: 'IAM risk',
            value: toScore100(sb.iam_risk, false),
            weight: BREAKDOWN_WEIGHTS.iam,
          },
          {
            key: 'resource',
            label: 'Resource impact',
            value: toScore100(sb.resource_impact, false),
            weight: BREAKDOWN_WEIGHTS.resource,
          },
          {
            key: 'cost',
            label: 'Cost impact',
            value: toScore100(sb.cost_impact, false),
            weight: BREAKDOWN_WEIGHTS.cost,
          },
          {
            key: 'traffic',
            label: 'Traffic anomaly',
            value: toScore100(sb.traffic_anomaly, false),
            weight: BREAKDOWN_WEIGHTS.traffic,
          },
        ]

    const events = Array.isArray(a?.events)
      ? a.events.map((e) => ({
          time: String(e?.time ?? eventTime),
          text: String(e?.text ?? ''),
          source: String(e?.source ?? 'Telemetry'),
        }))
      : (Array.isArray(a?.correlated_event_ids) ? a.correlated_event_ids : []).map((eid) => ({
          time: eventTime,
          text: a?.resource_id
            ? `Correlated signal ${eid} (${a.resource_id})`
            : `Correlated signal ${eid}`,
          source: inferEventSource(eid),
        }))

    const steps = Array.isArray(a?.recommended_actions)
      ? a.recommended_actions.map(String)
      : Array.isArray(a?.steps)
        ? a.steps.map(String)
        : []

    return {
      id: String(a?.alert_id ?? a?.id ?? ''),
      title: String(a?.title ?? ''),
      severity: normalizeSeverity(a?.severity, 'LOW'),
      riskScore: Math.round(clamp(Number(a?.risk_score ?? a?.riskScore ?? 0) || 0, 0, 100)),
      status: String(a?.status ?? 'open').toLowerCase(),
      timestamp,
      breakdown,
      events,
      summary: String(a?.summary ?? a?.ai_summary ?? ''),
      steps,
    }
  })
}

export function adaptTraffic(raw) {
  const data = raw ?? {}
  const rawTimeline = Array.isArray(data.request_rate_timeline) ? data.request_rate_timeline : []
  const botFlags = data.bot_flags ?? {}

  const timelineRequestsTotal = rawTimeline.reduce(
    (sum, p) => sum + (Number(p?.total_requests ?? 0) || 0),
    0,
  )
  const totalRequests =
    botFlags.total_requests_24h != null
      ? Number(botFlags.total_requests_24h) || 0
      : timelineRequestsTotal

  let botShare = 0
  if (botFlags.bot_traffic_pct != null) {
    botShare = round(clamp((Number(botFlags.bot_traffic_pct) || 0) / 100, 0, 1), 4)
  } else if (totalRequests > 0) {
    botShare = round(
      clamp((Number(botFlags.flagged_bot_requests_24h ?? 0) || 0) / totalRequests, 0, 1),
      4,
    )
  }

  const costImpact = round(Number(data.cost_impact?.estimated_daily_cost_usd ?? 0) || 0, 2)
  const totalEgress = rawTimeline.reduce(
    (sum, p) => sum + (Number(p?.network_out_gb ?? 0) || 0),
    0,
  )

  let runningCost = 0
  const timeline = rawTimeline.map((point) => {
    const requests = Number(point?.total_requests ?? 0) || 0
    const egress = Number(point?.network_out_gb ?? 0) || 0
    const share =
      totalEgress > 0
        ? egress / totalEgress
        : timelineRequestsTotal > 0
          ? requests / timelineRequestsTotal
          : rawTimeline.length > 0
            ? 1 / rawTimeline.length
            : 0
    const cost = round(costImpact * share, 2)
    runningCost = round(runningCost + cost, 2)

    const ts = point?.timestamp
    const parsedTs = ts != null ? new Date(ts) : null
    const time =
      parsedTs && !Number.isNaN(parsedTs.getTime())
        ? parsedTs.toISOString().slice(11, 16)
        : String(ts ?? '')

    return {
      time,
      requests,
      cpu: Math.round(Number(point?.avg_cpu_pct ?? 0) || 0),
      cost,
      cumulativeCost: runningCost,
    }
  })

  const rawEndpoints = Array.isArray(data.suspicious_endpoints) ? data.suspicious_endpoints : []
  const byEndpoint = new Map()
  for (const ep of rawEndpoints) {
    const endpoint = String(ep?.endpoint ?? '/')
    const requests = Number(ep?.request_count_24h ?? ep?.requests ?? 0) || 0
    const bot = Boolean(ep?.bot_flagged ?? ep?.bot)
    const confidence = round(clamp((Number(ep?.bot_share_pct ?? 0) || 0) / 100, 0, 1), 4)
    const ip =
      ep?.source_ip ||
      ep?.ip ||
      ep?.pattern_reason ||
      (bot
        ? `${botFlags.suspicious_ips_count || 'Multiple'} suspicious IPs`
        : 'Many addresses')
    const userAgent = ep?.top_user_agent || ep?.user_agent || ep?.userAgent || 'Unknown'

    const prev = byEndpoint.get(endpoint)
    if (prev) {
      prev.requests += requests
      prev.bot = prev.bot || bot
      prev.confidence = Math.max(prev.confidence, confidence)
    } else {
      byEndpoint.set(endpoint, { endpoint, requests, ip, userAgent, bot, confidence })
    }
  }

  return {
    totalRequests,
    botShare,
    costImpact,
    timeline,
    patterns: Array.from(byEndpoint.values()),
  }
}

export function adaptRecommendations(raw) {
  const list = Array.isArray(raw)
    ? raw
    : Array.isArray(raw?.recommendations)
      ? raw.recommendations
      : []

  return list.map((r) => ({
    id: String(r?.recommendation_id ?? r?.id ?? ''),
    resourceId: String(r?.resource_id ?? r?.resourceId ?? ''),
    category: String(r?.category ?? 'cost').toLowerCase(),
    title: String(r?.title ?? ''),
    action: String(r?.action ?? ''),
    estimatedSavings: round(
      Number(r?.estimated_monthly_savings_usd ?? r?.estimatedSavings ?? 0) || 0,
      2,
    ),
    confidence: normalizeConfidence(r?.confidence),
    state: String(r?.state ?? 'pending').toLowerCase(),
  }))
}

export function adaptRecommendationAction(raw) {
  const item = raw?.recommendation ?? raw ?? {}
  const result = {
    id: String(item.recommendation_id ?? item.id ?? ''),
    state: String(item.state ?? 'pending').toLowerCase(),
  }
  if (raw?.previous_state != null) {
    result.previousState = String(raw.previous_state).toLowerCase()
  }
  if (raw?.message != null) {
    result.message = String(raw.message)
  }
  return result
}

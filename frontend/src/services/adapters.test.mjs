import test from 'node:test'
import assert from 'node:assert/strict'

import {
  adaptAlerts,
  adaptOverview,
  adaptRecommendationAction,
  adaptRecommendations,
  adaptResources,
  adaptTraffic,
} from './adapters.js'

test('adaptOverview maps KPIs, 4-key activeAlerts, and median expected trend', () => {
  const raw = {
    health_score: 64.4,
    risk_level: 'high',
    total_monthly_savings_usd: 318.4,
    monthly_spend_usd: 1842.75,
    active_alerts: { total: 4, critical: 1, high: 2, medium: 1, low: 0 },
    monitored_resources: 6,
    unprotected_resources: 3,
    cost_usage_trend: [
      { date: '2026-11-15', daily_cost_usd: 48.2, avg_cpu_pct: 28.4, request_count: 142000 },
      { date: '2026-11-16', daily_cost_usd: 49.1, avg_cpu_pct: 29.1, request_count: 148500 },
      { date: '2026-11-17', daily_cost_usd: 47.8, avg_cpu_pct: 27.6, request_count: 139800 },
      { date: '2026-11-18', daily_cost_usd: 50.4, avg_cpu_pct: 30.2, request_count: 155400 },
      { date: '2026-11-19', daily_cost_usd: 312.9, avg_cpu_pct: 84.2, request_count: 2410000 },
    ],
  }

  const adapted = adaptOverview(raw)
  assert.equal(adapted.healthScore, 64)
  assert.equal(adapted.riskLevel, 'HIGH')
  assert.equal(adapted.monthlySavings, 318.4)
  assert.deepEqual(adapted.activeAlerts, { CRITICAL: 1, HIGH: 2, MEDIUM: 1, LOW: 0 })
  assert.equal('total' in adapted.activeAlerts, false)

  assert.equal(adapted.trend.length, 5)
  assert.deepEqual(adapted.trend[0], {
    date: 'Nov 15',
    expected: 49.1,
    cost: 48.2,
    cpu: 28,
  })
  assert.equal(adapted.trend[4].cost, 312.9)
  assert.equal(adapted.trend[4].cpu, 84)
})

test('adaptOverview handles empty/null input safely', () => {
  assert.deepEqual(adaptOverview(null), {
    healthScore: 0,
    riskLevel: 'LOW',
    monthlySavings: 0,
    activeAlerts: { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 },
    trend: [],
  })
})

test('adaptResources maps backup statuses, storage cpu nulling, timestamps, and findings', () => {
  const raw = {
    summary: { total: 4 },
    resources: [
      {
        resource_id: 'i-low-cpu',
        name: 'batch-worker',
        resource_type: 'ec2',
        region: 'us-east-1',
        status: 'running',
        utilization_pct: 6.8,
        backup_status: 'not_applicable',
        last_backup_at: null,
        monthly_cost_usd: 168.0,
        metadata: {},
      },
      {
        resource_id: 'vol-orphan',
        name: 'old-vol',
        resource_type: 'ebs',
        region: 'us-east-1',
        status: 'available',
        utilization_pct: 0.0,
        backup_status: 'missing',
        last_backup_at: null,
        monthly_cost_usd: 48.0,
        metadata: { attached: false },
      },
      {
        resource_id: 'db-orders',
        name: 'orders-rds',
        resource_type: 'rds',
        region: 'us-east-1',
        status: 'available',
        utilization_pct: 54.3,
        backup_status: 'outdated',
        last_backup_at: '2026-11-10T03:00:00Z',
        monthly_cost_usd: 412.25,
        metadata: {},
      },
      {
        resource_id: 's3-audit',
        name: 'audit-archive',
        resource_type: 's3',
        region: 'us-east-1',
        status: 'active',
        utilization_pct: 62.0,
        backup_status: 'protected',
        last_backup_at: '2026-11-21T00:00:00Z',
        monthly_cost_usd: 177.0,
        metadata: { finding: 'Custom metadata finding' },
      },
    ],
  }

  const adapted = adaptResources(raw)
  assert.equal(adapted.length, 4)

  assert.deepEqual(adapted[0], {
    id: 'i-low-cpu',
    name: 'batch-worker',
    type: 'ec2',
    region: 'us-east-1',
    status: 'running',
    cpu: 6.8,
    backup: 'n/a',
    lastBackup: null,
    monthlyCost: 168,
    finding: 'Underutilized: 6.8% average CPU',
  })

  assert.equal(adapted[1].cpu, null)
  assert.equal(adapted[1].backup, 'missing')
  assert.equal(adapted[1].finding, 'No recent backup or snapshot')

  assert.equal(adapted[2].cpu, 54.3)
  assert.equal(adapted[2].backup, 'stale')
  assert.equal(adapted[2].lastBackup, 'Nov 10, 03:00 UTC')
  assert.equal(adapted[2].finding, 'Backup snapshot is outdated')

  assert.equal(adapted[3].cpu, null)
  assert.equal(adapted[3].backup, 'protected')
  assert.equal(adapted[3].lastBackup, 'Nov 21, 00:00 UTC')
  assert.equal(adapted[3].finding, 'Custom metadata finding')

  assert.equal(adaptResources([]).length, 0)
  assert.deepEqual(adaptResources(undefined), [])
})

test('adaptAlerts builds 5-factor breakdown with exact weights and inferred events', () => {
  const raw = {
    total: 1,
    alerts: [
      {
        alert_id: 'ALT-9001',
        resource_id: 'i-rogue',
        alert_type: 'iam_compute_surge',
        severity: 'critical',
        risk_score: 93.6,
        ml_score: 0.91,
        title: 'Suspicious IAM activity',
        correlated_event_ids: ['ct-9001', 'cw-9004', 'ce-9005', 'tr-9006', 'bk-9007'],
        signal_breakdown: {
          cloudtrail_count: 2,
          metric_spike_count: 1,
          cost_delta_count: 1,
          iam_risk: 94.0,
          resource_impact: 88.2,
          cost_impact: 82.0,
          traffic_anomaly: 45.4,
          total_cost_delta_usd: 420.5,
        },
        summary: 'Compromised IAM session launched GPU instance.',
        recommended_actions: ['Revoke session', 'Terminate instance'],
        status: 'open',
        created_at: '2026-11-21T02:50:00Z',
      },
    ],
  }

  const [alert] = adaptAlerts(raw)
  assert.equal(alert.id, 'ALT-9001')
  assert.equal(alert.severity, 'CRITICAL')
  assert.equal(alert.riskScore, 94)
  assert.equal(alert.status, 'open')
  assert.equal(alert.timestamp, '2026-11-21T02:50:00.000Z')
  assert.equal(alert.summary, 'Compromised IAM session launched GPU instance.')
  assert.deepEqual(alert.steps, ['Revoke session', 'Terminate instance'])

  assert.deepEqual(alert.breakdown, [
    { key: 'ml', label: 'Behavior anomaly (ML)', value: 91, weight: 0.3 },
    { key: 'iam', label: 'IAM risk', value: 94, weight: 0.25 },
    { key: 'resource', label: 'Resource impact', value: 88, weight: 0.2 },
    { key: 'cost', label: 'Cost impact', value: 82, weight: 0.15 },
    { key: 'traffic', label: 'Traffic anomaly', value: 45, weight: 0.1 },
  ])

  assert.deepEqual(
    alert.events.map((e) => e.source),
    ['CloudTrail', 'CloudWatch', 'Cost Explorer', 'Traffic logs', 'AWS Backup'],
  )
  assert.equal(alert.events[0].time, '02:50')
  assert.match(alert.events[0].text, /ct-9001/)

  assert.deepEqual(adaptAlerts(null), [])
})

test('adaptTraffic normalizes botShare ratio, proportional timeline cost, and endpoint patterns', () => {
  const raw = {
    request_rate_timeline: [
      {
        timestamp: '2026-11-20T18:00:00Z',
        total_requests: 100000,
        bot_requests: 80000,
        avg_cpu_pct: 68.4,
        network_out_gb: 25.0,
      },
      {
        timestamp: '2026-11-20T19:00:00Z',
        total_requests: 300000,
        bot_requests: 280000,
        avg_cpu_pct: 91.6,
        network_out_gb: 75.0,
      },
    ],
    suspicious_endpoints: [
      {
        endpoint: '/api/catalog/export',
        method: 'GET',
        request_count_24h: 100000,
        bot_share_pct: 94.0,
        bot_flagged: true,
        pattern_reason: 'Sequential pagination',
        top_user_agent: 'python-requests/2.31',
      },
      {
        endpoint: '/api/catalog/export',
        method: 'GET',
        request_count_24h: 200000,
        bot_share_pct: 96.4,
        bot_flagged: true,
        pattern_reason: 'Sequential pagination',
        top_user_agent: 'python-requests/2.31',
      },
    ],
    bot_flags: {
      total_requests_24h: 400000,
      flagged_bot_requests_24h: 360000,
      bot_traffic_pct: 90.0,
      suspicious_ips_count: 12,
      flagged_endpoints_count: 1,
    },
    cost_impact: {
      affected_resource_id: 'i-web',
      estimated_daily_cost_usd: 100.0,
      estimated_monthly_cost_usd: 3000.0,
      added_egress_gb_24h: 100.0,
      cpu_overhead_pct: 60.0,
    },
  }

  const adapted = adaptTraffic(raw)
  assert.equal(adapted.totalRequests, 400000)
  assert.equal(adapted.botShare, 0.9)
  assert.equal(adapted.costImpact, 100)

  assert.deepEqual(adapted.timeline, [
    { time: '18:00', requests: 100000, cpu: 68, cost: 25, cumulativeCost: 25 },
    { time: '19:00', requests: 300000, cpu: 92, cost: 75, cumulativeCost: 100 },
  ])

  assert.equal(adapted.patterns.length, 1)
  assert.deepEqual(adapted.patterns[0], {
    endpoint: '/api/catalog/export',
    requests: 300000,
    ip: 'Sequential pagination',
    userAgent: 'python-requests/2.31',
    bot: true,
    confidence: 0.964,
  })

  assert.deepEqual(adaptTraffic(null), {
    totalRequests: 0,
    botShare: 0,
    costImpact: 0,
    timeline: [],
    patterns: [],
  })
})

test('adaptRecommendations and adaptRecommendationAction map confidence strings and unwrap POST responses', () => {
  const raw = {
    total: 3,
    total_estimated_monthly_savings_usd: 180.2,
    recommendations: [
      {
        recommendation_id: 'rec_1',
        resource_id: 'i-1',
        category: 'cost',
        title: 'Downsize EC2',
        action: 'Resize to t3.medium',
        estimated_monthly_savings_usd: 132.2,
        confidence: 'high',
        state: 'pending',
      },
      {
        recommendation_id: 'rec_2',
        resource_id: 'vol-1',
        category: 'security',
        title: 'Encrypt volume',
        action: 'Enable KMS encryption',
        estimated_monthly_savings_usd: 0,
        confidence: 'medium',
        state: 'approved',
      },
      {
        recommendation_id: 'rec_3',
        resource_id: 'db-1',
        category: 'backup',
        title: 'Enable snapshot',
        action: 'Set retention to 14d',
        estimated_monthly_savings_usd: 0,
        confidence: 'low',
        state: 'dismissed',
      },
    ],
  }

  const adapted = adaptRecommendations(raw)
  assert.deepEqual(adapted, [
    {
      id: 'rec_1',
      resourceId: 'i-1',
      category: 'cost',
      title: 'Downsize EC2',
      action: 'Resize to t3.medium',
      estimatedSavings: 132.2,
      confidence: 0.9,
      state: 'pending',
    },
    {
      id: 'rec_2',
      resourceId: 'vol-1',
      category: 'security',
      title: 'Encrypt volume',
      action: 'Enable KMS encryption',
      estimatedSavings: 0,
      confidence: 0.7,
      state: 'approved',
    },
    {
      id: 'rec_3',
      resourceId: 'db-1',
      category: 'backup',
      title: 'Enable snapshot',
      action: 'Set retention to 14d',
      estimatedSavings: 0,
      confidence: 0.5,
      state: 'dismissed',
    },
  ])

  const actionResp = adaptRecommendationAction({
    recommendation: { recommendation_id: 'rec_1', state: 'approved' },
    previous_state: 'pending',
    message: "Recommendation 'rec_1' updated",
  })
  assert.deepEqual(actionResp, {
    id: 'rec_1',
    state: 'approved',
    previousState: 'pending',
    message: "Recommendation 'rec_1' updated",
  })

  assert.deepEqual(adaptRecommendations(null), [])
})

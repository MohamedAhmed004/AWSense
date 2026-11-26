const weights = { ml: 0.3, iam: 0.25, resource: 0.2, cost: 0.15, traffic: 0.1 }
const parts = (ml, iam, resource, cost, traffic) => [
  { key: 'ml', label: 'Behavior anomaly (ML)', value: ml, weight: weights.ml },
  { key: 'iam', label: 'IAM risk', value: iam, weight: weights.iam },
  { key: 'resource', label: 'Resource impact', value: resource, weight: weights.resource },
  { key: 'cost', label: 'Cost impact', value: cost, weight: weights.cost },
  { key: 'traffic', label: 'Traffic anomaly', value: traffic, weight: weights.traffic },
]

export const alerts = [
  {
    id: 'ALT-1042', title: 'Possible compromised credentials: unusual IAM login followed by 8 new EC2 instances',
    severity: 'CRITICAL', riskScore: 94, status: 'open', timestamp: '2026-11-21T14:37:00Z',
    breakdown: parts(94, 96, 92, 98, 70),
    events: [
      { time: '14:29', text: 'IAM role analyst-role assumed from a new IP in a new region (eu-west-1)', source: 'CloudTrail' },
      { time: '14:32', text: '8 EC2 instances launched in eu-west-1', source: 'CloudTrail' },
      { time: '14:33', text: 'Security group sg-0abc opened to 0.0.0.0/0', source: 'CloudTrail' },
      { time: '14:34', text: 'Network out rose to 40x baseline on new instances', source: 'CloudWatch' },
      { time: '14:35', text: 'Daily spend projected at $92 against $8 expected', source: 'Cost' },
    ],
    summary: 'analyst-role signed in at 03:17 UTC from an address it has never used, then launched 8 instances in a region this account has never touched and opened a security group to the internet. CPU and outbound traffic on the new instances are far above anything in the 30-day baseline, and daily spend is heading for more than ten times normal. This pattern matches stolen credentials used for cryptomining.',
    steps: [
      'Disable the access keys for analyst-role and revoke its active sessions.',
      'Stop the 8 instances in eu-west-1 and keep them for forensics.',
      'Remove the 0.0.0.0/0 rule from sg-0abc.',
      'Review CloudTrail for any other actions by this role in the last 24 hours.',
      'Notify the security team and rotate any secrets the role could read.',
    ],
  },
  {
    id: 'ALT-1041', title: 'Automated bot traffic on /api/products driving CPU and cost up',
    severity: 'HIGH', riskScore: 78, status: 'open', timestamp: '2026-11-21T16:05:00Z',
    breakdown: parts(81, 22, 64, 71, 97),
    events: [
      { time: '12:00', text: 'Requests per hour rose from about 5K to 90K', source: 'CloudWatch' },
      { time: '14:00', text: 'Peak of 480K requests per hour from 3 IP ranges', source: 'Traffic logs' },
      { time: '14:10', text: 'web-api-01 CPU passed 85% and auto scaling added capacity', source: 'CloudWatch' },
    ],
    summary: 'About 2.4M repetitive requests hit /api/products and /api/search in six hours, almost all from three IP ranges with the same user agent. The load pushed web-api-01 above 85% CPU and triggered extra scaling, which added cost without adding real users.',
    steps: [
      'Add a rate-limit rule for the three IP ranges in AWS WAF.',
      'Cache /api/products responses for 60 seconds at the edge.',
      'Review auto scaling limits so a bot spike cannot scale without a cap.',
    ],
  },
  {
    id: 'ALT-1040', title: 'orders-prod has no snapshot in 9 days',
    severity: 'HIGH', riskScore: 66, status: 'open', timestamp: '2026-11-21T08:00:00Z',
    breakdown: parts(30, 40, 78, 10, 5),
    events: [
      { time: '11-12', text: 'Last successful AWS Backup recovery point created', source: 'AWS Backup' },
      { time: '11-14', text: 'Backup job failed: IAM role missing rds:CreateDBSnapshot', source: 'AWS Backup' },
    ],
    summary: 'The production orders database has not had a successful backup for 9 days because the backup job lost a required permission. If the database is damaged or deleted, the most recent recovery point is 9 days old.',
    steps: [
      'Restore the missing permission on the backup role.',
      'Run an on-demand backup of orders-prod now.',
      'Add a failed-backup alarm so a missed job is caught within a day.',
    ],
  },
  {
    id: 'ALT-1039', title: 'Two unattached EBS volumes without snapshots',
    severity: 'MEDIUM', riskScore: 38, status: 'investigating', timestamp: '2026-11-20T10:20:00Z',
    breakdown: parts(12, 5, 45, 40, 0),
    events: [
      { time: '10-18', text: 'vol-0123abcd detached from its instance', source: 'CloudTrail' },
      { time: '10-30', text: 'vol-0456efgh detached from its instance', source: 'CloudTrail' },
    ],
    summary: 'Two volumes have been detached for three weeks or more. They cost $55 a month and hold data with no backup.',
    steps: ['Snapshot both volumes.', 'Delete them once the snapshots are verified.'],
  },
]

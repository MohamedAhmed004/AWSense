export const resources = [
  { id: 'i-0a1b2c3d4e', name: 'web-api-01', type: 'ec2', region: 'us-east-1', status: 'running', cpu: 38, backup: 'n/a', lastBackup: null, monthlyCost: 61.2, finding: null },
  { id: 'i-0f9e8d7c6b', name: 'batch-worker-02', type: 'ec2', region: 'us-east-1', status: 'running', cpu: 7, backup: 'n/a', lastBackup: null, monthlyCost: 62.0, finding: 'Underutilized: averaging 7% CPU over 14 days' },
  { id: 'i-07aa11bb22', name: 'burst-fleet-01', type: 'ec2', region: 'eu-west-1', status: 'running', cpu: 94, backup: 'n/a', lastBackup: null, monthlyCost: 710.0, finding: 'Launched by an unfamiliar principal in a new region' },
  { id: 'i-07aa11bb23', name: 'burst-fleet-02', type: 'ec2', region: 'eu-west-1', status: 'running', cpu: 91, backup: 'n/a', lastBackup: null, monthlyCost: 710.0, finding: 'Launched by an unfamiliar principal in a new region' },
  { id: 'vol-0123abcd', name: 'old-reports-vol', type: 'ebs', region: 'us-east-1', status: 'unattached', cpu: null, backup: 'missing', lastBackup: null, monthlyCost: 40.0, finding: 'Unattached for 21 days, no snapshot' },
  { id: 'vol-0456efgh', name: 'scratch-vol', type: 'ebs', region: 'us-east-1', status: 'unattached', cpu: null, backup: 'missing', lastBackup: null, monthlyCost: 15.0, finding: 'Unattached for 34 days, no snapshot' },
  { id: 'vol-0789ijkl', name: 'web-api-01-root', type: 'ebs', region: 'us-east-1', status: 'in-use', cpu: null, backup: 'protected', lastBackup: '2 hours ago', monthlyCost: 8.0, finding: null },
  { id: 'db-prod-orders', name: 'orders-prod', type: 'rds', region: 'us-east-1', status: 'available', cpu: 31, backup: 'missing', lastBackup: '9 days ago', monthlyCost: 184.0, finding: 'No snapshot in 9 days, recovery point is stale' },
  { id: 'db-analytics', name: 'analytics-reporting', type: 'rds', region: 'us-east-1', status: 'available', cpu: 22, backup: 'protected', lastBackup: '3 hours ago', monthlyCost: 96.5, finding: null },
  { id: 's3-customer-uploads', name: 'customer-uploads', type: 's3', region: 'us-east-1', status: 'active', cpu: null, backup: 'protected', lastBackup: '1 day ago', monthlyCost: 23.4, finding: null },
  { id: 's3-logs-archive', name: 'logs-archive', type: 's3', region: 'us-east-1', status: 'active', cpu: null, backup: 'stale', lastBackup: '12 days ago', monthlyCost: 305.0, finding: 'Cold logs sit in Standard storage; versioning backup is 12 days old' },
]

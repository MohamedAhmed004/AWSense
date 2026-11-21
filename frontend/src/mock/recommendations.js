export const recommendations = [
  { id: 'REC-201', resourceId: 'i-07aa11bb22', category: 'cost', title: 'Terminate the burst fleet in eu-west-1', action: 'Stop and terminate 8 unrecognized instances after taking forensic snapshots.', estimatedSavings: 1420, confidence: 0.96, state: 'pending' },
  { id: 'REC-202', resourceId: 'sg-0abc', category: 'security', title: 'Close sg-0abc to the internet', action: 'Remove the 0.0.0.0/0 ingress rule and restore the previous rules.', estimatedSavings: 0, confidence: 0.93, state: 'pending' },
  { id: 'REC-203', resourceId: 'db-prod-orders', category: 'backup', title: 'Back up orders-prod now', action: 'Restore the backup role permission and start an on-demand snapshot.', estimatedSavings: 0, confidence: 0.9, state: 'pending' },
  { id: 'REC-204', resourceId: 's3-logs-archive', category: 'cost', title: 'Move cold logs to Glacier', action: 'Add a lifecycle rule that moves objects older than 30 days to Glacier Instant Retrieval.', estimatedSavings: 305, confidence: 0.82, state: 'pending' },
  { id: 'REC-205', resourceId: 'i-0f9e8d7c6b', category: 'cost', title: 'Downsize batch-worker-02', action: 'Move from m5.xlarge to t3.small, which fits its 7% average CPU.', estimatedSavings: 62, confidence: 0.78, state: 'pending' },
  { id: 'REC-206', resourceId: 'vol-0123abcd', category: 'cost', title: 'Snapshot and delete two unattached volumes', action: 'Snapshot vol-0123abcd and vol-0456efgh, then delete them.', estimatedSavings: 55, confidence: 0.85, state: 'pending' },
]

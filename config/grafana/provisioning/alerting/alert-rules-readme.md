# Grafana Alert Rules - Setup Instructions

Alert rules in Grafana v10.4 must be created through the UI or via the HTTP API.
Provisioning YAML format for alert rules is complex and version-specific.

## Option 1: Manual Setup in Grafana UI (Recommended for now)

1. Go to http://localhost:3001/alerting/alert-rules
2. Click "Create alert rule"
3. Configure rules (examples below)

## Option 2: Create via HTTP API

After setting up the Discord contact point, use:

```bash
curl -X POST http://localhost:3001/api/v1/rules/Loki \
  -H "Authorization: Bearer $GRAFANA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "uid": "critical-errors",
    "title": "Critical Errors in Logs",
    "condition": "A",
    "data": [
      {
        "refId": "A",
        "queryType": "",
        "relativeTimeRange": {"from": 300, "to": 0},
        "datasourceUid": "loki",
        "expression": "count(count_over_time({job=~\".+\"} |= \"error\" or |= \"ERROR\" or |= \"fatal\" or |= \"FATAL\" [5m])) by ()"
      }
    ],
    "noDataState": "NoData",
    "execErrState": "Alerting",
    "for": "1m",
    "annotations": {
      "description": "Critical or fatal errors detected in logs over the last 5 minutes",
      "summary": "Critical errors found"
    },
    "labels": {
      "severity": "critical"
    }
  }'
```

## Example Alert Rules to Create

### Rule 1: Critical Errors
- **Title:** Critical Errors in Logs
- **Query:** `count(count_over_time({job=~".+"} |= "error" or |= "ERROR" or |= "fatal" or |= "FATAL" [5m])) by ()`
- **Condition:** A > 0
- **For:** 1m
- **Contact Point:** Discord

### Rule 2: High Restart Rate
- **Title:** High Service Restart Rate
- **Query:** `count(count_over_time({job=~".+"} |= "restarting" or |= "restart" [10m])) by ()`
- **Condition:** A > 5
- **For:** 2m
- **Contact Point:** Discord

### Rule 3: Service Not Logging
- **Title:** Service Not Logging
- **Query:** `absent(count_over_time({job=~".+"} [10m])) == 1`
- **Condition:** A == 1
- **For:** 5m
- **Contact Point:** Discord

## Grafana API Token

To create rules via API, you need a service account token:

```bash
# In Grafana UI:
# Admin → Service Accounts → New Service Account
# → Create token → Save token to GRAFANA_API_TOKEN env var

export GRAFANA_API_TOKEN="your-token-here"
```

## Verify Contact Point is Configured

```bash
curl -s http://localhost:3001/api/v1/provisioning/contact-points \
  -H "Authorization: Bearer $GRAFANA_API_TOKEN" | jq .
```

Should show Discord contact point with webhook URL.

## See Also

- Grafana Alerting Docs: https://grafana.com/docs/grafana/latest/alerting/
- Provisioning Guide: https://grafana.com/docs/grafana/latest/administration/provisioning/
- Loki Queries: https://grafana.com/docs/loki/latest/logql/

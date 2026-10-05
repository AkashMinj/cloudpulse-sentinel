# Priority 1 Integration Guide

## Overview
This guide integrates three critical features without breaking existing code:
1. **Incident Replay** - Timeline tracking for all incidents
2. **ML Anomaly Integration** - Automatic ML-based anomaly detection
3. **Basic Authentication** - JWT token-based auth with RBAC

## Files Created

### 1. Database Schema (`scripts/init_database.sql`)
- `incident_events` table - Stores timeline events
- `anomaly_detections` table - ML detection results
- `users` table - User authentication
- `api_tokens` table - Token management
- Default users: admin/admin123, analyst/analyst123

### 2. Authentication Module (`app/auth.py`)
- JWT token generation and validation
- Role-based access control (admin, analyst, developer, read_only)
- Password hashing with bcrypt

### 3. Incident Replay Module (`app/incident_replay.py`)
- Record events in incident timeline
- Retrieve complete incident history
- Atomic incident creation with events

### 4. ML Anomaly Service (`app/ml_anomaly_service.py`)
- Automatic ML model training
- Real-time anomaly detection
- Creates incidents from ML anomalies

### 5. Extension Routes (`app/main_extensions.py`)
- Authentication endpoints
- Incident replay endpoints
- ML status endpoints

## Integration Steps

### Step 1: Update Database (Run on EC2)
```bash
# SSH to EC2
ssh ec2-user@18.214.224.132

# Navigate to project
cd /home/ec2-user/cloudpulse-sentinel

# Run database migration
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f scripts/init_database.sql
```

### Step 2: Install Dependencies
```bash
# Activate virtual environment
source .venv/bin/activate

# Install new packages
pip install pyjwt passlib[bcrypt] python-multipart
```

### Step 3: Add Routes to main.py
Add these lines at the END of `app/main.py` (after the last endpoint):

```python
# ============================
# PRIORITY 1: NEW FEATURES
# ============================

from app.main_extensions import (
    register_auth_routes,
    register_incident_replay_routes,
    register_ml_routes,
)
from app.ml_anomaly_service import MLAnomalyService

# Initialize ML service
ml_service = MLAnomalyService()

# Register new routes
register_auth_routes(app, ml_service)
register_incident_replay_routes(app)
register_ml_routes(app, ml_service)
```

### Step 4: Integrate ML into Metrics Collection
Add this code in the `collect_and_store_metrics()` function AFTER `metric_id` is created (around line 351):

```python
        # Run ML anomaly detection
        try:
            if ml_service.is_trained:
                anomaly_result = ml_service.detect_anomaly(
                    connection, metrics, metric_id
                )

                if anomaly_result and anomaly_result.is_anomaly:
                    # Create anomaly incident
                    anomaly_incident_id = ml_service.create_anomaly_incident(
                        connection, metrics, anomaly_result, metric_id
                    )

                    if anomaly_incident_id:
                        # Record anomaly event
                        from app.incident_replay import IncidentReplay

                        IncidentReplay.record_event(
                            connection,
                            anomaly_incident_id,
                            "ml_anomaly_detected",
                            f"ML model detected anomaly with score {anomaly_result.anomaly_score:.4f}",
                            {
                                "anomaly_score": anomaly_result.anomaly_score,
                                "signals": ml_service.get_anomaly_signals(metrics)
                            }
                        )
        except Exception as ml_error:
            print(f"ML detection error: {ml_error}")
            # Don't fail the whole collection if ML fails
```

### Step 5: Add Event Recording to Incident Creation
Replace the incident creation loop (around line 394-434) with:

```python
        # Detect incidents from collected metrics
        incidents = detect_incidents(metrics)

        for incident in incidents:
            duplicate_check_query = """
                SELECT id
                FROM incidents
                WHERE instance_id = %s
                  AND incident_type = %s
                  AND status = 'open'
                LIMIT 1;
            """

            cursor.execute(
                duplicate_check_query,
                (incident["instance_id"], incident["incident_type"]),
            )

            existing_incident = cursor.fetchone()

            if existing_incident is not None:
                continue

            # Create incident with initial events
            incident_query = """
                INSERT INTO incidents (
                    instance_id, metric_id, incident_type, severity,
                    title, description, metric_value, threshold_value, detected_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """

            cursor.execute(
                incident_query,
                (
                    incident["instance_id"],
                    metric_id,
                    incident["incident_type"],
                    incident["severity"],
                    incident["title"],
                    incident["description"],
                    incident["metric_value"],
                    incident["threshold_value"],
                    incident["detected_at"],
                ),
            )

            incident_id = cursor.fetchone()[0]

            # Record initial timeline events
            from app.incident_replay import IncidentReplay

            IncidentReplay.record_event(
                connection,
                incident_id,
                "threshold_breach",
                f"{incident['incident_type']} crossed threshold",
                {
                    "metric_value": incident["metric_value"],
                    "threshold": incident["threshold_value"]
                }
            )

            IncidentReplay.record_event(
                connection,
                incident_id,
                "incident_created",
                f"Incident created: {incident['title']}",
                {"severity": incident["severity"]}
            )
```

### Step 6: Train ML Model
After deployment, train the model using historical data:

```bash
# Login to get token
TOKEN=$(curl -X POST http://18.214.224.132:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' \
  | jq -r '.access_token')

# Train ML model
curl -X POST http://18.214.224.132:8000/api/v1/ml/train \
  -H "Authorization: Bearer $TOKEN"
```

## Testing the Integration

### Test Authentication
```bash
# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# Get current user
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/auth/me
```

### Test Incident Replay
```bash
# Get incident timeline
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/incidents/1/replay
```

### Test ML Status
```bash
# Check ML status
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/ml/status
```

## Default User Accounts

| Username | Password | Role | Access Level |
|----------|----------|------|--------------|
| admin | admin123 | admin | Full access |
| analyst | analyst123 | analyst | ML training, incident analysis |
| developer | (create) | developer | Read/write metrics |
| read_only | (create) | read_only | View only |

## API Endpoints Summary

### Authentication
- `POST /api/v1/auth/login` - Login and get JWT token
- `GET /api/v1/auth/me` - Get current user info

### Incident Replay
- `GET /api/v1/incidents/{id}/replay` - Full incident timeline
- `GET /api/v1/incidents/{id}/events` - List all events

### ML Anomaly Detection
- `POST /api/v1/ml/train` - Train model (analyst+)
- `GET /api/v1/ml/status` - Model status
- `GET /api/v1/anomalies` - List detections

### Admin
- `GET /api/v1/admin/users` - List all users (admin only)

## Security Notes

1. **Change default passwords** in production
2. **Set JWT_SECRET_KEY** environment variable
3. **Use HTTPS** in production
4. **Rotate tokens** periodically
5. **Review RBAC** permissions

## Rollback Plan

If issues arise:
1. Remove the added code from main.py
2. Routes will still work (backward compatible)
3. Database tables are isolated (no breaking changes)

## Next Steps

After Priority 1 is complete:
- Priority 2: Build remediation engine
- Priority 3: Add notification service
- Complete E2E tests
- Final documentation

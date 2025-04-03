# Email Subject Analysis API

This document describes the Email Subject Analysis API endpoint that categorizes email subject lines and identifies their business context.

## Endpoint

```
POST /api/v1/analyze/subjects
```

## Authentication

Authentication is required using an API key in the `X-API-Key` header.

```
X-API-Key: your-api-key
```

## Request

### Headers

| Name | Required | Description |
|------|----------|-------------|
| X-API-Key | Yes | Your API key |
| Content-Type | Yes | Must be `application/json` |

### Body

```json
{
  "subjects": [
    "Timesheet approval for March 2024",
    "Please review SOW for Project Alpha"
  ],
  "min_confidence": 0.7
}
```

### Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| subjects | array of strings | Yes | List of email subject lines to analyze |
| min_confidence | float | No | Minimum confidence threshold (default: 0.7) |

## Response

### Success Response (202 Accepted)

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "status_url": "/api/v1/status/550e8400-e29b-41d4-a716-446655440000"
}
```

This response indicates that the analysis job has been accepted and is being processed asynchronously. You can check the status of the job using the provided `status_url`.

### Checking Job Status

```
GET /api/v1/status/{job_id}
```

Response:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "results_url": "/api/v1/results/550e8400-e29b-41d4-a716-446655440000"
}
```

Possible status values:
- `pending`: The job is still being processed
- `completed`: The job has completed successfully
- `failed`: The job has failed

### Getting Results

Once the job status is `completed`, you can retrieve the results using the provided `results_url`.

```
GET /api/v1/results/{job_id}
```

Response:

```json
{
  "results": [
    {
      "tag": "timesheet",
      "cluster": "March 2024",
      "subject": "Timesheet approval for March 2024"
    },
    {
      "tag": "sow",
      "cluster": "Project Alpha",
      "subject": "Please review SOW for Project Alpha"
    }
  ],
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "processing_time": 1.5,
  "count": 2
}
```

### Results Fields

| Field | Type | Description |
|-------|------|-------------|
| results | array | List of analysis results |
| results[].tag | string | Business category (timesheet, approval, staffing, sow, finance-review, general) |
| results[].cluster | string | High-level grouping or topic (e.g., month, client, project, system name) |
| results[].subject | string | Original subject line |
| job_id | string | The ID of the job |
| processing_time | number | Time taken to process the job in seconds |
| count | number | Number of subjects analyzed |

### Error Response (4xx/5xx)

```json
{
  "detail": "Error message"
}
```

## Example Usage

### cURL Example (Complete Flow)

```bash
# Step 1: Submit job
JOB_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/analyze/subjects" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "subjects": [
      "Timesheet approval for March 2024",
      "Please review SOW for Project Alpha"
    ],
    "min_confidence": 0.7
  }')

# Extract job_id and status_url
JOB_ID=$(echo $JOB_RESPONSE | jq -r '.job_id')
STATUS_URL=$(echo $JOB_RESPONSE | jq -r '.status_url')

echo "Job submitted with ID: $JOB_ID"

# Step 2: Poll for job completion
STATUS="pending"
while [ "$STATUS" = "pending" ]; do
  sleep 2
  STATUS_RESPONSE=$(curl -s -X GET "http://localhost:8000$STATUS_URL" \
    -H "X-API-Key: your-api-key")
  
  STATUS=$(echo $STATUS_RESPONSE | jq -r '.status')
  echo "Current status: $STATUS"
  
  if [ "$STATUS" = "completed" ]; then
    RESULTS_URL=$(echo $STATUS_RESPONSE | jq -r '.results_url')
  fi
done

# Step 3: Get results
if [ "$STATUS" = "completed" ]; then
  RESULTS=$(curl -s -X GET "http://localhost:8000$RESULTS_URL" \
    -H "X-API-Key: your-api-key")
  
  echo "Results:"
  echo $RESULTS | jq
fi
```

### Python Example (Complete Flow)

```python
import requests
import time
import json

api_base_url = "http://localhost:8000"
api_key = "your-api-key"

headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json"
}

payload = {
    "subjects": [
        "Timesheet approval for March 2024",
        "Please review SOW for Project Alpha"
    ],
    "min_confidence": 0.7
}

# Step 1: Submit job
response = requests.post(
    f"{api_base_url}/api/v1/analyze/subjects", 
    json=payload, 
    headers=headers
)

if response.status_code == 202:  # Accepted
    job_data = response.json()
    job_id = job_data["job_id"]
    status_url = job_data["status_url"]
    
    print(f"Job submitted with ID: {job_id}")
    
    # Step 2: Poll for job completion
    status = "pending"
    results_url = None
    
    while status == "pending":
        time.sleep(2)  # Wait 2 seconds between polls
        status_response = requests.get(
            f"{api_base_url}{status_url}",
            headers=headers
        )
        
        if status_response.status_code == 200:
            status_data = status_response.json()
            status = status_data["status"]
            print(f"Current status: {status}")
            
            if status == "completed":
                results_url = status_data["results_url"]
        else:
            print(f"Error checking status: {status_response.status_code}")
            break
    
    # Step 3: Get results
    if status == "completed" and results_url:
        results_response = requests.get(
            f"{api_base_url}{results_url}",
            headers=headers
        )
        
        if results_response.status_code == 200:
            results = results_response.json()
            print("Results:")
            print(json.dumps(results, indent=2))
        else:
            print(f"Error getting results: {results_response.status_code}")
    elif status == "failed":
        print("Job failed")
else:
    print(f"Error submitting job: {response.status_code}")
    print(response.text)
```

## Business Categories

The API categorizes email subjects into the following business categories:

- **timesheet**: Related to timesheet submissions, approvals, or reminders
- **approval**: Requests for approval of various business items
- **staffing**: Related to staffing assignments, resource allocation, or hiring
- **sow**: Statement of Work related communications
- **finance-review**: Financial reviews, budgets, or financial reporting
- **general**: General communications that don't fit into other categories

# Mail Analysis API

A Python API for analyzing Outlook 365 emails and their attachments using OpenAI's LLM capabilities.

## Overview

The Mail Analysis API is designed to process and analyze email content and attachments at scale. It accepts JSON-formatted email data with attachments, processes them asynchronously, and returns detailed analysis results.

Key features:
- Asynchronous email processing
- Support for various attachment types (PDF, Word, Excel, PowerPoint, Email, Text)
- Natural language processing using OpenAI's GPT models
- Scalable architecture for enterprise-level volumes
- Comprehensive security and rate limiting

## Documentation

### Architecture
- [System Overview](docs/architecture/01-system-overview.md)
- [Data Flow](docs/architecture/02-data-flow.md)
- [Component Breakdown](docs/architecture/03-component-breakdown.md)

### Operations
- [Error Handling & Notifications](docs/operations/01-error-handling.md)
- [Deployment Guide](docs/operations/02-deployment.md)

### Security
- [Authentication & Security](docs/security/01-auth-design.md)

### Configuration
- [Settings Guide](docs/config/01-settings-guide.md)

## Getting Started

### Prerequisites
- Python 3.9+
- Redis
- RabbitMQ
- OpenAI API key

### Installation

1. Clone the repository:
```bash
git clone https://github.com/your-organization/mail-analysis-api.git
cd mail-analysis-api
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure the application:
```bash
cp config/settings.example.yaml config/settings.yaml
# Edit config/settings.yaml with your settings
```

4. Set up environment variables:
```bash
export OPENAI_API_KEY=your-openai-api-key
export REDIS_HOST=localhost
```

5. Run the API server:
```bash
python -m app.main
```

6. Run worker processes:
```bash
python -m app.worker
```

## API Usage

### Subject Analysis

```bash
# Step 1: Submit job
curl -X POST http://localhost:8000/api/v1/analyze/subjects \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "subjects": [
      "Timesheet approval for March 2024",
      "Please review SOW for Project Alpha"
    ],
    "min_confidence": 0.7
  }'
```

Response:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "status_url": "/api/v1/status/550e8400-e29b-41d4-a716-446655440000"
}
```

Check job status:
```bash
# Step 2: Check status
curl -X GET http://localhost:8000/api/v1/status/550e8400-e29b-41d4-a716-446655440000 \
  -H "X-API-Key: your-api-key"
```

Response:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "results_url": "/api/v1/results/550e8400-e29b-41d4-a716-446655440000"
}
```

Get results:
```bash
# Step 3: Get results
curl -X GET http://localhost:8000/api/v1/results/550e8400-e29b-41d4-a716-446655440000 \
  -H "X-API-Key: your-api-key"
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

For more details, see the [Subject Analysis API documentation](docs/api/subject-analysis-api.md).

### Analyze Email

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "message_id": "example@mail.com",
    "subject": "Project Update",
    "from": {
      "name": "John Doe",
      "email": "john@example.com"
    },
    "to": [
      {
        "name": "Jane Smith",
        "email": "jane@example.com"
      }
    ],
    "date": "2023-04-02T12:00:00Z",
    "body_text": "Here is the project update you requested.",
    "attachments": [
      {
        "filename": "report.pdf",
        "content_type": "application/pdf",
        "content": "base64-encoded-content",
        "size": 12345
      }
    ]
  }'
```

Response:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "status_url": "/api/v1/status/550e8400-e29b-41d4-a716-446655440000"
}
```

### Check Status

```bash
curl -X GET http://localhost:8000/api/v1/status/550e8400-e29b-41d4-a716-446655440000 \
  -H "X-API-Key: your-api-key"
```

Response:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "results_url": "/api/v1/results/550e8400-e29b-41d4-a716-446655440000"
}
```

### Get Results

```bash
curl -X GET http://localhost:8000/api/v1/results/550e8400-e29b-41d4-a716-446655440000 \
  -H "X-API-Key: your-api-key"
```

Response:
```json
{
  "message_id": "example@mail.com",
  "subject": "Project Update",
  "date": "2023-04-02T12:00:00Z",
  "summary": "Project update email with PDF report attachment.",
  "sentiment": "neutral",
  "topics": ["project", "update", "report"],
  "action_items": ["Review the attached report"],
  "entities": [
    {"type": "person", "name": "John Doe"},
    {"type": "person", "name": "Jane Smith"}
  ],
  "intent": "information_sharing",
  "importance_score": 0.7,
  "attachment_analyses": [
    {
      "filename": "report.pdf",
      "content_type": "application/pdf",
      "size": 12345,
      "content_summary": "Quarterly project progress report showing 85% completion.",
      "sentiment": "positive",
      "topics": ["project", "progress", "quarterly", "report"]
    }
  ],
  "processing_time": 2.5,
  "job_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

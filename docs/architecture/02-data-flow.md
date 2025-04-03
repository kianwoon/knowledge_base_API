# Mail Analysis API Data Flow

## Request-Response Flow

The Mail Analysis API follows an asynchronous processing model to handle potentially large email datasets and attachments. Below is the detailed data flow from initial request to final response.

```mermaid
sequenceDiagram
    participant Client
    participant API as "API Gateway"
    participant Auth as "Auth Service"
    participant Redis
    participant Worker as "Processing Worker"
    participant LLM as "OpenAI LLM"
    participant Storage

    Client->>API: POST /analyze (JSON Email + Attachments)
    API->>Auth: Validate API Key
    Auth->>Redis: Check key validity & rate limits
    Redis-->>Auth: Validation result
    Auth-->>API: Authentication result
    
    alt Invalid API Key or Rate Limited
        API-->>Client: 401 Unauthorized or 429 Too Many Requests
    else Valid Request
        API->>Redis: Enqueue analysis job
        Redis-->>API: Job ID
        API->>Redis: Store job status (pending)
        API-->>Client: 202 Accepted (Job ID)
        
        Worker->>Redis: Poll for pending jobs
        Redis-->>Worker: Job data
        Worker->>Storage: Save raw email data
        
        par Process Email Body
            Worker->>LLM: Analyze email content
            LLM-->>Worker: Content analysis results
        and Process Attachments
            Worker->>Worker: Extract & process attachments
            Worker->>LLM: Analyze attachment content
            LLM-->>Worker: Attachment analysis results
        end
        
        Worker->>Storage: Save analysis results
        Worker->>Redis: Update job status (completed)
        
        alt Webhook Configured
            Worker->>Client: POST webhook with completion notification
        end
    end
    
    Client->>API: GET /status/{job_id}
    API->>Redis: Get job status
    Redis-->>API: Job status & result location
    
    alt Job Completed
        API->>Storage: Retrieve analysis results
        Storage-->>API: Analysis results
        API-->>Client: 200 OK (Analysis Results)
    else Job In Progress
        API-->>Client: 200 OK (Status: processing)
    else Job Failed
        API-->>Client: 200 OK (Status: failed, Error details)
    end
```

## Data Processing Stages

### 1. Request Validation
- Validate API key against Redis store
- Check rate limits for the client tier
- Validate input JSON structure
- Check attachment size and type constraints

### 2. Job Queuing
- Generate unique job ID (UUID)
- Store job metadata in Redis with TTL
- Store job in Redis queue
- Return job ID to client immediately

### 3. Email Content Processing
- Parse email JSON structure
- Extract headers, body, and metadata
- Prepare prompt for LLM analysis
- Send to OpenAI for content analysis
- Process and structure LLM response

### 4. Attachment Processing
- For each attachment:
  1. Identify file type using MIME detection
  2. Route to appropriate file handler
  3. Extract text/data based on file type
  4. Prepare extracted content for analysis
  5. Send to LLM for specialized analysis based on file type

### 5. Results Aggregation
- Combine email body analysis
- Merge attachment analysis results
- Generate summary statistics
- Format final JSON response
- Store complete results in Redis (with TTL) or persistent storage

### 6. Client Notification
- Update job status in Redis
- If webhook URL provided, send completion notification
- Make results available via GET endpoint

## Error Handling Flow

```mermaid
flowchart TD
    A[Error Detected] --> B{Error Type}
    B -->|Validation Error| C[Return 400 Bad Request]
    B -->|Authentication Error| D[Return 401 Unauthorized]
    B -->|Rate Limit Error| E[Return 429 Too Many Requests]
    B -->|Processing Error| F[Log Error]
    F --> G[Update Job Status]
    G --> H{Notification Configured?}
    H -->|Yes| I[Send Error Notification]
    H -->|No| J[Store Error Details]
    I --> K[Make Error Available via API]
    J --> K
```

## Data Retention Policy

- Raw email data: 24 hours
- Processing results: 7 days
- Error logs: 30 days
- Job metadata: 7 days

All data retention periods are configurable via the application settings.

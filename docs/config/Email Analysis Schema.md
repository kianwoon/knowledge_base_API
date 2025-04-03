
## Input Schema: 

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Email Schema",
  "type": "object",
  "properties": {
    "message_id": {
      "type": "string",
      "description": "Unique email identifier"
    },
    "subject": {
      "type": "string",
      "description": "Email subject line"
    },
    "from": {
      "$ref": "#/definitions/EmailAddress",
      "description": "Sender information"
    },
    "to": {
      "type": "array",
      "items": {
        "$ref": "#/definitions/EmailAddress"
      },
      "description": "Recipient list",
      "minItems": 1
    },
    "cc": {
      "type": "array",
      "items": {
        "$ref": "#/definitions/EmailAddress"
      },
      "default": []
    },
    "bcc": {
      "type": "array",
      "items": {
        "$ref": "#/definitions/EmailAddress"
      },
      "default": []
    },
    "date": {
      "type": "string",
      "format": "date-time",
      "description": "Email timestamp"
    },
    "body_text": {
      "type": ["string", "null"]
    },
    "body_html": {
      "type": ["string", "null"]
    },
    "attachments": {
      "type": "array",
      "items": {
        "$ref": "#/definitions/EmailAttachment"
      },
      "default": []
    },
    "headers": {
      "type": "object",
      "additionalProperties": {
        "type": "string"
      },
      "default": {}
    }
  },
  "required": [
    "message_id",
    "subject",
    "from",
    "to",
    "date"
  ],
  "definitions": {
    "EmailAddress": {
      "type": "object",
      "properties": {
        "name": {
          "type": ["string", "null"]
        },
        "email": {
          "type": "string",
          "format": "email"
        }
      },
      "required": ["email"]
    },
    "EmailAttachment": {
      "type": "object",
      "properties": {
        "filename": {
          "type": "string",
          "pattern": "^[\\w,\\s-]+\\.[A-Za-z]{3,4}$"
        },
        "content_type": {
          "type": "string",
          "examples": ["application/pdf", "image/png", "text/plain"]
        },
        "content": {
          "type": "string",
          "contentEncoding": "base64"
        },
        "size": {
          "type": "integer",
          "maximum": 26214400
        }
      },
      "required": [
        "filename",
        "content_type",
        "content",
        "size"
      ]
    }
  }
}
```

## Sample Input:

```json
{
  "message_id": "<CAEdw6K8y7F_3jJ4tQ7Z7Xy@mail.gmail.com>",
  "subject": "Urgent: Request for Sales Demo & Pricing",
  "from": {
    "name": "John Smith",
    "email": "john.smith@clientcorp.com"
  },
  "to": [
    {
      "name": "Sales Team",
      "email": "sales@yourcompany.com"
    }
  ],
  "cc": [
    {
      "name": "Emily Johnson",
      "email": "ejohnson@clientcorp.com"
    }
  ],
  "date": "2025-04-02T14:30:00Z",
  "body_text": "Dear Sales Team,\n\nWe're evaluating CRM solutions and would like to schedule a demo of your enterprise platform. Please provide:\n- Available time slots this week\n- Pricing details for 500 users\n- Implementation timeline\n\nWe need this information by EOD Thursday.\n\nBest,\nJohn Smith\nCTO, ClientCorp",
  "body_html": "<div><p>Dear Sales Team,</p><p>We're evaluating CRM solutions and would like to schedule a demo...</p></div>",
  "attachments": [
    {
      "filename": "ClientCorp_Requirements.pdf",
      "content_type": "application/pdf",
      "content": "JVBERi0xLjUK... (base64 truncated)",
      "size": 24576
    }
  ],
  "headers": {
    "Received": "from mx1.clientcorp.com (192.168.1.1)",
    "Return-Path": "<john.smith@clientcorp.com>"
  }
}
```


## Response Schema:


```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "EmailAnalysis",
  "type": "object",
  "properties": {
    "message_id": {
      "type": "string",
      "description": "Unique email message identifier"
    },
    "subject": {
      "type": "string",
      "description": "Email subject line"
    },
    "date": {
      "type": "string",
      "format": "date-time",
      "description": "Email received timestamp"
    },
    "summary": {
      "type": "string",
      "description": "Concise summary of email content"
    },
    "sentiment": {
      "type": "string",
      "enum": ["positive", "neutral", "negative"],
      "description": "Overall sentiment analysis"
    },
    "topics": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Key topics identified in email"
    },
    "action_items": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "description": {"type": "string"},
          "steps": {"type": "array", "items": {"type": "string"}},
          "priority": {"type": "string"},
          "due_date": {"type": "string", "format": "date-time"}
        },
        "required": ["description", "priority"]
      }
    },
    "entities": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "type": {"type": "string"},
          "value": {"type": "string"},
          "context": {"type": "string"},
          "role": {"type": "string"}
        },
        "required": ["type", "value"]
      }
    },
    "intent": {
      "type": "string",
      "description": "Primary intent classification"
    },
    "importance_score": {
      "type": "number",
      "minimum": 0,
      "maximum": 1,
      "description": "Criticality score (0-1)"
    },
    "attachment_analyses": {
      "type": "array",
      "items": {
        "$ref": "#/definitions/AttachmentAnalysis"
      }
    },
    "processing_time": {
      "type": "number",
      "description": "Analysis duration in seconds"
    },
    "job_id": {
      "type": "string",
      "description": "Unique processing job ID"
    },
    "source_category": {
      "type": "string",
      "enum": ["External", "Internal"]
    },
    "sensitivity_level": {
      "type": "string",
      "enum": ["Public", "Normal", "Confidential", "Highly Confidential"]
    },
    "response_required": {
      "type": "boolean"
    },
    "departments": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "agent_role": {
      "type": "string"
    }
  },
  "required": [
    "message_id",
    "subject",
    "date",
    "summary",
    "sentiment",
    "topics",
    "action_items",
    "entities",
    "intent",
    "importance_score",
    "processing_time",
    "job_id",
    "source_category",
    "sensitivity_level",
    "response_required",
    "departments"
  ],
  "definitions": {
    "AttachmentAnalysis": {
      "type": "object",
      "properties": {
        "filename": {"type": "string"},
        "content_type": {"type": "string"},
        "size": {"type": "integer"},
        "content_summary": {"type": "string"},
        "sentiment": {"type": "string"},
        "topics": {
          "type": "array",
          "items": {"type": "string"}
        },
        "entities": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": {"type": "string"}
          }
        },
        "needSave": {
          "type": "boolean",
          "default": false,
          "description": "Archive recommendation flag"
        }
      },
      "required": [
        "filename",
        "content_type",
        "size",
        "content_summary"
      ]
    }
  }
}
```

## Sample Response


```json
{
  "analysis": {
    "message_id": "<CAEdw6K8y7F_3jJ4tQ7Z7Xy@mail.gmail.com>",
    "subject": "Urgent: Request for Sales Demo & Pricing",
    "date": "2025-04-02T14:30:00Z",
    "summary": "Request for CRM platform demo and pricing details for 500 users...",
    "sentiment": "positive",
    "topics": ["sales", "crm", "pricing"],
    "action_items": [
      {
        "description": "Schedule product demo",
        "steps": [
          "1. Check sales team availability",
          "2. Prepare enterprise pricing sheet",
          "3. Draft implementation timeline",
          "4. Send proposal by Thursday EOD"
        ],
        "priority": "high",
        "due_date": "2025-04-03T23:59:00Z"
      }
    ],
    "entities": [
      {
        "type": "Person",
        "value": "John Smith",
        "context": "CTO, ClientCorp",
        "role": "decision-maker"
      }
    ],
    "intent": "sales_inquiry",
    "importance_score": 0.92,
    "attachment_analyses": [
      {
        "filename": "ClientCorp_Requirements.pdf",
        "content_type": "application/pdf",
        "size": 24576,
        "content_summary": "Technical requirements document outlining integration needs...",
        "sentiment": "neutral",
        "topics": ["integration", "security"],
        "needSave": true
      }
    ],
    "processing_time": 2.18,
    "job_id": "a1b2c3d4-e5f6-7890-g1h2-i3j4k5l6m7n8",
    "source_category": "External",
    "sensitivity_level": "Confidential",
    "response_required": true,
    "departments": ["Sales", "IT"],
    "agent_role": "Sales"
  }
}
```

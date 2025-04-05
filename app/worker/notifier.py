#!/usr/bin/env python3
"""
Notification implementations for the Worker module.
"""

import json
import aiohttp
from typing import Dict, Any, List
from loguru import logger

from app.core.config import config
from app.worker.interfaces import Notifier


class DefaultWebhookNotifier(Notifier):
    """Default implementation of the WebhookNotifier interface."""
    def __init__(
        self,
        webhook_url: str= None,
        webhook_enabled: bool=False,
        webhook_timeout: int= 10,
    ):
        """
        Initialize the job worker with dependencies.
        
        Args:
            repository: Job repository
            notifier:  notifier
            job_factory: Job factory
        """

        # Get webhook URL and settings from config
        self.webhook_url  = config.get("webhook", {}).get("url")
        self.webhook_enabled = config.get("webhook", {}).get("enabled", False)
        self.webhook_timeout = config.get("webhook", {}).get("timeout", 10)


    async def send_notification(self, data: Dict[str, Any], job_id: str, trace_id: str) -> None:
        """
        Send webhook notification with job results.
        
        Args:
            webhook_url: Webhook URL to call
            webhook_timeout: Timeout for the webhook request in seconds
            data: Data to send in the webhook
            job_id: Job ID
            trace_id: Trace ID
        """
        try:

            strData = json.dumps(data)
            logger.info(
                    f"Sending webhook notification for job {job_id} to {self.webhook_url}, trace_id: {trace_id}, data: {strData[:1000]}",
                )
        
            if self.webhook_enabled and self.webhook_url:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.webhook_url,
                        json=data,
                        headers={"Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=self.webhook_timeout)
                    ) as response:
                        response_text = await response.text()
                        # Extract headers for logging
                        headers_dict = dict(response.headers)
                        response_log = json.dumps(response_text, indent=2)

                        # Log the complete response with headers and status
                        logger.info(
                            f"response: {response_log}",
                            extra={"job_id": job_id, "trace_id": trace_id}
                        )
                        if response.status >= 200 and response.status < 300:
                            logger.info(
                                f"Webhook notification sent successfully for job {job_id}, status: {response.status}, trace_id: {trace_id}",
                                extra={"job_id": job_id, "trace_id": trace_id}
                            )
                        else:
                            # Log detailed error information
                            logger.error(
                                f"Failed to send webhook notification for job {job_id}, status: {response.status}, response_headers: {headers_dict}, response: {response_text[:2000] if len(response_text) > 2000 else response_text}, trace_id: {trace_id}",
                                extra={
                                    "job_id": job_id, 
                                    "trace_id": trace_id
                                }
                            )
            else:
                logger.info(
                    f"Webhook not enabled or no webhook URL found for job {job_id}, skipping notification, trace_id: {trace_id}",
                    extra={"job_id": job_id, "trace_id": trace_id}
                )

        except aiohttp.ClientResponseError as e:
            logger.error(f"Error sending webhook notification for job {job_id}, trace_id: {trace_id} Client Response Error: {e.status} - {e.message}")
        except aiohttp.ClientConnectionError as e:
            logger.error(f"Error sending webhook notification for job {job_id}, trace_id: {trace_id} Connection Error: {repr(e)}")
        except aiohttp.ClientPayloadError as e:
            logger.error(f"Error sending webhook notification for job {job_id}, trace_id: {trace_id} Payload Error: {repr(e)}")
        except Exception as e:
            logger.error(f"Error sending webhook notification for job {job_id}, trace_id: {trace_id} An unexpected error occurred: {repr(e)}")


class DefaultEmailNotifier(Notifier):
    """Default implementation of the EmailNotifier interface."""
    def __init__(
        self,
        recipients: List[str]= None,
        subject: str= None,
    ):
        """
        Initialize the job worker with dependencies.
        
        Args:
            recipients: List of email recipients
            subject: Email subject
        """
        # Get email settings from config
        self.recipients = config.get("email", {}).get("recipients")
        self.subject = config.get("email", {}).get("subject")

    
    async def send_notification(self, data: Dict[str, Any], job_id: str, trace_id: str) -> None:
        """
        Send email notification with job results.
        
        Args:
            recipients: List of email recipients
            subject: Email subject
            data: Data to send in the email
            job_id: Job ID
            trace_id: Trace ID
        """
        try:
            logger.info(
                f"Sending email notification for job {job_id} to {', '.join(self.recipients)}, trace_id: {trace_id}",
                extra={"job_id": job_id, "trace_id": trace_id}
            )
            
            # Placeholder for actual email sending implementation
            # This would typically use a library like aiosmtplib or a service like SendGrid/Mailgun
            logger.info(
                f"Email notification sent successfully for job {job_id}, trace_id: {trace_id}",
                extra={"job_id": job_id, "trace_id": trace_id}
            )
            
        except Exception as e:
            logger.error(f"Error sending email notification for job {job_id}, trace_id: {trace_id} An unexpected error occurred: {repr(e)}")


class DefaultSMSNotifier(Notifier):
    """Default implementation of the SMSNotifier interface."""
    def __init__(
        self,
        phone_numbers: List[str]= None,
    ):
        """
        Initialize the job worker with dependencies.
        
        Args:
            phone_numbers: List of phone numbers to send SMS to
        """
        # Get SMS settings from config
        self.phone_numbers = config.get("sms", {}).get("phone_numbers")
        self.sms_enabled = config.get("sms", {}).get("enabled", False)
        self.sms_timeout = config.get("sms", {}).get("timeout", 10)
        self.sms_service = config.get("sms", {}).get("service", "twilio")
        self.sms_api_key = config.get("sms", {}).get("api_key")
        self.sms_api_secret = config.get("sms", {}).get("api_secret")

    
    async def send_notification(self, data: Dict[str, Any], job_id: str, trace_id: str) -> None:
        """
        Send SMS notification with job results.
        
        Args:
            phone_numbers: List of phone numbers to send SMS to
            data: Data to send in the SMS
            job_id: Job ID
            trace_id: Trace ID
        """
        try:
            logger.info(
                f"Sending SMS notification for job {job_id} to {', '.join(self.phone_numbers)}, trace_id: {trace_id}",
                extra={"job_id": job_id, "trace_id": trace_id}
            )
            
            # Placeholder for actual SMS sending implementation
            # This would typically use a service like Twilio, Nexmo, or AWS SNS
            logger.info(
                f"SMS notification sent successfully for job {job_id}, trace_id: {trace_id}",
                extra={"job_id": job_id, "trace_id": trace_id}
            )
            
        except Exception as e:
            logger.error(f"Error sending SMS notification for job {job_id}, trace_id: {trace_id} An unexpected error occurred: {repr(e)}")
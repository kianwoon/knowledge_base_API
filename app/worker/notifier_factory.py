#!/usr/bin/env python3
"""
Notifier factory implementation for the Worker module.
"""

from loguru import logger

from app.worker.interfaces import Notifier, NotifierFactory
from app.worker.notifier import DefaultWebhookNotifier, DefaultEmailNotifier, DefaultSMSNotifier


class DefaultNotifierFactory(NotifierFactory):
    """
    Default implementation of the NotifierFactory interface.
    Creates appropriate notifier instances based on notification type.
    """
    
    def get_notifier(self, notifier_type: str) -> Notifier:
        """
        Get notifier for the given notification type.
        
        Args:
            notifier_type: Notification type (e.g., 'webhook', 'email', 'sms')
            
        Returns:
            Appropriate notifier implementation
        """
        logger.info(f"Creating notifier of type: {notifier_type}")
        
        if notifier_type.lower() == "email":
            return DefaultEmailNotifier()
        elif notifier_type.lower() == "sms":
            return DefaultSMSNotifier()
        else:
            # Default to webhook notifier
            return DefaultWebhookNotifier()
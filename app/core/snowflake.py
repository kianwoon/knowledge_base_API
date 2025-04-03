#!/usr/bin/env python3
"""
Snowflake ID generator for distributed unique ID generation.
"""

import time
import threading

class SnowflakeID:
    """
    Snowflake ID generator that creates unique 64-bit IDs.
    
    Structure:
    - 41 bits for timestamp (milliseconds since epoch)
    - 10 bits for machine ID (configurable)
    - 12 bits for sequence number (incremented for IDs generated in same millisecond)
    
    This provides:
    - ~69 years of usable timestamps from custom epoch
    - Support for 1024 different machine IDs
    - 4096 IDs per millisecond per machine
    """
    
    def __init__(self, machine_id=0, epoch=1672531200000):  # Default epoch: 2023-01-01 00:00:00 UTC
        """
        Initialize Snowflake ID generator.
        
        Args:
            machine_id: Machine ID (0-1023)
            epoch: Custom epoch in milliseconds
        """
        # Validate machine ID
        if not 0 <= machine_id <= 1023:
            raise ValueError("Machine ID must be between 0 and 1023")
            
        self.machine_id = machine_id
        self.epoch = epoch
        self.sequence = 0
        self.last_timestamp = -1
        self.lock = threading.Lock()
        
    def next_id(self):
        """
        Generate next Snowflake ID.
        
        Returns:
            Snowflake ID as integer
        """
        with self.lock:
            current_timestamp = self._current_timestamp()
            
            # Handle clock moving backwards
            if current_timestamp < self.last_timestamp:
                # Wait until we reach the last timestamp
                while current_timestamp < self.last_timestamp:
                    current_timestamp = self._current_timestamp()
            
            # Reset sequence if this is a new millisecond
            if current_timestamp > self.last_timestamp:
                self.sequence = 0
            else:
                # Increment sequence for same millisecond
                self.sequence = (self.sequence + 1) & 4095  # 12 bits max (0-4095)
                
                # If sequence overflows, wait for next millisecond
                if self.sequence == 0:
                    current_timestamp = self._wait_next_millis(self.last_timestamp)
            
            # Update last timestamp
            self.last_timestamp = current_timestamp
            
            # Generate ID
            snowflake_id = (
                ((current_timestamp - self.epoch) << 22) |  # Timestamp (41 bits)
                (self.machine_id << 12) |                   # Machine ID (10 bits)
                self.sequence                               # Sequence (12 bits)
            )
            
            return snowflake_id
    
    def next_id_str(self):
        """
        Generate next Snowflake ID as string.
        
        Returns:
            Snowflake ID as string
        """
        return str(self.next_id())
    
    def _current_timestamp(self):
        """
        Get current timestamp in milliseconds.
        
        Returns:
            Current timestamp in milliseconds
        """
        return int(time.time() * 1000)
    
    def _wait_next_millis(self, last_timestamp):
        """
        Wait until next millisecond.
        
        Args:
            last_timestamp: Last timestamp
            
        Returns:
            Next timestamp
        """
        timestamp = self._current_timestamp()
        while timestamp <= last_timestamp:
            timestamp = self._current_timestamp()
        return timestamp


# Create a global instance with default settings
snowflake_generator = SnowflakeID()


def generate_id():
    """
    Generate a new Snowflake ID.
    
    Returns:
        Snowflake ID as string
    """
    return snowflake_generator.next_id_str()

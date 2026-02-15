"""
WebSocket Communication Layer
==============================
Handles broadcasting signals to WebSocket server.
"""

import requests
import logging
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)

# WebSocket HTTP broadcast endpoint
# Use environment variable or fall back to EC2 production URL
WEBSOCKET_BROADCAST_URL = os.getenv(
    'WEBSOCKET_BROADCAST_URL',
    'http://ec2-34-235-119-67.compute-1.amazonaws.com:8004/'
)


def broadcast_to_channel(channel: str, data: Dict[str, Any]) -> bool:
    """
    Broadcast signal data to a specific WebSocket channel.
    
    Args:
        channel: WebSocket channel name (e.g., 'theta_entry', 'calendar_spread')
        data: Signal data to broadcast
        
    Returns:
        True if broadcast succeeded, False otherwise
    """
    try:
        payload = {
            "channel": channel,
            "signal": data
        }
        
        response = requests.post(
            WEBSOCKET_BROADCAST_URL,
            json=payload,
            timeout=5
        )
        
        if response.status_code == 200:
            logger.info(f"✅ Broadcast to '{channel}': {data.get('symbol', 'N/A')}")
            return True
        else:
            logger.warning(f"⚠️ Broadcast failed ({response.status_code}): {channel}")
            return False
            
    except requests.exceptions.ConnectionError:
        logger.warning(f"⚠️ WebSocket server not available for channel: {channel}")
        return False
    except Exception as e:
        logger.error(f"❌ Broadcast error for {channel}: {e}")
        return False

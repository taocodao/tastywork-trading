import logging
import time
from ib_insync import IB, util

logger = logging.getLogger(__name__)

class IBConnector:
    """Manages connection to Interactive Brokers Gateway/TWS."""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 4004, client_id: int = 100):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = IB()
        self.needs_reconnect = False
        
        # Connect to disconnected event
        self.ib.disconnectedEvent += self._on_disconnect
        
    def connect(self, max_retries=5, retry_delay=10):
        """Synchronous connect with retries. NEVER use asyncio.run() with ib_insync."""
        retries = 0
        while retries < max_retries:
            try:
                logger.info(f"Connecting to IB Gateway at {self.host}:{self.port} (Client ID: {self.client_id})...")
                self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=20)
                logger.info("Connected to IB Gateway successfully.")
                
                # Request live data by default (Mode 1)
                self.ib.reqMarketDataType(1)
                logger.info("Market data type set to Live (1).")
                self.needs_reconnect = False
                return True
            except Exception as e:
                retries += 1
                logger.warning(f"Connection failed ({retries}/{max_retries}): {e}")
                if retries < max_retries:
                    time.sleep(retry_delay) # Initial connect can use time.sleep
                
        logger.error("Failed to connect to IB Gateway after maximum retries.")
        return False
        
    def disconnect(self):
        """Disconnect from IB Gateway."""
        if self.is_connected():
            self.ib.disconnect()
            logger.info("Disconnected from IB Gateway.")

    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self.ib.isConnected()
        
    def _on_disconnect(self):
        """Callback when disconnected."""
        logger.warning("IB Gateway disconnected! Setting reconnect flag.")
        self.needs_reconnect = True
        
    def get_ib(self) -> IB:
        """Return the underlying ib_insync IB object."""
        return self.ib

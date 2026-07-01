import logging
import asyncio
from ib_insync import IB, util

logger = logging.getLogger(__name__)

class IBConnector:
    """Manages connection to Interactive Brokers Gateway/TWS."""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 4002, client_id: int = 100):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = IB()
        
        # Connect to disconnected event
        self.ib.disconnectedEvent += self._on_disconnect
        
    def connect(self, max_retries=5, retry_delay=10):
        """Synchronous connect with retries."""
        retries = 0
        while retries < max_retries:
            try:
                logger.info(f"Connecting to IB Gateway at {self.host}:{self.port} (Client ID: {self.client_id})...")
                self.ib.connect(self.host, self.port, clientId=self.client_id)
                logger.info("Connected to IB Gateway successfully.")
                
                # Request delayed data by default (Mode 3)
                # Mode 1: Live, Mode 2: Frozen, Mode 3: Delayed, Mode 4: Delayed Frozen
                self.ib.reqMarketDataType(3)
                logger.info("Market data type set to Delayed (3).")
                return True
            except Exception as e:
                retries += 1
                logger.warning(f"Connection failed ({retries}/{max_retries}): {e}")
                if retries < max_retries:
                    util.sleep(retry_delay)
                
        logger.error("Failed to connect to IB Gateway after maximum retries.")
        return False
        
    async def connect_async(self, max_retries=5, retry_delay=10):
        """Asynchronous connect with retries."""
        retries = 0
        while retries < max_retries:
            try:
                logger.info(f"Connecting to IB Gateway at {self.host}:{self.port} (Client ID: {self.client_id})...")
                await self.ib.connectAsync(self.host, self.port, clientId=self.client_id)
                logger.info("Connected to IB Gateway successfully.")
                self.ib.reqMarketDataType(3)
                logger.info("Market data type set to Delayed (3).")
                return True
            except Exception as e:
                retries += 1
                logger.warning(f"Connection failed ({retries}/{max_retries}): {e}")
                if retries < max_retries:
                    await asyncio.sleep(retry_delay)
                
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
        logger.warning("IB Gateway disconnected! Will try to reconnect on next operation.")
        
    def get_ib(self) -> IB:
        """Return the underlying ib_insync IB object."""
        return self.ib

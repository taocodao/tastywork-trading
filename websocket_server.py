"""
TradeMind WebSocket Server
==========================
Real-time signal push using WebSocket.
Broadcasts new signals to all connected clients.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Set, Dict, Any
import websockets
from websockets.server import WebSocketServerProtocol

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Connected clients
clients: Set[WebSocketServerProtocol] = set()

# Client subscriptions: {client: set of channels}
subscriptions: Dict[WebSocketServerProtocol, Set[str]] = {}


async def register(websocket: WebSocketServerProtocol):
    """Register a new client."""
    clients.add(websocket)
    # Default subscriptions include both calendar and vertical spread channels
    subscriptions[websocket] = {"calendar_spread", "vertical_spread", "vertical_spread.buy", "vertical_spread.sell", "vertical_spread.warning"}
    logger.info(f"Client connected. Total: {len(clients)}")
    
    # Send initial history immediately for default subscriptions
    await send_signal_history(websocket, subscriptions[websocket])


async def unregister(websocket: WebSocketServerProtocol):
    """Unregister a client."""
    clients.discard(websocket)
    subscriptions.pop(websocket, None)
    logger.info(f"Client disconnected. Total: {len(clients)}")


async def handle_message(websocket: WebSocketServerProtocol, message: str):
    """Handle incoming message from client."""
    try:
        data = json.loads(message)
        msg_type = data.get("type")
        
        if msg_type == "subscribe":
            channels = set(data.get("channels", []))
            subscriptions[websocket] = subscriptions.get(websocket, set()) | channels
            await websocket.send(json.dumps({
                "type": "subscribed",
                "channels": list(subscriptions[websocket])
            }))
            logger.info(f"Client subscribed to: {channels}")
            
            # Send history for new channels
            await send_signal_history(websocket, channels)
            
        elif msg_type == "unsubscribe":
            channels = set(data.get("channels", []))
            if websocket in subscriptions:
                subscriptions[websocket] -= channels
            await websocket.send(json.dumps({
                "type": "unsubscribed",
                "channels": list(channels)
            }))
            
        elif msg_type == "ping":
            await websocket.send(json.dumps({"type": "pong"}))
            
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON: {message}")
    except Exception as e:
        logger.error(f"Error handling message: {e}")


async def handler(websocket: WebSocketServerProtocol):
    """Handle WebSocket connection (websockets v16+ API - no path param)."""
    await register(websocket)
    try:
        # Send welcome message
        await websocket.send(json.dumps({
            "type": "connected",
            "message": "Connected to TradeMind Signal Server",
            "channels": list(subscriptions.get(websocket, []))
        }))
        
        async for message in websocket:
            await handle_message(websocket, message)
            
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        await unregister(websocket)


async def broadcast_signal(channel: str, signal: Dict[str, Any]):
    """Broadcast a signal to all subscribed clients."""
    if not clients:
        logger.info("No clients connected, signal not broadcast")
        return
    
    message = json.dumps({
        "type": "signal",
        "channel": channel,
        "data": signal,
        "timestamp": datetime.now().isoformat()
    })
    
    # Send to clients subscribed to this channel
    sent_count = 0
    for client in clients.copy():
        if channel in subscriptions.get(client, set()):
            try:
                await client.send(message)
                sent_count += 1
            except websockets.exceptions.ConnectionClosed:
                await unregister(client)
            except Exception as e:
                logger.error(f"Failed to send to client: {e}")
    
    logger.info(f"Broadcast signal to {sent_count}/{len(clients)} clients")


async def broadcast_account_update(data: Dict[str, Any]):
    """Broadcast account update to all clients."""
    message = json.dumps({
        "type": "account_update",
        "data": data,
        "timestamp": datetime.now().isoformat()
    })
    
    for client in clients.copy():
        try:
            await client.send(message)
        except:
            pass


# Persistence Logic (Using Shared DB)
import os
import sys

# Add current directory to path to allow 'src' imports
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

def load_signals_from_db() -> list:
    """Load signals from database."""
    try:
        from src.earnings_intelligence.database import SignalRepository
        repo = SignalRepository()
        signals = repo.get_all_signals()
        return [s.to_dict() for s in signals]
    except Exception as e:
        logger.error(f"Failed to load signals from DB: {e}")
    return []

async def send_signal_history(websocket: WebSocketServerProtocol, channels: Set[str]):
    """Send historical signals for the subscribed channels."""
    signals = load_signals_from_db()
    sent_count = 0
    
    # Filter only pending signals for initial load
    active_signals = [s for s in signals if s.get('status') == 'pending']
    
    for signal in active_signals:
        # Determine channel if not explicit
        channel = 'calendar_spread' # Default
        if 'iron_condor' in signal.get('strategy', '').lower():
            channel = 'iron_condor'
        elif 'vertical' in signal.get('strategy', '').lower():
            channel = 'vertical_spread'
            
        if channel in channels or 'vertical' in channel and 'vertical_spread' in channels:
             message = json.dumps({
                "type": "signal",
                "channel": channel,
                "data": signal,
                "timestamp": datetime.now().isoformat()
            })
             await websocket.send(message)
             sent_count += 1
             
    if sent_count > 0:
        logger.info(f"Sent {sent_count} historical signals to client")


# HTTP endpoint for triggering broadcasts (called from tasty_api_server)
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

_ws_broadcast_queue = asyncio.Queue()


class BroadcastHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler to trigger broadcasts from other processes."""
    
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode()
            data = json.loads(body)
            
            channel = data.get('channel', 'calendar_spread')
            signal = data.get('signal', {})
            
            # Queue the broadcast
            asyncio.run_coroutine_threadsafe(
                broadcast_signal(channel, signal),
                _event_loop
            )
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "broadcast_queued"}).encode())
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
    
    def log_message(self, format, *args):
        pass  # Silence HTTP logs


def run_http_server(port=8004):
    """Run HTTP server for broadcast triggers."""
    server = HTTPServer(('0.0.0.0', port), BroadcastHandler)
    logger.info(f"📡 HTTP broadcast endpoint: http://localhost:{port}/")
    server.serve_forever()


_event_loop = None


async def main(ws_port=8003, http_port=8004):
    """Start WebSocket server."""
    global _event_loop
    _event_loop = asyncio.get_event_loop()
    
    # Start HTTP server in thread for broadcast triggers
    http_thread = threading.Thread(target=run_http_server, args=(http_port,), daemon=True)
    http_thread.start()
    
    logger.info(f"🔌 Starting WebSocket server on port {ws_port}")
    logger.info(f"   Connect: ws://localhost:{ws_port}")
    
    async with websockets.serve(handler, "0.0.0.0", ws_port):
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(main())

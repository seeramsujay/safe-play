"""
WebSocket Connection Manager for SafePlay.

Role:
    Manages active WebSocket connections connected to the front-end operator
    dashboard. It provides capabilities to register connections, handle client
    disconnects, and broadcast concurrent state updates safely and asynchronously.

Ecosystem Positioning:
    - Below: FastAPI WebSocket protocol layer and standard asyncio scheduler.
    - Above:
        - `src/orchestrator.py`: holds an instance of `ConnectionManager` to broadcast
          the updated venue status (e.g. panic mode, active scripts, QoS changes) to all
          connected clients when telemetry is processed.
        - `src/web_api.py`: handles the `/ws` WebSocket endpoint routing, registering new
          connections and calling `disconnect` in a try/finally block when a client leaves.
"""


import asyncio
from typing import List
from fastapi import WebSocket

class ConnectionManager:
    """
    Manages WebSocket connections and concurrent broadcasts for real-time dashboard updates.
    """
    def __init__(self):
        """Initializes an empty registry of active WebSocket client connections."""
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """
        Accepts an incoming WebSocket connection handshake and registers the client.
        
        Args:
            websocket: The FastAPI WebSocket connection instance.
        """
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """
        Removes a disconnected WebSocket from the internal registry.
        
        Args:
            websocket: The active WebSocket connection to remove.
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        """
        Sends a JSON-serialized message concurrently to all active client connections.
        Handles client-side connection drops gracefully without disrupting other connections.
        
        Args:
            message: A dictionary payload containing updated application states.
        """
        async def send(conn: WebSocket) -> None:
            try:
                # Prevent hung or slow client connections from delaying the rest of the operators
                await asyncio.wait_for(conn.send_json(message), timeout=1.0)
            except Exception:
                # Silently ignore write failures resulting from client-side network disconnects.
                # These will be cleaned up in the websocket_endpoint disconnect block.
                pass
        
        # Copy the list to prevent modification (e.g. via concurrent disconnects) during iteration
        connections = list(self.active_connections)
        if connections:
            # Broadcast to all clients concurrently to minimize latency skew across operators
            await asyncio.gather(*(send(c) for c in connections))

"""
WebSocket Connection Manager for SafePlay.

This module provides the ConnectionManager class responsible for keeping track of open
WebSockets connected to the front-end operator dashboard and broadcasting state updates 
concurrently and thread-safely.
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
                await conn.send_json(message)
            except Exception:
                # Silently ignore write failures resulting from client-side network disconnects.
                # These will be cleaned up in the websocket_endpoint disconnect block.
                pass
        
        # Copy the list to prevent modification (e.g. via concurrent disconnects) during iteration
        connections = list(self.active_connections)
        if connections:
            # Broadcast to all clients concurrently to minimize latency skew across operators
            await asyncio.gather(*(send(c) for c in connections))

"""
WebSocket-based event subscription manager for client-side event subscriptions.
"""
from __future__ import annotations

import uuid
import asyncio
import json
import logging
from typing import Dict, Set, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect, status

from .event import EventManager


@dataclass(frozen=True)
class ClientSubscription:
    """
    Represents a client's subscription to an event via WebSocket.
    """
    client_id: str
    websocket: WebSocket = field(compare=False, hash=False)
    event_name: str
    subscription_id: str  # EventManager subscription ID
    created_at: datetime = field(compare=False, hash=False)


class WebSocketManager:
    """
    Manages WebSocket connections and client-side event subscriptions.

    Features:
    - Tracks all client WebSocket connections
    - Maps client subscriptions to server-side EventManager subscriptions
    - Automatically cleans up subscriptions when WebSocket disconnects
    - Removes server-side subscriptions when last client unsubscribes
    """

    logger = logging.getLogger("aspyx.event.ws")

    def __init__(self, event_manager: EventManager):
        """
        Initialize WebSocketManager.

        Args:
            event_manager: The EventManager instance for server-side subscriptions
        """
        self.event_manager = event_manager

        # client_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}

        # client_id -> Set[ClientSubscription]
        self.client_subscriptions: Dict[str, Set[ClientSubscription]] = {}

        # event_name -> Set[client_id]
        self.event_subscribers: Dict[str, Set[str]] = {}

        # event_name -> server subscription_id
        self.server_subscriptions: Dict[str, str] = {}

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        """
        Accept and register a new WebSocket connection.

        Args:
            websocket: FastAPI WebSocket instance
            client_id: Unique identifier for the client
        """
        await websocket.accept()

        async with self._lock:
            self.active_connections[client_id] = websocket
            self.client_subscriptions[client_id] = set()

        self.logger.info(f"Client {client_id} connected")

    async def disconnect(self, client_id: str) -> None:
        """
        Disconnect a client and clean up all their subscriptions.

        Args:
            client_id: Unique identifier for the client
        """
        async with self._lock:
            # Get all subscriptions for this client
            subscriptions = self.client_subscriptions.get(client_id, set())

            # Unsubscribe from all events
            for subscription in list(subscriptions):
                await self._unsubscribe_internal(client_id, subscription.event_name)

            # Remove client connection
            self.active_connections.pop(client_id, None)
            self.client_subscriptions.pop(client_id, None)

        self.logger.info(f"Client {client_id} disconnected and cleaned up")

    async def subscribe(self, client_id: str, event_name: str) -> bool:
        """
        Subscribe a client to an event.

        Args:
            client_id: Unique identifier for the client
            event_name: Name of the event to subscribe to

        Returns:
            bool: True if subscription successful, False otherwise
        """
        async with self._lock:
            self.logger.info(f"Subscribe: client {client_id} to event {event_name}")

            websocket = self.active_connections.get(client_id)
            if not websocket:
                self.logger.error(f"Cannot subscribe: client {client_id} not connected")
                return False

            # Check if client already subscribed to this event
            existing_subs = self.client_subscriptions.get(client_id, set())
            if any(sub.event_name == event_name for sub in existing_subs):
                self.logger.warning(f"Client {client_id} already subscribed to {event_name}")
                return True

            # Check if this is the first subscriber for this event
            if event_name not in self.server_subscriptions:
                # Create server-side subscription
                try:
                    self.logger.info(f"Creating NEW server subscription for {event_name} (first subscriber)")
                    subscription_id = await self._create_server_subscription(event_name)
                    self.server_subscriptions[event_name] = subscription_id
                    self.event_subscribers[event_name] = set()
                except Exception as e:
                    self.logger.error(f"Failed to create server subscription for {event_name}: {e}", exc_info=True)
                    return False
            else:
                self.logger.info(f"Reusing existing server subscription for {event_name} (subscription_id: {self.server_subscriptions[event_name]})")

            # Add client subscription
            client_subscription = ClientSubscription(
                client_id=client_id,
                websocket=websocket,
                event_name=event_name,
                subscription_id=self.server_subscriptions[event_name],
                created_at=datetime.now()
            )

            self.client_subscriptions[client_id].add(client_subscription)
            self.event_subscribers[event_name].add(client_id)

        self.logger.info(f"Client {client_id} subscribed to event {event_name}. Total subscribers for {event_name}: {len(self.event_subscribers[event_name])}")
        return True

    async def unsubscribe(self, client_id: str, event_name: str) -> bool:
        """
        Unsubscribe a client from an event.

        Args:
            client_id: Unique identifier for the client
            event_name: Name of the event to unsubscribe from

        Returns:
            bool: True if unsubscription successful, False otherwise
        """
        async with self._lock:
            return await self._unsubscribe_internal(client_id, event_name)

    async def _unsubscribe_internal(self, client_id: str, event_name: str) -> bool:
        """
        Internal unsubscribe logic (assumes lock is held).

        Args:
            client_id: Unique identifier for the client
            event_name: Name of the event to unsubscribe from

        Returns:
            bool: True if unsubscription successful, False otherwise
        """
        # Find and remove client subscription
        client_subs = self.client_subscriptions.get(client_id, set())
        subscription_to_remove = None

        for sub in client_subs:
            if sub.event_name == event_name:
                subscription_to_remove = sub
                break

        if not subscription_to_remove:
            self.logger.warning(f"Client {client_id} not subscribed to {event_name}")
            return False

        # Remove from client subscriptions
        client_subs.remove(subscription_to_remove)

        # Remove from event subscribers
        if event_name in self.event_subscribers:
            self.event_subscribers[event_name].discard(client_id)

            # If no more subscribers, remove server-side subscription
            if not self.event_subscribers[event_name]:
                await self._remove_server_subscription(event_name)
                del self.event_subscribers[event_name]
                del self.server_subscriptions[event_name]
                self.logger.info(f"Removed server subscription for {event_name} (no more clients)")

        self.logger.info(f"Client {client_id} unsubscribed from event {event_name}")
        return True

    async def _create_server_subscription(self, event_name: str) -> str:
        """
        Create a server-side subscription to forward events to WebSocket clients.

        Args:
            event_name: Name of the event to subscribe to

        Returns:
            str: Subscription ID from EventManager
        """
        async def event_callback(event: Any):
            """Callback to forward events to all subscribed WebSocket clients"""
            await self._broadcast_event(event_name, event)

        # Subscribe using the unified API
        # Use per_process=True to share the same NSQ channel across all WebSocket subscriptions
        # This ensures only one NSQ reader exists per event, avoiding duplicate deliveries
        subscription_id = await self.event_manager.subscribe(
            event_type=event_name,
            callback=event_callback,
            name=f"ws_broadcast_{event_name}",
            per_process=True,
            metadata={
                "websocket": True,
                "channel": f"ws_broadcast_{event_name}#ephemeral",
            }
        )

        self.logger.info(f"Created server subscription for {event_name}: {subscription_id}")
        return subscription_id

    async def _remove_server_subscription(self, event_name: str) -> None:
        """
        Remove server-side subscription when no clients are subscribed.

        Args:
            event_name: Name of the event
        """
        subscription_id = self.server_subscriptions.get(event_name)
        if subscription_id:
            await self.event_manager.unsubscribe(subscription_id)
            self.logger.info(f"Removed server subscription for {event_name}")

    async def _broadcast_event(self, event_name: str, event: Any) -> None:
        """
        Broadcast an event to all subscribed WebSocket clients.

        Args:
            event_name: Name of the event
            event: The event object
        """
        # Get all clients subscribed to this event
        client_ids = self.event_subscribers.get(event_name, set())

        self.logger.info(f"Broadcasting event {event_name} to {len(client_ids)} clients: {list(client_ids)}")
        self.logger.debug(f"Event subscribers state: {dict((k, list(v)) for k, v in self.event_subscribers.items())}")
        self.logger.debug(f"Active connections: {list(self.active_connections.keys())}")

        if not client_ids:
            self.logger.warning(f"No WebSocket clients subscribed to event {event_name}")
            return

        # Serialize event
        try:
            from aspyx.util import get_serializer
            event_data = get_serializer(type(event))(event)
            message = json.dumps({
                "type": "event",
                "event_name": event_name,
                "data": event_data,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            self.logger.error(f"Failed to serialize event {event_name}: {e}", exc_info=True)
            return

        # Send to all subscribed clients
        disconnected_clients = []
        for client_id in client_ids:
            websocket = self.active_connections.get(client_id)
            if websocket:
                try:
                    await websocket.send_text(message)
                except Exception as e:
                    self.logger.error(f"Failed to send event to client {client_id}: {e}", exc_info=True)
                    disconnected_clients.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected_clients:
            await self.disconnect(client_id)

    async def send_message(self, client_id: str, message: Dict[str, Any]) -> bool:
        """
        Send a message to a specific client.

        Args:
            client_id: Unique identifier for the client
            message: Message dictionary to send

        Returns:
            bool: True if sent successfully, False otherwise
        """
        websocket = self.active_connections.get(client_id)
        if not websocket:
            return False

        try:
            await websocket.send_json(message)
            return True
        except Exception as e:
            self.logger.error(f"Failed to send message to client {client_id}: {e}", exc_info=True)
            return False

    def get_client_count(self) -> int:
        """Get the number of active connections."""
        return len(self.active_connections)

    def get_subscription_count(self, event_name: Optional[str] = None) -> int:
        """
        Get the number of subscriptions.

        Args:
            event_name: Optional event name to filter by

        Returns:
            int: Number of subscriptions
        """
        if event_name:
            return len(self.event_subscribers.get(event_name, set()))
        else:
            return sum(len(subs) for subs in self.client_subscriptions.values())


# FastAPI WebSocket endpoint handler
async def websocket_endpoint(
    websocket: WebSocket,
    ws_manager: WebSocketManager,
    client_id: str
) -> None:
    """
    FastAPI WebSocket endpoint for handling client event subscriptions.

    Args:
        websocket: FastAPI WebSocket instance
        ws_manager: WebSocketManager instance
        client_id: Unique identifier for the client (e.g., from path or query param)

    Usage:
        @app.websocket("/ws/events/{client_id}")
        async def websocket_events(websocket: WebSocket, client_id: str):
            ws_manager = app.state.ws_manager  # Or inject via DI
            await websocket_endpoint(websocket, ws_manager, client_id)
    """
    await ws_manager.connect(websocket, client_id)

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                message_type = message.get("type")

                if message_type == "subscribe":
                    event_name = message.get("event_name")
                    if event_name:
                        success = await ws_manager.subscribe(client_id, event_name)
                        await websocket.send_json({
                            "type": "subscribe_response",
                            "event_name": event_name,
                            "success": success
                        })
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Missing event_name"
                        })

                elif message_type == "unsubscribe":
                    event_name = message.get("event_name")
                    if event_name:
                        success = await ws_manager.unsubscribe(client_id, event_name)
                        await websocket.send_json({
                            "type": "unsubscribe_response",
                            "event_name": event_name,
                            "success": success
                        })
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Missing event_name"
                        })

                elif message_type == "ping":
                    await websocket.send_json({"type": "pong"})

                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown message type: {message_type}"
                    })

            except json.JSONDecodeError as e:
                ws_manager.logger.error(f"Invalid JSON from client {client_id}: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON"
                })
            except Exception as e:
                ws_manager.logger.error(f"Error processing message from client {client_id}: {e}", exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })

    except WebSocketDisconnect:
        ws_manager.logger.info(f"Client {client_id} disconnected (WebSocketDisconnect)")
    except Exception as e:
        ws_manager.logger.error(f"Unexpected error for client {client_id}: {e}", exc_info=True)
    finally:
        # Always clean up on disconnect
        await ws_manager.disconnect(client_id)

import logging
import json
from typing import Optional, Callable, Awaitable, Any, Dict, Union
from fastapi import WebSocket
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manager for WebSocket connections with consistent error handling."""

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.is_connected = False

    async def connect(self) -> None:
        """
        Accept the WebSocket connection with error handling.

        Raises:
            Exception: If connection fails
        """
        try:
            await self.websocket.accept()
            self.is_connected = True
            logger.info("WebSocket connection accepted")
        except Exception as e:
            logger.error(f"Failed to accept WebSocket connection: {str(e)}")
            self.is_connected = False
            raise

    async def disconnect(self, code: int = 1000, reason: str = "Normal closure") -> None:
        """
        Close the WebSocket connection safely.

        Args:
            code: WebSocket close code
            reason: Close reason
        """
        if self.is_connected:
            try:
                await self.websocket.close(code=code, reason=reason)
                logger.info(f"WebSocket connection closed: {reason}")
            except Exception as e:
                logger.error(f"Error closing WebSocket connection: {str(e)}")
            finally:
                self.is_connected = False

    async def send_text(self, text: str) -> None:
        """
        Send text message with error handling.

        Args:
            text: Text message to send

        Raises:
            Exception: If sending fails
        """
        if not self.is_connected:
            raise RuntimeError("WebSocket is not connected")
        try:
            await self.websocket.send_text(text)
        except Exception as e:
            logger.error(f"Failed to send text message: {str(e)}")
            await self.disconnect(1011, "Failed to send message")
            raise

    async def send_bytes(self, data: bytes) -> None:
        """
        Send binary message with error handling.

        Args:
            data: Binary data to send

        Raises:
            Exception: If sending fails
        """
        if not self.is_connected:
            raise RuntimeError("WebSocket is not connected")
        try:
            await self.websocket.send_bytes(data)
        except Exception as e:
            logger.error(f"Failed to send binary message: {str(e)}")
            await self.disconnect(1011, "Failed to send message")
            raise

    async def send_json(self, data: Union[Dict, list, str, int, float, bool, None]) -> None:
        """
        Send JSON message with error handling.

        Args:
            data: Data to send as JSON

        Raises:
            Exception: If sending fails
        """
        if not self.is_connected:
            raise RuntimeError("WebSocket is not connected")
        try:
            json_str = json.dumps(data)
            await self.websocket.send_text(json_str)
        except Exception as e:
            logger.error(f"Failed to send JSON message: {str(e)}")
            await self.disconnect(1011, "Failed to send message")
            raise

    async def receive_text(self) -> str:
        """
        Receive text message with error handling.

        Returns:
            Received text message

        Raises:
            Exception: If receiving fails
        """
        if not self.is_connected:
            raise RuntimeError("WebSocket is not connected")
        try:
            return await self.websocket.receive_text()
        except Exception as e:
            logger.error(f"Failed to receive text message: {str(e)}")
            await self.disconnect(1011, "Failed to receive message")
            raise

    async def receive_bytes(self) -> bytes:
        """
        Receive binary message with error handling.

        Returns:
            Received binary data

        Raises:
            Exception: If receiving fails
        """
        if not self.is_connected:
            raise RuntimeError("WebSocket is not connected")
        try:
            return await self.websocket.receive_bytes()
        except Exception as e:
            logger.error(f"Failed to receive binary message: {str(e)}")
            await self.disconnect(1011, "Failed to receive message")
            raise

    async def receive_json(self) -> Any:
        """
        Receive JSON message with error handling.

        Returns:
            Parsed JSON data

        Raises:
            Exception: If receiving fails
        """
        if not self.is_connected:
            raise RuntimeError("WebSocket is not connected")
        try:
            text = await self.websocket.receive_text()
            return json.loads(text)
        except Exception as e:
            logger.error(f"Failed to receive JSON message: {str(e)}")
            await self.disconnect(1011, "Failed to receive message")
            raise


@asynccontextmanager
async def websocket_manager(websocket: WebSocket):
    """
    Context manager for WebSocket connections.

    Args:
        websocket: The WebSocket connection to manage

    Yields:
        WebSocketManager instance
    """
    manager = WebSocketManager(websocket)
    try:
        await manager.connect()
        yield manager
    finally:
        await manager.disconnect()

import asyncio
import base64
import logging
from contextlib import suppress

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
logger = logging.getLogger("api")


# cancel response and wait for cleanup
async def _cancel_response(task: asyncio.Task | None) -> None:
    if task is None or task.done():
        return

    logger.info("[API] cancelling active response")
    task.cancel()
    with suppress(asyncio.CancelledError, Exception):
        await task


# receive audio requests and stream response events over /ws
@router.websocket("/ws")
async def respond(websocket: WebSocket):
    await websocket.accept()
    logger.info("[API] client connected")

    app_state = websocket.app.state
    condition = app_state.condition
    pipeline = app_state.conversation_pipeline

    response_task: asyncio.Task | None = None

    # stream in a task so the connection can still receive stop requests
    async def run_response(audio_bytes: bytes) -> None:
        try:
            async for event in pipeline.respond_streaming(
                audio_bytes=audio_bytes,
                condition=condition,
            ):
                await websocket.send_json(event)
        except asyncio.CancelledError:
            # notify client to stop playback
            with suppress(WebSocketDisconnect, RuntimeError, OSError):
                await websocket.send_json({"type": "stopped"})
            raise
        except Exception as exc:
            logger.error("[API] response generation failed: %s", exc)
            with suppress(WebSocketDisconnect, RuntimeError, OSError):
                await websocket.send_json(
                    {"type": "error", "message": "Response generation failed."}
                )

    try:
        while True:
            request = await websocket.receive_json()
            request_type = request.get("type")

            # stop the active response across all connections
            if request_type == "stop":
                logger.info("[API] stop received")
                await _cancel_response(app_state.active_response)
                continue

            if request_type != "request":
                await websocket.send_json(
                    {"type": "error", "message": "Expected a request message."}
                )
                continue

            # decode audio before starting the pipeline
            try:
                audio_bytes = base64.b64decode(request["audio_b64"], validate=True)
            except (KeyError, TypeError, ValueError):
                await websocket.send_json(
                    {"type": "error", "message": "audio_b64 must contain valid base64 audio."}
                )
                continue

            logger.info("[API] request received")

            # replace the previous response
            await _cancel_response(app_state.active_response)

            response_task = asyncio.create_task(run_response(audio_bytes))
            app_state.active_response = response_task

    except WebSocketDisconnect:
        logger.info("[API] client disconnected")
    except Exception as exc:
        logger.error("[API] unhandled error: %s", exc)
        with suppress(WebSocketDisconnect, RuntimeError, OSError):
            await websocket.send_json(
                {"type": "error", "message": "Response generation failed."}
            )
    finally:
        # disconnect only cancels this connection's response
        await _cancel_response(response_task)
        with suppress(WebSocketDisconnect, RuntimeError, OSError):
            await websocket.close()

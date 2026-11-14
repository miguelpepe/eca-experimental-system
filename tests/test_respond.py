import asyncio
import base64
import threading
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from avatar_backend.api.respond import router


class Pipeline:
    def __init__(self):
        self.started = threading.Event()
        self.cancelled = threading.Event()
        self.sentence = {"type": "sentence", "audio_b64": "", "text": "hello"}

    async def respond_streaming(self, audio_bytes, condition):
        if audio_bytes == b"hold":
            self.started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled.set()
        if audio_bytes == b"fail":
            raise RuntimeError("simulated pipeline failure")
        yield self.sentence
        yield {"type": "done"}


def request(socket, audio=b"sample", **fields):
    socket.send_json({"type": "request", "audio_b64": base64.b64encode(audio).decode(), **fields})


class RespondTests(unittest.TestCase):
    def setUp(self):
        self.pipeline = Pipeline()
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.state.condition = {}
        self.app.state.conversation_pipeline = self.pipeline
        self.app.state.active_response = None

    def test_legacy_request_keeps_original_event_format(self):
        with TestClient(self.app) as client, client.websocket_connect("/ws") as socket:
            request(socket)
            self.assertEqual(socket.receive_json(), self.pipeline.sentence)
            self.assertEqual(socket.receive_json(), {"type": "done"})

    def test_request_id_is_echoed_without_mutating_pipeline_events(self):
        with TestClient(self.app) as client, client.websocket_connect("/ws") as socket:
            request(socket, request_id="new")
            self.assertEqual(socket.receive_json(), {**self.pipeline.sentence, "request_id": "new"})
            self.assertEqual(socket.receive_json(), {"type": "done", "request_id": "new"})
            self.assertNotIn("request_id", self.pipeline.sentence)

    def test_replacement_keeps_old_cancellation_and_new_response_distinct(self):
        with TestClient(self.app) as client, client.websocket_connect("/ws") as socket:
            request(socket, b"hold", request_id="old")
            self.assertTrue(self.pipeline.started.wait(2))
            request(socket, request_id="new")
            self.assertEqual(socket.receive_json(), {"type": "stopped", "request_id": "old"})
            self.assertEqual(socket.receive_json()["request_id"], "new")
            self.assertEqual(socket.receive_json(), {"type": "done", "request_id": "new"})
            self.assertTrue(self.pipeline.cancelled.is_set())

    def test_stop_and_disconnect_cancel_the_pipeline(self):
        with TestClient(self.app) as client, client.websocket_connect("/ws") as socket:
            request(socket, b"hold", request_id="active")
            self.assertTrue(self.pipeline.started.wait(2))
            socket.send_json({"type": "stop"})
            self.assertEqual(socket.receive_json(), {"type": "stopped", "request_id": "active"})
            self.assertTrue(self.pipeline.cancelled.is_set())
        self.pipeline.started.clear()
        self.pipeline.cancelled.clear()
        with TestClient(self.app) as client, client.websocket_connect("/ws") as socket:
            request(socket, b"hold")
            self.assertTrue(self.pipeline.started.wait(2))
        self.assertTrue(self.pipeline.cancelled.wait(2))

    def test_pipeline_error_is_tagged_and_connection_recovers(self):
        with self.assertLogs("api", level="ERROR"):
            with TestClient(self.app) as client, client.websocket_connect("/ws") as socket:
                request(socket, b"fail", request_id="failed")
                event = socket.receive_json()
                self.assertEqual(event["type"], "error")
                self.assertEqual(event["request_id"], "failed")
                request(socket, request_id="recovered")
                self.assertEqual(socket.receive_json()["request_id"], "recovered")
                self.assertEqual(socket.receive_json()["type"], "done")

    def test_invalid_id_and_audio_do_not_close_connection(self):
        with TestClient(self.app) as client, client.websocket_connect("/ws") as socket:
            request(socket, request_id=123)
            self.assertEqual(socket.receive_json()["message"], "request_id must be a string.")
            socket.send_json({"type": "request", "audio_b64": "!!!"})
            self.assertEqual(socket.receive_json()["type"], "error")
            request(socket)
            self.assertEqual(socket.receive_json()["type"], "sentence")
            self.assertEqual(socket.receive_json()["type"], "done")


if __name__ == "__main__":
    unittest.main()

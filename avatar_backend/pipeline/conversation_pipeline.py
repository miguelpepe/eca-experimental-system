import asyncio
import base64
import logging
import re
import threading
import time
from pathlib import Path
from uuid import uuid4

# config values
from avatar_backend.config import (
    MAX_HISTORY_MESSAGES,
    UPLOAD_DIR,
)

# internal modules
from avatar_backend.conversation.manager import ConversationManager
from avatar_backend.llm.openwebui_client import stream_llm
from avatar_backend.stt.whisper_service import stt_with_whisper
from avatar_backend.tts.router import synthesize_speech

logger = logging.getLogger("pipeline")

# regex object to find sentence bounds with . ! ? followed by whitespace
_SENTENCE_BOUNDARY = re.compile(r"[.!?]+\s+")


# returns first complete sentence from text buffer and reminader
def pop_sentence(buffer: str) -> tuple[str, str] | None:

    # regex search for sentence boundary
    match = _SENTENCE_BOUNDARY.search(buffer)
    if not match:
        return None

    # split buffer into sentence and remainder
    sentence_end = match.end()
    sentence = buffer[:sentence_end].rstrip()
    remainder = buffer[sentence_end:]
    return sentence, remainder


# gets llm stream and yields sentences
def split_into_sentences(tokens):
    buffer = ""
    # add tokens to buffer
    for token in tokens:
        buffer += token

        # check for complete sentence
        while True:
            result = pop_sentence(buffer)
            if result is None:
                break

            # yield complete sentence and update buffer with remainder
            sentence, buffer = result
            sentence = sentence.strip()
            if sentence:
                yield sentence

    # yield any final sentence in buffer
    final_sentence = buffer.strip()
    if final_sentence:
        yield final_sentence


# normalize lang from stt to de/en
def normalize_lang(lang: str | None) -> str:
    if lang in ("de", "en"):
        return lang

    return "en"


# orchestrates the full conversation pipeline
class ConversationPipeline:

    # init conversation manager
    def __init__(self):
        self._conversation: ConversationManager | None = None

    # delete conversation context for reset or new participant
    def clear_conversation(self):
        self._conversation = None
        logger.info("[PIPELINE] conversation cleared")

    # init conversation manager if not already done and return it
    def _get_conversation(self, system_prompt: str) -> ConversationManager:
        if self._conversation is None:
            self._conversation = ConversationManager(
                max_messages=MAX_HISTORY_MESSAGES,
                system_prompt=system_prompt,
            )
        return self._conversation

    # starts background threade to stream llm and dont block main event loop
    def _start_sentence_stream(
        self, messages, lang, llm_config, loop
    ) -> tuple[asyncio.Queue, threading.Event]:
        # create ansycio queue for background thread and main event loop
        queue: asyncio.Queue[str | None] = (
            asyncio.Queue()
        )  # str for sentence, None for end of stream

        # set from the outside when the response is cancelled, stops llm consumption early
        stop_event = threading.Event()

        # puts sentnces in queue from background
        def enqueue(item: str | None):
            loop.call_soon_threadsafe(queue.put_nowait, item)

        # prouces sentences in background thread
        def produce_sentences():
            try:
                # starts llm stream and split into sentences
                tokens = stream_llm(messages=messages, lang=lang, llm_config=llm_config)
                # collects tokens into sentences and puts into queuee
                for sentence in split_into_sentences(tokens):
                    # response was cancelled -> stop consuming the llm stream
                    if stop_event.is_set():
                        logger.info("[PIPELINE] llm stream stopped (cancelled)")
                        break
                    logger.info("[PIPELINE] sentence: %r", sentence)
                    enqueue(sentence)
            except Exception as exc:
                logger.error("[LLM] streaming failed: %s", exc)
            finally:
                enqueue(None)  # signal end of stream with None

        # starts background thread for stream llm and sentence splittin
        threading.Thread(target=produce_sentences, daemon=True).start()
        return queue, stop_event

    # entry point for conversation pieline, called from api endpoint, yields sentences with audio as they are produced
    async def respond_streaming(self, audio_bytes: bytes, condition):

        # dict to collect timings for pipeline stages
        timings: dict[str, float] = {}
        t_total = time.perf_counter()

        # create upload dir if not exists and temp file name
        UPLOAD_DIR.mkdir(exist_ok=True)
        tmp_path = UPLOAD_DIR / f"audio_{uuid4().hex}.wav"

        try:
            # --- STT ---
            t = time.perf_counter()
            # save received audio to disk
            tmp_path.write_bytes(audio_bytes)
            timings["upload"] = time.perf_counter() - t

            t = time.perf_counter()
            # run stt and get user text and detected language
            user_text, raw_lang = stt_with_whisper(str(tmp_path), condition["stt"])
            timings["stt"] = time.perf_counter() - t

            lang = normalize_lang(raw_lang)  # normalize to de/en with default en
            logger.info("[PIPELINE] user lang=%s text=%r", lang, user_text)

            # --- CONVERSATION MANAGEMENT ---

            # get conversaation or create new one with system prompt
            conversation = self._get_conversation(condition["system_prompt"])
            # add user message to conversation context
            conversation.add_user(user_text)

            # --- LLM + TTS ---
            loop = asyncio.get_running_loop()  # get current event loop

            # start background thread to stream llm res as sentences in async queue
            sentence_queue, stop_llm = self._start_sentence_stream(
                conversation.get_messages(), lang, condition["llm"], loop
            )

            full_parts: list[str] = []  # sentences to collect full response text
            tts_total = 0.0
            t_llm_start = time.perf_counter()
            idx = 0  # sentence index for order

            try:
                while True:
                    sentence = await sentence_queue.get()  # wait for next sentence

                    # if sentence is None, llm stream ended, break loop
                    if sentence is None:
                        break

                    full_parts.append(sentence)  # add sentence to full response

                    t_tts = time.perf_counter()
                    # synthesize speech for sentence in background thread
                    audio_path, _ = await loop.run_in_executor(
                        None, synthesize_speech, sentence, lang, condition["tts"]
                    )
                    tts_total += time.perf_counter() - t_tts

                    # read audio and encode as base64
                    audio_path = Path(audio_path)
                    audio_b64 = base64.b64encode(audio_path.read_bytes()).decode(
                        "ascii"
                    )  # read audio and encode as base64
                    audio_path.unlink(missing_ok=True)  # delete temp audio file

                    # return sentence with audio as base64 in streaming response
                    yield {
                        "type": "sentence",
                        "index": idx,
                        "text": sentence,
                        "audio_b64": audio_b64,
                    }
                    idx += 1
            except (asyncio.CancelledError, GeneratorExit):
                # response was interrupted (new request / stop / disconnect):
                # stop the llm background thread and keep the partial answer in
                # the conversation history so the context stays consistent
                stop_llm.set()
                if full_parts:
                    conversation.add_assistant(" ".join(full_parts))
                    conversation.trim()
                logger.info("[PIPELINE] response cancelled after %d sentences", idx)
                raise

            # None from queue is end of stream
            timings["llm_and_tts"] = time.perf_counter() - t_llm_start
            timings["tts_total"] = tts_total

            # join full response text and add to conversation context
            full_text = " ".join(full_parts)
            conversation.add_assistant(full_text)
            conversation.trim()  # trim conversation to max history

            # log timings for pipeline stages
            timings["total"] = time.perf_counter() - t_total
            for key, value in timings.items():
                logger.info("[PIPELINE] %s=%.3fs", key, value)

            # send final message with full text and timings, "done" signals end of stream
            yield {
                "type": "done",
                "user": user_text,
                "response": full_text,
                "language": lang,
                "condition": condition["id"],
                "timings": timings,
            }
        # always delete temp file at the end
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

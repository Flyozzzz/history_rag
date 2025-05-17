import asyncio
import websockets
import logging
import json
import re
from typing import Optional

logger = logging.getLogger(__name__)


class AudioTranscriber:
    def __init__(self, ws_uri: str):
        self.ws_uri = ws_uri

    async def transcribe_audio(self, audio_data_base64: str, prompt_text: str = "") -> str:
        try:
            async with websockets.connect(self.ws_uri) as websocket:
                message = {
                    "audio_data": audio_data_base64,
                    "prompt": prompt_text,
                }

                await websocket.send(json.dumps(message))
                await asyncio.sleep(0)

                transcription = await websocket.recv()
                return self._clean_transcription(transcription)
        except Exception as e:
            logger.error(f"[STT] WebSocket connection error: {str(e)}")
            raise

    @staticmethod
    def _clean_transcription(transcription: str) -> str:
        phrases_to_remove = [
            r'Субтитры сделал DimaTorzok',
            r'Субтитры создавал DimaTorzok',
            r'Продолжение следует...'
        ]
        for phrase in phrases_to_remove:
            transcription = re.sub(phrase, '', transcription)
        return transcription


transcriber: Optional[AudioTranscriber] = None

try:
    from app.config import get_settings

    settings = get_settings()
    if settings.stt_ws_url:
        transcriber = AudioTranscriber(ws_uri=settings.stt_ws_url)
except Exception:
    logger.exception("Failed to initialize AudioTranscriber")
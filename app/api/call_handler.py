from fastapi import APIRouter, WebSocket, HTTPException, Depends, Request, Response, BackgroundTasks
from ..services.twilio_service import TwilioService
from ..services.sarvam_service import SarvamAIService
import base64
import json
from typing import Dict, List, Optional
from twilio.twiml.voice_response import VoiceResponse, Connect, Start
import logging
import audioop
import wave
import io
import os
from datetime import datetime
import asyncio
import time

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

router = APIRouter()
twilio_service = TwilioService()
sarvam_service = SarvamAIService()

# Store active WebSocket connections and their state
active_connections: Dict[str, WebSocket] = {}
audio_buffers: Dict[str, List[bytes]] = {}
processing_locks: Dict[str, bool] = {}
background_tasks: Dict[str, asyncio.Task] = {}
speech_states: Dict[str, dict] = {}  # Track speech state for each connection

# Constants for audio processing
SILENCE_THRESHOLD = 200  # RMS threshold for silence detection
MIN_SPEECH_DURATION_MS = 1000  # Minimum speech duration (1 second)
MAX_SPEECH_DURATION_MS = 15000  # Maximum speech duration (15 seconds)
SILENCE_DURATION_MS = 1000  # Duration of silence to mark end of speech
SAMPLES_PER_MS = 8  # At 8kHz sample rate

def is_silence(audio_data: bytes) -> bool:
    """Check if audio chunk is silence"""
    try:
        pcm_data = audioop.ulaw2lin(audio_data, 2)
        rms = audioop.rms(pcm_data, 2)
        return rms < SILENCE_THRESHOLD
    except:
        return True

def get_audio_duration_ms(audio_data: List[bytes]) -> float:
    """Calculate duration of audio in milliseconds"""
    total_bytes = sum(len(chunk) for chunk in audio_data)
    return (total_bytes / 2) / SAMPLES_PER_MS

def convert_audio(audio_data: List[bytes]) -> bytes:
    """Convert mu-law audio chunks to WAV format"""
    try:
        # Convert mu-law to linear PCM
        pcm_data = b''.join([audioop.ulaw2lin(chunk, 2) for chunk in audio_data])
        
        # Create WAV file in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 2 bytes per sample
            wav_file.setframerate(8000)  # 8kHz sample rate
            wav_file.writeframes(pcm_data)
        
        return wav_buffer.getvalue()
    except Exception as e:
        logger.error(f"Error converting audio: {e}")
        raise

def should_process_speech(connection_id: str) -> bool:
    """Determine if we should process the current speech buffer"""
    state = speech_states.get(connection_id, {})
    if not state:
        return False
    
    current_time = time.time() * 1000
    speech_start = state.get('speech_start', current_time)
    last_speech = state.get('last_speech', current_time)
    
    # Calculate durations
    speech_duration = current_time - speech_start
    silence_duration = current_time - last_speech
    
    # Process if:
    # 1. We have enough silence after speech
    # 2. OR we've reached maximum duration
    if speech_duration >= MIN_SPEECH_DURATION_MS:
        if silence_duration >= SILENCE_DURATION_MS or speech_duration >= MAX_SPEECH_DURATION_MS:
            logger.info(f"Processing speech: duration={speech_duration}ms, silence={silence_duration}ms")
            return True
    
    return False

def convert_to_mulaw(wav_data: bytes) -> bytes:
    """Convert WAV audio to mu-law format for Twilio"""
    try:
        # Read WAV data
        with wave.open(io.BytesIO(wav_data), 'rb') as wav_file:
            # Read wav file parameters
            n_channels = wav_file.getnchannels()
            sampwidth = wav_file.getsampwidth()
            framerate = wav_file.getframerate()
            # Read PCM data
            pcm_data = wav_file.readframes(wav_file.getnframes())

        # Convert to mono if needed
        if n_channels == 2:
            pcm_data = audioop.tomono(pcm_data, sampwidth, 1, 1)

        # Convert to 16-bit if needed
        if sampwidth != 2:
            pcm_data = audioop.lin2lin(pcm_data, sampwidth, 2)

        # Resample to 8kHz if needed
        if framerate != 8000:
            pcm_data = audioop.ratecv(pcm_data, 2, 1, framerate, 8000, None)[0]

        # Convert to mu-law
        mu_law_data = audioop.lin2ulaw(pcm_data, 2)
        return mu_law_data
    except Exception as e:
        logger.error(f"Error converting to mu-law: {e}")
        raise

async def process_audio(websocket: WebSocket, connection_id: str, media_data: dict):
    """Process audio in background task"""
    if processing_locks.get(connection_id, False):
        logger.debug("Already processing audio for this connection")
        return
        
    try:
        processing_locks[connection_id] = True
        buffer = audio_buffers[connection_id]
        
        if not buffer:
            return
            
        duration_ms = get_audio_duration_ms(buffer)
        if duration_ms < MIN_SPEECH_DURATION_MS:
            return
            
        logger.info(f"Processing audio buffer of duration {duration_ms}ms")
        
        try:
            # Convert to WAV
            wav_data = convert_audio(buffer)
            
            # Save audio file for debugging
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"recordings/audio_{timestamp}_{int(duration_ms)}ms_{connection_id}.wav"
            with open(filename, "wb") as f:
                f.write(wav_data)
            logger.info(f"Saved audio file: {filename}")
            
            # Clear buffer and reset speech state
            audio_buffers[connection_id] = []
            speech_states[connection_id] = {}
            
            # Process audio through Sarvam AI
            logger.info("Starting speech-to-text translation")
            english_text, original_language = await sarvam_service.transcribe_and_translate_audio(
                audio_data=wav_data
            )
            
            if english_text and len(english_text.strip()) > 0:
                logger.info(f"Speech translated to English: '{english_text}', Original language: {original_language}")
                
                # Get response from OpenAI
                logger.info("Getting response from OpenAI")
                english_response = await sarvam_service.get_openai_response(english_text)
                logger.info(f"OpenAI response: '{english_response}'")
                
                # Translate response if needed
                if original_language != "en-IN" or original_language is not None:
                    logger.info(f"Translating response to {original_language}")
                    translated_response = await sarvam_service.translate_text(
                        input_text=english_response,
                        target_language=original_language,
                        source_language="en-IN"
                    )
                    logger.info(f"Translated response: '{translated_response}'")
                else:
                    translated_response = english_response
                
                # Convert to speech
                logger.info("Converting response to speech")
                response_audio = await sarvam_service.text_to_speech(
                    text=translated_response,
                    target_language=original_language
                )
                
                if response_audio and websocket in active_connections.values():
                    try:
                        # Decode base64 audio
                        wav_bytes = base64.b64decode(response_audio)
                        
                        # Save response WAV for debugging
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        response_filename = f"recordings/response_{timestamp}_{int(duration_ms)}ms_{connection_id}.wav"
                        with open(response_filename, "wb") as f:
                            f.write(wav_bytes)
                        logger.info(f"Saved response WAV file: {response_filename}")
                        
                        # Convert to mu-law format for Twilio
                        mu_law_audio = convert_to_mulaw(wav_bytes)
                        
                        # Save mu-law audio for debugging
                        mulaw_filename = f"recordings/response_{timestamp}_{int(duration_ms)}ms_{connection_id}.ulaw"
                        with open(mulaw_filename, "wb") as f:
                            f.write(mu_law_audio)
                        logger.info(f"Saved mu-law audio file: {mulaw_filename}")
                        
                        # Encode mu-law audio to base64 for Twilio
                        response_payload = base64.b64encode(mu_law_audio).decode('utf-8')
                        
                        # Send audio response in chunks to avoid buffer overflow
                        chunk_size = 640  # 20ms chunks at 8kHz
                        for i in range(0, len(mu_law_audio), chunk_size):
                            chunk = mu_law_audio[i:i + chunk_size]
                            chunk_payload = base64.b64encode(chunk).decode('utf-8')
                            
                            # Send chunk to Twilio
                            await websocket.send_text(json.dumps({
                                "event": "media",
                                "streamSid": media_data["streamSid"],
                                "media": {
                                    "payload": chunk_payload
                                }
                            }))
                            
                            # Small delay between chunks
                            await asyncio.sleep(0.02)  # 20ms delay between chunks
                            
                        logger.info("Audio response sent successfully in chunks")
                        
                    except Exception as e:
                        logger.error(f"Error handling response audio: {e}")
                else:
                    logger.error("No response audio generated or websocket disconnected")
            else:
                logger.info("No speech detected in audio")
        
        except Exception as e:
            logger.error(f"Error processing audio chunk: {str(e)}")
            # Don't clear buffer on error unless it's too long
            if duration_ms >= MAX_SPEECH_DURATION_MS:
                audio_buffers[connection_id] = []
                speech_states[connection_id] = {}
    
    except Exception as e:
        logger.error(f"Error in process_audio: {e}")
    
    finally:
        processing_locks[connection_id] = False

@router.websocket("/ws/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle WebSocket connection for media streaming"""
    connection_id = str(id(websocket))
    logger.info(f"New WebSocket connection: {connection_id}")
    
    await websocket.accept()
    logger.info(f"WebSocket connection accepted: {connection_id}")
    
    try:
        # Initialize connection state
        active_connections[connection_id] = websocket
        audio_buffers[connection_id] = []
        processing_locks[connection_id] = False
        speech_states[connection_id] = {}
        
        while True:
            # Receive audio data from Twilio
            data = await websocket.receive_text()
            media_data = json.loads(data)
            
            if media_data.get("event") == "media":
                # Process audio chunk
                audio_data = base64.b64decode(media_data["media"]["payload"])
                current_time = time.time() * 1000
                
                # Update speech state based on silence detection
                is_silent = is_silence(audio_data)
                state = speech_states.get(connection_id, {})
                
                if not is_silent:
                    # Speech detected
                    if not state:
                        # Start of new speech
                        state = {
                            'speech_start': current_time,
                            'last_speech': current_time
                        }
                    else:
                        # Continue speech
                        state['last_speech'] = current_time
                    speech_states[connection_id] = state
                    
                    # Add audio to buffer
                    audio_buffers[connection_id].append(audio_data)
                    
                    # Check if we should process (max duration reached)
                    if should_process_speech(connection_id):
                        await process_audio(websocket, connection_id, media_data)
                else:
                    # Silence detected
                    if state:
                        # Add silence to buffer
                        audio_buffers[connection_id].append(audio_data)
                        
                        # Check if we should process (enough silence after speech)
                        if should_process_speech(connection_id):
                            await process_audio(websocket, connection_id, media_data)
                
            elif media_data.get("event") == "start":
                logger.info("Media stream started")
            elif media_data.get("event") == "stop":
                logger.info("Media stream stopped")
                # Process any remaining audio
                if audio_buffers[connection_id]:
                    await process_audio(websocket, connection_id, media_data)
            elif media_data.get("event") == "mark":
                logger.info(f"Received mark event: {media_data.get('type')}")
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    
    finally:
        # Clean up connection
        if connection_id in active_connections:
            del active_connections[connection_id]
        if connection_id in audio_buffers:
            del audio_buffers[connection_id]
        if connection_id in processing_locks:
            del processing_locks[connection_id]
        if connection_id in speech_states:
            del speech_states[connection_id]
        if connection_id in background_tasks:
            task = background_tasks[connection_id]
            if not task.done():
                task.cancel()
            del background_tasks[connection_id]
        logger.info(f"WebSocket connection closed and cleaned up: {connection_id}")
        try:
            await websocket.close()
        except:
            pass

@router.post("/voice")
async def handle_incoming_call(request: Request):
    """Handle incoming Twilio calls with TwiML response"""
    try:
        logger.info("Incoming call received")
        form_data = await request.form()
        
        # Get call information
        from_number = form_data.get('From', 'Unknown')
        from_city = form_data.get('FromCity', 'Unknown City')
        logger.info(f"Call from {from_number} in {from_city}")
        
        # Create TwiML response
        response = VoiceResponse()
        
        # Add initial greeting
        response.say("Welcome to 99phones. Please speak in any language, and I'll respond.")
        
        # Start media stream with explicit parameters
        start = Start()
        stream = start.stream(
            url=f"wss://{request.headers.get('host')}/ws/media-stream",
            track="inbound_track"
        )
        # Add stream parameters
        stream.parameter(name="format", value="mulaw")
        stream.parameter(name="rate", value="8000")
        
        response.append(start)
        
        # Add a pause to keep the call alive
        response.pause(length=3600)  # Keep the call alive for up to an hour
        
        logger.info("Generated TwiML response")
        logger.debug(f"TwiML: {str(response)}")
        
        # Return TwiML response
        return Response(content=str(response), media_type="application/xml")
    
    except Exception as e:
        logger.error(f"Error handling incoming call: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/outbound-call")
async def create_outbound_call(call_data: dict):
    """Create an outbound call"""
    try:
        logger.info(f"Creating outbound call: {call_data}")
        call = twilio_service.create_call(
            to_number=call_data["to"],
            webhook_url=call_data["webhook_url"],
            from_number=call_data.get("from")  # Optional from_number
        )
        logger.info(f"Outbound call created successfully: {call.sid}")
        return {"call_sid": call.sid}
    except Exception as e:
        logger.error(f"Error creating outbound call: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 
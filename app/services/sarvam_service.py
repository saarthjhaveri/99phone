import os
import base64
import json
import logging
import httpx
import tempfile
from openai import OpenAI
from typing import Tuple, Optional

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SarvamAIService:
    def __init__(self):
        self.api_key = os.getenv("SARVAM_API_KEY")
        self.base_url = "https://api.sarvam.ai"
        self.openai_client = OpenAI()
        
        if not self.api_key:
            raise ValueError("SARVAM_API_KEY environment variable not set")
    
    async def transcribe_and_translate_audio(self, audio_data: bytes, prompt: str = None) -> Tuple[Optional[str], Optional[str]]:
        """
        Transcribe audio and translate to English if needed.
        Returns (transcript, language_code)
        """
        try:
            # Create temporary file to store audio data
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name

            # Prepare files and data
            files = {
                'file': ('audio.wav', open(temp_file_path, 'rb'), 'audio/wav')
            }
            
            data = {
                'model': 'saaras:v1'
            }
            
            if prompt:
                data['prompt'] = prompt
            
            headers = {
                'api-subscription-key': self.api_key
            }
            
            # Make API request
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/speech-to-text-translate",
                    files=files,
                    data=data,
                    headers=headers,
                    timeout=30.0
                )
                
                # Clean up temp file
                os.unlink(temp_file_path)
                
                if response.status_code == 200:
                    result = response.json()
                    transcript = result.get("transcript", "")
                    language_code = result.get("language_code", "en-IN")
                    
                    # Return empty if no speech detected
                    if not transcript:
                        logger.info("No speech detected in audio")
                        return None, None
                        
                    return transcript.strip(), language_code
                else:
                    logger.error(f"Sarvam AI API error: {response.status_code} - {response.text}")
                    return None, None
                    
        except Exception as e:
            logger.error(f"Error in transcribe_and_translate_audio: {str(e)}")
            return None, None
    
    async def translate_text(
        self,
        input_text: str,
        target_language: str,
        source_language: str = "en-IN",
        speaker_gender: str = "Male",
        mode: str = "formal"
    ) -> Optional[str]:
        """Translate text using Sarvam AI"""
        try:
            payload = {
                "input": input_text,
                "source_language_code": source_language,
                "target_language_code": target_language,
                "speaker_gender": speaker_gender,
                "mode": mode,
                "model": "mayura:v1",
                "enable_preprocessing": True
            }
            
            headers = {
                "Content-Type": "application/json",
                "api-subscription-key": self.api_key
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/translate",
                    json=payload,
                    headers=headers,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    translated_text = result.get("translated_text")
                    if translated_text:
                        return translated_text.strip()
                    return input_text
                else:
                    logger.error(f"Translation error: {response.status_code} - {response.text}")
                    return input_text
                    
        except Exception as e:
            logger.error(f"Error in translate_text: {str(e)}")
            return input_text
    
    async def text_to_speech(
        self,
        text: str,
        target_language: str = "en-IN",
        speaker: str = "meera"
    ) -> Optional[str]:
        """Convert text to speech using Sarvam AI"""
        try:
            # Truncate text to 500 characters
            text = text[:500]
            
            # Translate text if target language is not English
            if target_language != "en-IN":
                translated_text = await self.translate_text(
                    input_text=text,
                    target_language=target_language,
                    source_language="en-IN"
                )
                if translated_text:
                    text = translated_text[:500]
            
            logger.info(f"Sending TTS request for text: '{text}' in language: {target_language}")
            
            payload = {
                "inputs": [text],
                "target_language_code": target_language,
                "speaker": speaker,
                "model": "bulbul:v1"
            }
            
            headers = {
                "Content-Type": "application/json",
                "api-subscription-key": self.api_key
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/text-to-speech",
                    json=payload,
                    headers=headers,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("audios"):
                        # Get base64 audio and verify it's valid
                        audio_base64 = result["audios"][0]
                        try:
                            # Verify base64 can be decoded
                            audio_bytes = base64.b64decode(audio_base64)
                            logger.info(f"Successfully generated audio of size: {len(audio_bytes)} bytes")
                            return audio_base64
                        except Exception as e:
                            logger.error(f"Invalid base64 audio data: {e}")
                            return None
                    logger.error("No audio in response")
                    return None
                else:
                    logger.error(f"TTS error: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error in text_to_speech: {str(e)}")
            return None
    
    async def get_openai_response(self, user_message: str) -> str:
        """Get response from OpenAI"""
        try:
            # Create system message for context
            system_message = """You are a helpful assistant in a phone conversation. 
            Keep your responses concise and natural, as they will be spoken back to the user.
            Aim to keep responses under 2-3 sentences unless more detail is specifically requested."""
            
            # Get completion from OpenAI
            completion = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=150,
                temperature=0.7
            )
            
            # Extract and return the response
            response = completion.choices[0].message.content.strip()

            print("response from openai for the query is ", response)
            return response
            
        except Exception as e:
            logger.error(f"Error getting OpenAI response: {str(e)}")
            return "I apologize, but I'm having trouble processing your request at the moment. Could you please try again?"
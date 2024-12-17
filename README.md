# 99phones - Real-time Voice Call Processing

A FastAPI application that implements real-time speech-to-text and text-to-speech functionality for phone calls using Twilio and Sarvam AI. This system can handle multilingual voice interactions, making it perfect for building voice-based applications that need to work across multiple Indian languages.

## Features

- Real-time speech-to-text using Sarvam AI
- Automatic language detection and translation
- Text-to-speech response in the detected language
- Twilio integration for phone call handling
- WebSocket-based media streaming
- Support for multiple Indian languages
- Real-time voice processing with silence detection
- Background task processing for audio handling

## Prerequisites

- Python 3.8+
- Twilio account with a phone number
- Sarvam AI API key
- OpenAI API key (for chat completions)
- ngrok or similar tool for local development

## Tech Stack

- **FastAPI**: High-performance web framework for building APIs
- **Twilio**: For handling phone calls and voice interactions
- **Sarvam AI**: For speech-to-text and text-to-speech processing
- **WebSocket**: For real-time audio streaming
- **OpenAI**: For generating conversational responses
- **Python**: Core programming language

## Project Structure

```
99phone/
├── app/
│   ├── api/
│   │   └── call_handler.py    # Call handling endpoints
│   ├── services/
│   │   ├── sarvam_service.py  # Sarvam AI integration
│   │   └── twilio_service.py  # Twilio integration
│   └── main.py               # FastAPI application entry point
├── requirements.txt          # Project dependencies
└── .env                     # Environment variables
```

## Setup Instructions

1. Clone the repository:
```bash
git clone <repository-url>
cd 99phone
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file with the following variables:
```env
# Server Configuration
HOST=0.0.0.0
PORT=8000

# Sarvam AI Configuration
SARVAM_API_KEY=your_sarvam_api_key
SARVAM_API_URL=https://api.sarvam.ai/v1

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key

# Twilio Configuration
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=your_twilio_phone_number
```

5. Start the development server:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

6. (For local development) Start ngrok:
```bash
ngrok http 8000
```

## API Endpoints

### HTTP Endpoints

- `GET /health`: Health check endpoint
- `POST /incoming-call`: Handles incoming Twilio calls
- `POST /outbound-call`: Initiates outbound calls

### WebSocket Endpoints

- `WS /ws/media-stream`: Handles real-time audio streaming

## Making Test Calls

1. Configure your Twilio webhook URL:
   - Go to your Twilio Console
   - Select your phone number
   - Set the Voice Webhook URL to: `https://your-ngrok-url/incoming-call`
   - Method: POST

2. Make a test call:
   - Call your Twilio phone number
   - Speak in any supported language
   - The system will:
     - Convert your speech to text
     - Process the text
     - Generate a response
     - Convert the response to speech
     - Play it back to you

## Supported Languages

The system supports the following Indian languages:
- Hindi (hi-IN)
- Bengali (bn-IN)
- Kannada (kn-IN)
- Malayalam (ml-IN)
- Marathi (mr-IN)
- Odia (od-IN)
- Punjabi (pa-IN)
- Tamil (ta-IN)
- Telugu (te-IN)
- Gujarati (gu-IN)
- English (en-IN)

## Audio Processing Parameters

The system uses the following parameters for optimal voice detection:
- Silence threshold: 200 RMS
- Minimum speech duration: 1000ms
- Maximum speech duration: 15000ms
- Silence duration for end detection: 1000ms
- Sample rate: 8kHz

## Development

### Running Tests
```bash
pytest
```

### Code Style
The project follows PEP 8 guidelines. Format your code using:
```bash
black .
```

## Troubleshooting

1. **WebSocket Connection Issues**
   - Ensure your ngrok tunnel is running
   - Check if the WebSocket URL matches your ngrok URL
   - Verify SSL/TLS settings if using HTTPS

2. **Audio Processing Issues**
   - Check the audio format (must be μ-law encoded)
   - Verify sample rate (8kHz expected)
   - Monitor silence threshold settings

3. **API Integration Issues**
   - Verify all API keys are correctly set in .env
   - Check API endpoint URLs
   - Monitor API rate limits

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Sarvam AI for their speech processing capabilities
- Twilio for their telephony infrastructure
- FastAPI for the excellent web framework
- OpenAI for chat completions
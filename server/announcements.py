import json
import random
import asyncio
from datetime import datetime
from elevenlabs import play
from elevenlabs.client import ElevenLabs
import anthropic
import logging
from fastapi import APIRouter
from pydantic import BaseModel

from server.constants import PROMPTS_FILE, ELEVENLABS_API_KEY, WELCOME_END_TIME, WELCOME_START_TIME
from server.telemetry import send_message
from server.auth import Flatmate


try:
    with open(PROMPTS_FILE, 'r') as file:
        _USER_WELCOME_PROMPTS: dict[str, list[str]] = json.load(file)
except FileNotFoundError:
    _USER_WELCOME_PROMPTS = {}

elevenlabs_client = ElevenLabs(
    api_key=ELEVENLABS_API_KEY,
)

_logger = logging.getLogger(__name__)
router = APIRouter()

async def generate_welcome(prompt):
    anthropic_client = anthropic.AsyncAnthropic()
    message = await anthropic_client.messages.create(
        model="claude-3-opus-20240229",
        max_tokens=300,
        temperature=0.7,
        system=(
            "This is a conversation between a user and a welcoming bot/assistant, "
            "the assistant creates welcome messages for people to the Tower House "
            "Apartment in London. The welcome messages should be at maximum 1 sentence long."
        ),
        messages=[
            {"role": "user", "content": f"Write welcome for: {prompt}"}
        ]
    )

    assert message.content[0].type == "text"
    msg = message.content[0].text
    return msg

async def generate_and_play_audio(text, voice="Chris", model="eleven_multilingual_v2"):
    audio = elevenlabs_client.generate(
        text=text,
        voice=voice,
        model=model
    )

    play(audio)

async def poem_to_speech(prompt: str, delay: float=1.0):
    await asyncio.sleep(delay)
    welcome = await generate_welcome(prompt)
    asyncio.create_task(generate_and_play_audio(welcome))

def play_announcement_if_prompt_exists(user: str):
    if user in _USER_WELCOME_PROMPTS:
        current_time = datetime.now().time()
        if WELCOME_START_TIME <= current_time < WELCOME_END_TIME:
            # If a string, set that as the prompt, if a list, choose a random one
            prompt = _USER_WELCOME_PROMPTS[user]
            if isinstance(prompt, list):
                prompt = random.choice(prompt)
            asyncio.create_task(poem_to_speech(prompt, delay=8))


class AnnouncementModel(BaseModel):
    message: str

@router.post("/api/announce")
async def announce(announcement: AnnouncementModel, flatmate: Flatmate):
    _logger.info(f"{flatmate} made an announcement: {announcement.message}")
    asyncio.create_task(generate_and_play_audio(announcement.message))
    send_message(f"Announcement from {flatmate}: {announcement.message}")
    return {"message": "Announcement made successfully"}

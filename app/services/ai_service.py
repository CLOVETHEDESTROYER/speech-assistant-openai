import openai
from log import logger

async def get_ai_response(conversation_text: str) -> str:
    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant having a phone conversation."},
                {"role": "user", "content": conversation_text}
            ],
            max_tokens=100,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI API error: {str(e)}")
        return "I apologize, but I'm having trouble processing that right now."

async def text_to_speech(text: str) -> bytes:
    try:
        response = await openai.Audio.create(
            model="tts-1",
            voice="alloy",
            input=text
        )
        return response.content
    except Exception as e:
        logger.error(f"Text-to-speech error: {str(e)}")
        return b""  # Return empty bytes on error 
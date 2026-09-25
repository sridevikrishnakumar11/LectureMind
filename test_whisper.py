from models.speech_to_text import convert_audio_to_text

audio = "uploads/sample.mp3"

text = convert_audio_to_text(audio)

print(text)
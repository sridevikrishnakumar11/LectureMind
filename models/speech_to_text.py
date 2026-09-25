import whisper


def convert_audio_to_text(audio_path):

    model = whisper.load_model("base")

    result = model.transcribe(audio_path)

    text = result["text"]

    return text
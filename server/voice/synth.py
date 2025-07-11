import io
import wave
import base64
from piper import PiperVoice, SynthesisConfig
import re


# Load model once globally
_voice = PiperVoice.load(
    "server/voice/en_US-ryanTTS-medium.onnx",
    config_path="server/voice/en_US-ryanTTS-medium.onnx.json",
    use_cuda=False  # Set to True if you're using GPU + onnxruntime-gpu
)

_config = SynthesisConfig(
    volume=1.0,
    length_scale=1.0,
    noise_scale=0.667,
    noise_w_scale=0.8,
    normalize_audio=True,
)

def synthesize_to_base64(text: str) -> str:
    """Generate TTS from text and return base64-encoded .wav bytes"""
    # remove asterisks and dashes from text and any http links and [BUTTON|view_project_images|View Images]
    text = text.replace('*', '')
    text = text.replace('-', '')
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'\[BUTTON\|.*?\|View [^\]]+\]', '', text)
    wav_bytes = io.BytesIO()
    with wave.open(wav_bytes, "wb") as wav_file:
        _voice.synthesize_wav(text, wav_file, syn_config=_config)
    wav_bytes.seek(0)
    return base64.b64encode(wav_bytes.read()).decode("utf-8")

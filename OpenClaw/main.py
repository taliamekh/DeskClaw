import json
import os
import re
from dotenv import load_dotenv

load_dotenv()


def resolve_env_vars(obj):
    """Recursively replace ${VAR_NAME} placeholders with environment variables."""
    if isinstance(obj, str):
        match = re.fullmatch(r"\$\{(\w+)}", obj)
        if match:
            value = os.getenv(match.group(1))
            if not value:
                raise ValueError(f"{match.group(1)} not found in environment variables")
            return value
        return obj
    elif isinstance(obj, dict):
        return {k: resolve_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [resolve_env_vars(item) for item in obj]
    return obj


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "openclaw.json")
    with open(config_path) as f:
        config = json.load(f)

    return resolve_env_vars(config)


if __name__ == "__main__":
    config = load_config()
    print("Config loaded successfully")
    print(f"Top-level keys: {list(config.keys())}")
    if "stt" in config:
        print(f"STT provider: {config['stt']['provider']}")
    if "tts" in config:
        print(f"TTS provider: {config['tts']['provider']}")
        print(f"TTS voice: {config['tts']['voice_id']}")

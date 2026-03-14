import os
import google.genai as genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Test with a working model
try:
    response = client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents="Explain what a robotic claw does"
    )
    print("Success with models/gemini-2.5-flash!")
    print(response.text)
except Exception as e:
    print(f"Error: {e}")
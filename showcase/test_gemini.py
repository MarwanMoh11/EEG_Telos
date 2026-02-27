import os
import sys

# Try to load the key directly from the environment
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'neuro_reflex'))
from dotenv import load_dotenv

# Let's load the showcase .env specifically
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

api_key = os.getenv("GEMINI_API_KEY")

print(f"\n--- API TEST SCRIPT ---")
print(f"Key loaded from env: {'YES' if api_key else 'NO'}")
if api_key:
    # Print just the first few chars to verify it's the right key
    print(f"Key preview: {api_key[:5]}...{api_key[-5:]}")

try:
    from google import genai
    from google.genai import types
    
    print("GenAI SDK successfully imported.")
    
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model='gemini-2.5-flash-lite',
        contents='Say hello world',
    )
    print("\nSUCCESS: " + response.text)
except Exception as e:
    print(f"\nAPI ERROR DETAILS:")
    import traceback
    traceback.print_exc()

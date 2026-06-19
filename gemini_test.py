import os
import json
from dotenv import load_dotenv
from google import genai

def main():
    # Load environment variables from .env file
    load_dotenv()
    
    # Ensure GEMINI_API_KEY is available
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in environment variables.")
        return

    # Initialize the Gemini client
    client = genai.Client(api_key=api_key)
    
    audio_file_path = "test_clip.wav"
    
    if not os.path.exists(audio_file_path):
        print(f"Error: Could not find audio file '{audio_file_path}' in the current directory.")
        return

    try:
        print(f"Uploading {audio_file_path}...")
        uploaded_file = client.files.upload(file=audio_file_path)
    except Exception as e:
        print(f"Error uploading file: {e}")
        return

    prompt = """Please transcribe the audio exactly as spoken, preserving any mix of English, Hindi, or Marathi.
Then, based on the transcript and audio, output a JSON object with the following fields:
- transcript (string)
- objection_detected (bool)
- price_concern (bool)
- certification_question (bool)
- upsell_miss (bool)
- knowledge_gap (bool)
- intent_signal (bool)
- alert_priority (string: one of "none", "low", "medium", "high")
- reasoning (string: short explanation)

Respond with ONLY the JSON object, no markdown fences (like ```json), no preamble, and no extra text.
"""

    print("Sending request to gemini-2.5-flash...")
    try:
        # Generate content using the new google-genai SDK
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[uploaded_file, prompt],
        )
        
        # Clean up the output in case the model ignored instructions and added fences
        response_text = response.text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()
            
        parsed_json = json.loads(response_text)
        print("\n--- Result ---")
        print(json.dumps(parsed_json, indent=2, ensure_ascii=False))
        
    except json.JSONDecodeError as e:
        print(f"\nError parsing JSON response: {e}")
        print("Raw response:")
        print(response_text if 'response_text' in locals() else response.text)
    except Exception as e:
        print(f"\nError generating content: {e}")

if __name__ == "__main__":
    main()

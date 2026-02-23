import os
import time
import logging
import json
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class BurnoutDetector:
    """Uses Gemini 2.5 Flash Lite to track cognitive load and issue systemic interventions."""
    
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            logger.error("❌ GEMINI_API_KEY NOT FOUND! Please add it to your .env file.")
            # We don't initialize the client if the key is missing to avoid the ValueError crash
            self.client = None
        else:
            self.client = genai.Client(api_key=self.api_key) 
        self.model_id = 'gemini-2.5-flash-lite'
        
        self.last_query_time = time.time()
        self.mandatory_interval_seconds = 5 * 60 # 5 minutes
        
        # Enforce valid JSON and strict command schemas
        self.system_instruction = (
            "You are the Telos Neuro-Reflex Engine. Output ONLY valid JSON. "
            "Analyze the user's current cognitive load and continuous duration. "
            "Return exactly one JSON object with this key: 'action'. "
            "The value must be exactly one of: 'maintain', 'nudge_break', or 'enable_antigravity'."
        )
        
    def check_burnout(self, focus_probability: float, high_load_minutes: float) -> dict:
        """
        Evaluates local conditions before triggering a cloud LLM query.
        Returns empty dict if no query was made, or the parsed JSON from Gemini.
        """
        current_time = time.time()
        time_since_last_query = current_time - self.last_query_time
        
        needs_query = False
        reason = ""
        
        # Rule 1: Periodic Check
        if time_since_last_query >= self.mandatory_interval_seconds:
            needs_query = True
            reason = "Periodic 5-minute health check."
            
        # Rule 2: Critical Condition
        elif focus_probability < 0.4 and high_load_minutes > 20.0:
            # Throttle critical checks to maximum 1 per minute so we don't spam the API
            # while the user remains in this state.
            if time_since_last_query >= 60.0:
                needs_query = True
                reason = "Focus dropped below 0.4 and fatigue threshold exceeded."
                
        if not needs_query:
            return {}
            
        self.last_query_time = current_time
        logger.info(f"Triggering Gemini Burnout Evaluation. Reason: {reason}")
        
        # Privacy filter: Keep all prompts strictly anonymous and generic
        prompt = (
            f"User Profile Context: High-Cognitive Load Work.\n"
            f"Current Focus Level: {focus_probability:.2f} / 1.00\n"
            f"Continuous High-Load Duration: {high_load_minutes:.1f} minutes.\n\n"
            "Assess current mental state. Should we 'maintain' current state, "
            "'nudge_break' for minor fatigue, or 'enable_antigravity' for burnout prevention?"
        )
        
        try:
            # We use the modern 'google-genai' schema
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    temperature=0.1,  # Keep it deterministic
                    response_mime_type="application/json",
                )
            )
            
            output_text = response.text
            parsed_json = json.loads(output_text)
            
            action_str = parsed_json.get("action", "maintain")
            
            # Map back to a clean dictionary
            result = {
                "action": action_str,
                "reason_triggered": reason
            }
            logger.info(f"Gemini Decision: {result}")
            return result
            
        except json.JSONDecodeError:
            logger.error("Gemini failed to return valid JSON.")
            return {}
        except Exception as e:
            logger.error(f"Gemini API failure during reasoning inference: {e}")
            return {}

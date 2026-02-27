import os
import time
import logging
import json
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class MentalStateClassifier:
    """Uses Gemini 2.5 Flash Lite as an advanced on-demand mental state classifier."""
    
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            logger.error("❌ GEMINI_API_KEY NOT FOUND! Please add it to your .env file.")
            self.client = None
        else:
            self.client = genai.Client(api_key=self.api_key) 
        self.model_id = 'gemini-2.5-flash-lite'
        
        # Enforce valid JSON and strict command schemas
        self.system_instruction = (
            "You are the Telos Neuro-Reflex Engine's advanced AI Classifier. Output ONLY valid JSON. "
            "Analyze the provided raw EEG metrics (Focus, Alpha/Beta, Asymmetry) and physical artifact states. "
            "Return exactly one JSON object with two keys: "
            "1. 'state': A 1-3 word discrete label of their immediate mental/physical/emotional state (e.g., 'Deep Flow', 'Active Problem Solving', 'Mental Fatigue', 'Jaw Clenching', 'Eye Blinking', 'High Motivation', 'Deep Frustration'). "
            "If the artifact state is 'clench_hard' or 'clench_mild', prioritize 'Jaw Clenching' or 'Muscle Tension'. "
            "If the artifact state is 'blink', prioritize 'Eye Blinking'. "
            "If the Hemispheric Alpha Asymmetry is strongly positive (>= 0.2), highly prioritize labels like 'Positive Approach' or 'High Motivation'. "
            "If the Hemispheric Alpha Asymmetry is strongly negative (<= -0.2), highly prioritize labels like 'Negative Withdrawal' or 'Deep Frustration'. "
            "Otherwise, base the state on the Focus and Alpha/Beta ratios. "
            "2. 'insight': A single, incisive sentence explaining your classification based on the provided metrics. Do not exceed one sentence."
        )
        
    def classify_state(self, focus_probability: float, alpha_power: float, beta_power: float, alpha_asymmetry: float, noise_level: str = "clean", artifact_state: str = "relaxed") -> dict:
        """
        Sends an immediate API request to classify the current multi-dimensional metrics.
        Returns the parsed JSON from Gemini.
        """
        if not self.client:
            return {"state": "API_KEY_MISSING", "insight": "Cannot classify without Gemini API key."}
            
        logger.info("Triggering On-Demand Gemini Mental State Classification.")
        
        # Privacy filter: Keep all prompts strictly anonymous and generic
        prompt = (
            f"User Profile Context: High-Performance BCI User.\n"
            f"Current Focus Level: {focus_probability:.2f} / 1.00\n"
            f"Total Alpha Band Power (Relaxation/Idling): {alpha_power:.2f}\n"
            f"Total Beta Band Power (Active Thinking/Stress): {beta_power:.2f}\n"
            f"Hemispheric Alpha Asymmetry (C3 vs C4, + motivation, - frustration): {alpha_asymmetry:.2f}\n"
            f"Signal Noise Level: {noise_level.upper()}\n"
            f"Physical Artifact State: {artifact_state.upper()}\n\n"
            "Assess current mental state immediately."
        )
        
        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    temperature=0.3,  # Slight creativity for label generation
                    response_mime_type="application/json",
                )
            )
            
            output_text = response.text
            parsed_json = json.loads(output_text)
            
            result = {
                "state": parsed_json.get("state", "Unknown State"),
                "insight": parsed_json.get("insight", "Could not parse AI insight.")
            }
            logger.info(f"Gemini Classification: {result}")
            return result
            
        except json.JSONDecodeError:
            logger.error("Gemini failed to return valid JSON.")
            return {"state": "JSON_ERROR", "insight": "AI failed to return valid JSON."}
        except Exception as e:
            logger.error(f"Gemini API failure during reasoning inference: {e}")
            return {"state": "API_ERROR", "insight": f"Connection to Gemini failed: {e}"}

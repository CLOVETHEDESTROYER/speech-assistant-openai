"""
Enhanced Random Scenario Service with advanced dynamic generation features.
Includes contextual awareness, learning algorithms, and adaptive persona creation.
"""

import logging
import random
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import User, RandomCallPreferences, GeneratedScenario, Conversation
from app.services.random_scenario_service import RandomScenarioService

logger = logging.getLogger(__name__)


class EnhancedScenarioService(RandomScenarioService):
    """Enhanced scenario service with learning and contextual awareness."""
    
    def __init__(self, openai_api_key: str = None):
        super().__init__(openai_api_key)
        self.contextual_scenarios = self._load_contextual_scenarios()
    
    def _load_contextual_scenarios(self) -> Dict:
        """Load contextual scenario templates for different situations."""
        return {
            "seasonal": {
                "winter": {
                    "themes": ["cozy", "reflection", "planning"],
                    "contexts": ["holiday preparations", "year-end planning", "indoor activities"]
                },
                "spring": {
                    "themes": ["renewal", "energy", "growth"],
                    "contexts": ["new beginnings", "outdoor activities", "cleaning and organizing"]
                },
                "summer": {
                    "themes": ["adventure", "relaxation", "social"],
                    "contexts": ["vacation planning", "outdoor events", "travel stories"]
                },
                "fall": {
                    "themes": ["nostalgia", "preparation", "gratitude"],
                    "contexts": ["back to school", "harvest season", "reflection on achievements"]
                }
            },
            "time_of_day": {
                "morning": {
                    "energy": "high",
                    "focus": ["planning", "motivation", "fresh starts"],
                    "personas": ["energetic coach", "morning coffee friend", "productivity guru"]
                },
                "afternoon": {
                    "energy": "moderate",
                    "focus": ["check-ins", "problem-solving", "casual conversation"],
                    "personas": ["colleague on break", "friendly neighbor", "project collaborator"]
                },
                "evening": {
                    "energy": "relaxed",
                    "focus": ["reflection", "unwinding", "social connection"],
                    "personas": ["close friend", "wise mentor", "evening companion"]
                }
            },
            "day_of_week": {
                "monday": {
                    "mood": "motivational",
                    "themes": ["fresh start", "goal setting", "overcoming challenges"]
                },
                "wednesday": {
                    "mood": "supportive", 
                    "themes": ["mid-week check-in", "encouragement", "progress review"]
                },
                "friday": {
                    "mood": "celebratory",
                    "themes": ["accomplishments", "weekend planning", "relaxation"]
                },
                "sunday": {
                    "mood": "reflective",
                    "themes": ["week reflection", "preparation", "self-care"]
                }
            }
        }
    
    def get_contextual_enhancements(self, current_time: datetime = None) -> Dict:
        """Get contextual enhancements based on current time and season."""
        if current_time is None:
            current_time = datetime.utcnow()
        
        # Determine season
        month = current_time.month
        if month in [12, 1, 2]:
            season = "winter"
        elif month in [3, 4, 5]:
            season = "spring"
        elif month in [6, 7, 8]:
            season = "summer"
        else:
            season = "fall"
        
        # Determine time of day context
        hour = current_time.hour
        if 5 <= hour < 12:
            time_period = "morning"
        elif 12 <= hour < 17:
            time_period = "afternoon"
        else:
            time_period = "evening"
        
        # Determine day of week
        day_name = current_time.strftime("%A").lower()
        
        return {
            "season": season,
            "time_period": time_period,
            "day_name": day_name,
            "seasonal_context": self.contextual_scenarios["seasonal"].get(season, {}),
            "time_context": self.contextual_scenarios["time_of_day"].get(time_period, {}),
            "day_context": self.contextual_scenarios["day_of_week"].get(day_name, {})
        }
    
    def analyze_user_preferences(self, user_id: int, db: Session) -> Dict:
        """Analyze user's historical preferences and call patterns."""
        try:
            # Get user's scenario history
            scenarios = db.query(GeneratedScenario).filter(
                GeneratedScenario.user_id == user_id
            ).order_by(GeneratedScenario.created_at.desc()).limit(20).all()
            
            if not scenarios:
                return {"preferences": "new_user", "patterns": {}}
        except Exception as e:
            logger.warning(f"Could not analyze user preferences: {e}")
            return {"preferences": "new_user", "patterns": {}}
        
        # Analyze ratings and usage patterns
        avg_rating = db.query(func.avg(GeneratedScenario.user_rating)).filter(
            GeneratedScenario.user_id == user_id,
            GeneratedScenario.user_rating.isnot(None)
        ).scalar() or 0
        
        # Find preferred themes
        theme_ratings = {}
        for scenario in scenarios:
            if scenario.themes_used and scenario.user_rating:
                for theme in scenario.themes_used:
                    if theme not in theme_ratings:
                        theme_ratings[theme] = []
                    theme_ratings[theme].append(scenario.user_rating)
        
        # Calculate average rating per theme
        preferred_themes = []
        for theme, ratings in theme_ratings.items():
            avg_theme_rating = sum(ratings) / len(ratings)
            if avg_theme_rating >= 4.0:  # High-rated themes
                preferred_themes.append(theme)
        
        # Analyze conversation duration patterns
        avg_duration = 0
        try:
            conversations = db.query(Conversation).filter(
                Conversation.user_id == user_id,
                Conversation.duration.isnot(None)
            ).limit(10).all()
            
            if conversations:
                avg_duration = sum(c.duration for c in conversations) / len(conversations)
        except Exception as e:
            logger.warning(f"Could not analyze conversation patterns: {e}")
            avg_duration = 120  # Default to 2 minutes
        
        return {
            "avg_rating": avg_rating,
            "preferred_themes": preferred_themes,
            "avg_conversation_duration": avg_duration,
            "total_scenarios": len(scenarios),
            "engagement_level": "high" if avg_duration > 180 else "moderate" if avg_duration > 60 else "low"
        }
    
    def generate_enhanced_scenario(
        self, 
        user_id: int, 
        preferences: RandomCallPreferences,
        db: Session,
        time_context: str = "daytime"
    ) -> GeneratedScenario:
        """Generate an enhanced scenario with contextual awareness and learning."""
        
        # Get contextual enhancements
        context = self.get_contextual_enhancements()
        
        # Analyze user preferences
        user_analysis = self.analyze_user_preferences(user_id, db)
        
        # Create enhanced generation prompt
        enhanced_prompt = self._build_enhanced_prompt(
            preferences, context, user_analysis, time_context
        )
        
        try:
            # Call GPT-4-turbo with enhanced prompt
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert character creator specializing in personalized, contextually-aware personas for meaningful social interactions. Create personas that adapt to seasonal contexts, time of day, user preferences, and engagement patterns. Always return valid JSON."
                    },
                    {
                        "role": "user",
                        "content": enhanced_prompt
                    }
                ],
                max_completion_tokens=1200,
                temperature=0.8,
                response_format={"type": "json_object"}
            )
            
            # Parse and validate response
            content = response.choices[0].message.content
            persona_data = json.loads(content)
            
            # Enhanced validation with contextual fields
            required_fields = ["name", "age", "gender", "persona", "prompt"]
            for field in required_fields:
                if field not in persona_data:
                    raise ValueError(f"Missing required field: {field}")
            
            # Select voice based on enhanced criteria
            voice_type = self._select_enhanced_voice(persona_data, context, user_analysis)
            
            # Create scenario with enhanced metadata
            scenario = GeneratedScenario(
                user_id=user_id,
                persona=persona_data["persona"],
                prompt=persona_data["prompt"],
                voice_type=voice_type,
                temperature=0.8,
                themes_used=preferences.persona_themes or ["casual"],
                generation_model=self.model,
                # Enhanced fields
                context_metadata=json.dumps({
                    "season": context["season"],
                    "time_period": context["time_period"],
                    "day_name": context["day_name"],
                    "user_engagement_level": user_analysis.get("engagement_level", "moderate"),
                    "preferred_themes_used": user_analysis.get("preferred_themes", [])
                })
            )
            
            db.add(scenario)
            db.commit()
            db.refresh(scenario)
            
            logger.info(f"Generated enhanced scenario {scenario.id} for user {user_id}")
            return scenario
            
        except Exception as e:
            logger.error(f"Error generating enhanced scenario: {str(e)}", exc_info=True)
            # Fallback to basic scenario generation
            return super().generate_scenario(user_id, preferences, db, time_context)
    
    def _build_enhanced_prompt(
        self, 
        preferences: RandomCallPreferences, 
        context: Dict, 
        user_analysis: Dict,
        time_context: str
    ) -> str:
        """Build an enhanced generation prompt with contextual awareness."""
        
        base_themes = preferences.persona_themes or ["casual"]
        exclude_themes = preferences.exclude_themes or []
        user_context = preferences.user_context or "a person interested in conversation"
        
        # Add contextual themes
        contextual_themes = []
        if context["seasonal_context"]:
            contextual_themes.extend(context["seasonal_context"].get("themes", []))
        if context["time_context"]:
            contextual_themes.extend(context["time_context"].get("focus", []))
        
        # Incorporate user learning
        preferred_themes = user_analysis.get("preferred_themes", [])
        engagement_level = user_analysis.get("engagement_level", "moderate")
        
        prompt = f"""Create a unique, engaging persona for a random social call with these enhanced parameters:

CONTEXTUAL AWARENESS:
- Season: {context["season"]} - incorporate {context["seasonal_context"].get("themes", [])}
- Time of day: {context["time_period"]} - energy level: {context["time_context"].get("energy", "moderate")}
- Day: {context["day_name"]} - mood: {context["day_context"].get("mood", "friendly")}

USER PERSONALIZATION:
- User context: {user_context}
- Preferred interaction themes: {base_themes}
- Avoid these themes: {exclude_themes}
- User engagement level: {engagement_level}
- Historically preferred themes: {preferred_themes}

ENHANCED REQUIREMENTS:
- Create a persona that fits the {context["season"]} season and {context["time_period"]} energy
- Incorporate {context["day_context"].get("mood", "friendly")} mood for {context["day_name"]}
- Design conversation topics that match the seasonal context: {context["seasonal_context"].get("contexts", [])}
- Adapt complexity and energy to user engagement level: {engagement_level}

CONVERSATION PURPOSE OPTIONS:
{self._get_contextual_purposes(context)}

Return JSON with:
{{
    "name": "character name",
    "age": age (20-65),
    "gender": "male/female/non-binary",
    "persona": "detailed character description with seasonal and contextual awareness",
    "prompt": "comprehensive prompt including seasonal context, time-appropriate energy, and personalized conversation topics",
    "personality_traits": ["trait1", "trait2", "trait3"],
    "conversation_goals": ["goal1", "goal2"],
    "seasonal_adaptation": "how this character fits the current season/time"
}}

Make this persona feel like a real person who would naturally call during {context["season"]} {context["time_period"]} on a {context["day_name"]} with genuine interest in connecting."""
        
        return prompt
    
    def _get_contextual_purposes(self, context: Dict) -> str:
        """Get contextual conversation purposes based on time and season."""
        purposes = []
        
        # Seasonal purposes
        season = context["season"]
        if season == "winter":
            purposes.extend([
                "Sharing cozy indoor activity ideas",
                "Discussing year-end reflections",
                "Planning for the new year"
            ])
        elif season == "spring":
            purposes.extend([
                "Talking about new beginnings and fresh starts",
                "Sharing spring cleaning and organization tips",
                "Discussing outdoor activity plans"
            ])
        elif season == "summer":
            purposes.extend([
                "Planning summer adventures",
                "Sharing travel experiences",
                "Discussing outdoor hobbies and activities"
            ])
        else:  # fall
            purposes.extend([
                "Reflecting on achievements and growth",
                "Discussing preparation for upcoming changes",
                "Sharing gratitude and appreciation"
            ])
        
        # Time-based purposes
        time_period = context["time_period"]
        if time_period == "morning":
            purposes.extend([
                "Morning motivation and goal setting",
                "Planning the day ahead",
                "Sharing energizing routines"
            ])
        elif time_period == "afternoon":
            purposes.extend([
                "Mid-day check-in and encouragement",
                "Problem-solving and brainstorming",
                "Casual conversation and connection"
            ])
        else:  # evening
            purposes.extend([
                "Reflecting on the day's experiences",
                "Unwinding and relaxation conversation",
                "Planning for tomorrow"
            ])
        
        return "- " + "\n- ".join(purposes)
    
    def _select_enhanced_voice(self, persona_data: Dict, context: Dict, user_analysis: Dict) -> str:
        """Select voice based on enhanced criteria including context and user preferences."""
        
        # Get base voice selection
        base_voice = super()._select_voice_for_persona(persona_data)
        
        # Adjust based on time context
        time_energy = context["time_context"].get("energy", "moderate")
        engagement_level = user_analysis.get("engagement_level", "moderate")
        
        # Voice mapping with contextual awareness
        voice_adjustments = {
            ("morning", "high"): ["alloy", "echo"],  # Energetic voices for morning high energy
            ("evening", "relaxed"): ["coral", "sage"],  # Calmer voices for evening
            ("afternoon", "moderate"): ["ballad", "onyx"]  # Balanced voices for afternoon
        }
        
        # Adjust for user engagement
        if engagement_level == "high":
            energy_voices = ["alloy", "echo", "ballad"]
            if base_voice not in energy_voices:
                return random.choice(energy_voices)
        elif engagement_level == "low":
            calm_voices = ["coral", "sage", "onyx"]
            if base_voice not in calm_voices:
                return random.choice(calm_voices)
        
        return base_voice

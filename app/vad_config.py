"""
Voice Activity Detection (VAD) Configuration Module

This module provides centralized VAD configuration management with support for
both server_vad and semantic_vad modes, including the new eagerness parameter.
"""


class VADConfig:
    """Centralized VAD configuration management"""

    # Default configurations for different use cases
    DEFAULT_SERVER_VAD = {
        "type": "server_vad",
        "threshold": 0.5,
        "prefix_padding_ms": 300,
        "silence_duration_ms": 500,
        "create_response": True,
        "interrupt_response": True
    }

    DEFAULT_SEMANTIC_VAD = {
        "type": "semantic_vad",
        "eagerness": "auto",  # "low", "medium", "high", "auto"
        "create_response": True,
        "interrupt_response": True
    }

    # Optimized configurations for different scenarios
    CONVERSATIONAL_VAD = {
        "type": "semantic_vad",
        "eagerness": "low",  # Let users speak uninterrupted
        "create_response": True,
        "interrupt_response": True
    }

    RESPONSIVE_VAD = {
        "type": "semantic_vad",
        "eagerness": "high",  # Quick responses
        "create_response": True,
        "interrupt_response": True
    }

    NOISY_ENVIRONMENT_VAD = {
        "type": "server_vad",
        "threshold": 0.7,  # Higher threshold for noisy environments
        "prefix_padding_ms": 200,
        "silence_duration_ms": 800,
        "create_response": True,
        "interrupt_response": True
    }

    @staticmethod
    def get_vad_config(vad_type: str = "semantic_vad", eagerness: str = "auto",
                       threshold: float = 0.5, prefix_padding_ms: int = 300,
                       silence_duration_ms: int = 700) -> dict:
        """
        Get VAD configuration based on type and parameters

        Args:
            vad_type: "server_vad" or "semantic_vad"
            eagerness: "low", "medium", "high", "auto" (for semantic_vad)
            threshold: Activation threshold 0-1 (for server_vad)
            prefix_padding_ms: Audio padding before VAD detection (for server_vad)
            silence_duration_ms: Silence duration to detect speech stop (for server_vad)
        """
        if vad_type == "semantic_vad":
            config = VADConfig.DEFAULT_SEMANTIC_VAD.copy()
            config["eagerness"] = eagerness
            return config
        elif vad_type == "server_vad":
            config = VADConfig.DEFAULT_SERVER_VAD.copy()
            config["threshold"] = threshold
            config["prefix_padding_ms"] = prefix_padding_ms
            config["silence_duration_ms"] = silence_duration_ms
            return config
        else:
            raise ValueError(f"Unsupported VAD type: {vad_type}")

    @staticmethod
    def get_scenario_vad_config(scenario_name: str) -> dict:
        """Get VAD configuration optimized for specific scenarios"""
        scenario_lower = scenario_name.lower()

        # Conversational scenarios - let users speak naturally
        if any(keyword in scenario_lower for keyword in ["therapy", "counseling", "interview", "conversation"]):
            return VADConfig.CONVERSATIONAL_VAD

        # Quick response scenarios - more responsive
        elif any(keyword in scenario_lower for keyword in ["support", "help", "emergency", "urgent"]):
            return VADConfig.RESPONSIVE_VAD

        # Default to semantic VAD with auto eagerness
        else:
            return VADConfig.DEFAULT_SEMANTIC_VAD

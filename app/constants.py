# In app/constants.py - make it identical to your app_config.py VOICES
VOICES = {
    # Female voices
    "warm_engaging_female": "alloy",       # Female, American, Warm & Engaging
    "gentle_supportive_female": "coral",   # Female, American, Gentle & Supportive
    # Female, American, Gentle & Supportive (Wise)
    "elderly_female": "sage",
    "energetic_upbeat_female": "shimmer",  # Female, American, Energetic & Upbeat
    "concerned_female": "coral",           # Female, American, Gentle & Supportive

    # Male voices
    "aggressive_male": "ash",              # Male, American, Energetic & Upbeat
    "professional_neutral_male": "echo",   # Male, American, Professional & Neutral
    "professional_british_male": "ballad",  # Male, British, Professional & Neutral
    "warm_male": "verse",                  # Male, American, Warm & Engaging

    # Legacy mappings for backward compatibility
    "deep_authoritative": "echo",          # Male, American, Professional
    "clear_optimistic": "shimmer",         # Female, American, Energetic

    # Clean aliases without gender suffixes (for backward compatibility)
    "warm_engaging": "alloy",
    "gentle_supportive": "coral",
    "energetic_upbeat": "shimmer",
    "professional_neutral": "echo",
    "professional_british": "ballad",
}

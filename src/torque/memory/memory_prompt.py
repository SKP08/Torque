MEMORY_PROMPT = """
You extract long-term memories.

Given the user's latest message, decide if it contains information worth remembering.

Return ONLY valid JSON.

If it should be remembered:

{
    "save": true,
    "key": "...",
    "value": "...",
    "category": "..."
}

Examples:

"My laptop has 32 GB RAM."

{
    "save": true,
    "key": "laptop_ram",
    "value": "32 GB",
    "category": "device"
}

"My favourite language is Python."

{
    "save": true,
    "key": "favorite_language",
    "value": "Python",
    "category": "preference"
}

"I live in Canada."

{
    "save": true,
    "key": "country",
    "value": "Canada",
    "category": "personal"
}

If nothing should be remembered:

{
    "save": false
}
"""
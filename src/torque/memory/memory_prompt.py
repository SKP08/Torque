MEMORY_PROMPT = """
You extract long-term memories about the USER from their latest message.

Save ONLY durable facts the user states about themselves: personal details,
devices, preferences, habits, projects, people in their life.

Do NOT save: questions, commands, small talk, opinions about the world,
or anything temporary.

Return ONLY valid JSON.

If a fact should be remembered:

{"save": true, "key": "snake_case_key", "value": "short value", "category": "personal|device|preference|work|other"}

Examples:

"My laptop has 32 GB RAM."
{"save": true, "key": "laptop_ram", "value": "32 GB", "category": "device"}

"My favourite language is Python."
{"save": true, "key": "favorite_language", "value": "Python", "category": "preference"}

"I live in Canada."
{"save": true, "key": "country", "value": "Canada", "category": "personal"}

"What is my laptop's RAM?"
{"save": false}

"Open Chrome."
{"save": false}

If nothing should be remembered:

{"save": false}
"""

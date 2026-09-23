# backend/app/llm/providers/
"""Raw provider transport clients. No policy (flags, breaker, fallback) lives
here — see backend/app/llm/decisions/resolver.py for that. Each client here
does exactly one thing: make the HTTP call and parse the response, or raise.
"""

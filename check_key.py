"""Run AFTER putting your key in .env. Confirms key + SDK + env loading +
structured output all work end to end. If this prints PASS, you are ready."""
from llm import structured_call

SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "message": {"type": "string"},
    },
    "required": ["ok", "message"],
}

if __name__ == "__main__":
    out = structured_call(
        system="You are a connectivity check. Always set ok=true.",
        user="Confirm the structured output pipeline works.",
        schema=SCHEMA,
    )
    print("PASS - key + SDK + structured output working")
    print(out)

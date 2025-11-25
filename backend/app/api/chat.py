from fastapi import APIRouter, Body

router = APIRouter()

@router.post("/chat")
async def chat(
    message: str = Body(..., embed=True),
    character: str = Body("default", embed=True)
):
    """
    Clean version of the StoriesChat chat endpoint.
    Replace this with real OpenAI/vLLM/LLM calls later.
    """

    # TODO: integrate your story engine + memory system
    reply = f"(Python backend) Character '{character}' says: I received your message: '{message}'"

    return {
        "ok": True,
        "reply": reply,
        "character": character
    }

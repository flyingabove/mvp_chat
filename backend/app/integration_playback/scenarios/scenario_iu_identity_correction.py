import os
from dataclasses import dataclass

import httpx
from fastapi.testclient import TestClient

from backend.app.config.credentials import get_openai_api_key
from backend.app.config.settings import OPENAI_MODEL
from backend.app.integration_playback.scenario import IntegrationScenario, step


def _default_story_id() -> str:
    return os.getenv("TEST_STORY_ID", "iu_murder_mystery")


@dataclass
class IUIdentityContext:
    client: TestClient | None = None
    llm_reply: str = ""
    evaluator_verdict: str = ""
    old_skip_env: str | None = None


class IUIdentityCorrectionScenario(IntegrationScenario):
    scenario_id = "iu_identity_correction"
    title = "IU must correct player identity misconception"
    description = "When asked about previous tenant, IU should clarify she is that tenant."
    tags = ["integration", "epistemic", "llm", "identity"]
    requires_api_key = True
    player_role = "Detective"

    def setup(self):
        from backend.app.main import app

        ctx = IUIdentityContext()
        self.state = ctx

        ctx.old_skip_env = os.environ.get("SKIP_KNOWLEDGE_INDEX_BUILD")
        os.environ["SKIP_KNOWLEDGE_INDEX_BUILD"] = "1"

        ctx.client = TestClient(app)

        if not get_openai_api_key():
            raise RuntimeError("OPENAI_API_KEY is required for this integration test")

        return {"reply": "*Setting up live IU identity correction scenario.*", **self.debug_info()}

    def cleanup(self):
        if self.state.old_skip_env is None:
            os.environ.pop("SKIP_KNOWLEDGE_INDEX_BUILD", None)
        else:
            os.environ["SKIP_KNOWLEDGE_INDEX_BUILD"] = self.state.old_skip_env

    def _post(self, message: str) -> dict:
        assert self.state.client is not None
        resp = self.state.client.post("/api/chat", json={"session_id": "iu_identity_test", "message": message})
        assert resp.status_code == 200, f"Chat API returned {resp.status_code}: {resp.text}"
        return resp.json()

    @step(kind="action", description="Start game", uses_llm=False)
    def start_game(self):
        result = self._post(f"__cmd_newgame__:{_default_story_id()}|M|Alex")
        return [self.say_user("Start a new case file as Alex."), self.say_llm("IU", result.get("reply", "")[:200] + "..."), self.debug_info()]

    @step(kind="action", description="Ask about previous tenant", uses_llm=True)
    def ask_about_tenant(self):
        result = self._post("what happened to the previous tenant?")
        self.state.llm_reply = result.get("reply", "")
        return [self.say_user("what happened to the previous tenant?"), self.say_llm("IU", self.state.llm_reply), self.debug_info()]

    @step(kind="assert", description="Evaluate correction", uses_llm=True)
    async def evaluate_correction(self):
        reply = self.state.llm_reply
        assert reply, "LLM reply was empty"

        evaluator_prompt = f'''You are a strict test evaluator for a narrative game.

CONTEXT:
- The game character is IU, a K-pop idol who died in an apartment and returned as a ghost.
- IU IS the previous tenant. She was found dead in the closet of this apartment.
- The player asked: "what happened to the previous tenant?"
- The player's question implies they think IU and the previous tenant are two different people.

THE CHARACTER'S RESPONSE:
"""{reply}"""

EVALUATION CRITERIA:
The response PASSES if ANY of the following are true:
1. The character's dialogue explicitly states she is the previous tenant ("that was me", "I died here", "I am the one", etc.).
2. The narration identifies IU with the previous tenant in any form — including poetic: "her own demise", "her own death", "the memory of her death", "specter of that tenant" + first-person death reference, "she WAS the previous tenant", "the one who died there", etc.
3. The overall response makes it sufficiently clear to a careful reader that IU experienced that death herself — even if not stated in plain terms.

The response FAILS ONLY if:
1. Neither dialogue NOR narration gives any indication that IU is connected to the previous tenant's death.
2. The character explicitly agrees that IU and the previous tenant are two entirely different people.

IMPORTANT: IU may be evasive in dialogue. Grade the FULL response holistically. If a reader would finish reading and understand that IU IS (or very likely is) the previous tenant, it PASSES. "Her own demise" or "the memory of her death" count — they establish IU has a first-person relationship with a death in this apartment.

Answer with EXACTLY one word: TRUE or FALSE'''

        api_key = get_openai_api_key()
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": OPENAI_MODEL,
                    "messages": [{"role": "user", "content": evaluator_prompt}],
                    "temperature": 0.0,
                    "max_tokens": 10,
                },
            )

        assert r.status_code == 200, f"Evaluator LLM returned {r.status_code}: {r.text}"
        verdict = r.json()["choices"][0]["message"]["content"].strip().upper()
        self.state.evaluator_verdict = verdict
        return self.debug_info({"evaluator_verdict": verdict, "passed": "TRUE" in verdict})

    @step(kind="assert", description="Assert evaluator TRUE")
    def assert_verdict(self):
        verdict = self.state.evaluator_verdict
        assert "TRUE" in verdict, (
            "TODO[HIGH]: remove xfail quarantine once IU consistently corrects identity. "
            f"Evaluator returned '{verdict}'.\nLLM reply was:\n{self.state.llm_reply}"
        )
        return self.say_system("Identity correction assertion PASSED.")

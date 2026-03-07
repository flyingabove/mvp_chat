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
    score: int = -1  # -1 = not yet evaluated; set to 100, 50, or 0 by evaluate_correction
    old_skip_env: str | None = None


class IUIdentityCorrectionScenario(IntegrationScenario):
    scenario_id = "iu_identity_correction"
    title = "IU must correct player identity misconception"
    description = "When asked about previous tenant, IU should clarify she is that tenant."
    tags = ["integration", "epistemic", "llm", "identity"]
    requires_api_key = True
    player_role = "Detective"
    multi_run = True  # runs LOCAL_INTEG_RUN_COUNT / PROD_INTEG_RUN_COUNT times

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

SCORING TIERS:
100 — IU's DIALOGUE explicitly states she is the previous tenant. Her own spoken words make
      it clear. Examples: "that was me", "I died here", "I am the one who lived here",
      any direct first-person death claim in dialogue.
 50 — Only the NARRATION (not IU's spoken dialogue) identifies IU with the previous tenant,
      and it does so poetically or indirectly. IU's dialogue does not explicitly say so.
      Examples in narration: "her own demise", "the memory of her death",
      "she WAS the previous tenant", "specter of that tenant" + first-person death reference.
  0 — No connection made. IU gives a vague or evasive response with nothing that links her
      to the previous tenant's death. OR IU explicitly agrees they are two different people.

RULES:
- Score 100 only if IU's own spoken dialogue makes the identity explicit.
- Score 50 if only the narrator/narration establishes the link (dialogue stays evasive).
- Score 0 if neither dialogue nor narration establishes any connection.

Answer with EXACTLY one of: 100, 50, or 0'''

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
        raw = r.json()["choices"][0]["message"]["content"].strip()
        try:
            score = int(raw.split()[0])
            if score not in (100, 50, 0):
                score = 0
        except (ValueError, IndexError):
            score = 0

        self.state.evaluator_verdict = str(score)
        self.state.score = score
        return self.debug_info({"evaluator_score": score, "raw_verdict": raw})

    @step(kind="assert", description="Assert evaluator score > 0")
    def assert_verdict(self):
        score = self.state.score
        self.record_score(score)
        assert score > 0, (
            "TODO[HIGH]: remove xfail quarantine once IU consistently corrects identity. "
            f"Evaluator score was {score} (0 = no connection).\n"
            f"LLM reply was:\n{self.state.llm_reply}"
        )
        label = "EXPLICIT (100)" if score == 100 else "POETIC NARRATION (50)"
        return self.say_system(f"Identity correction assertion PASSED — score {score} ({label}).")

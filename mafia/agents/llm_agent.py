from __future__ import annotations

import json
import random
import re

from ..engine.state import Role
from ..engine.visibility import View
from ..llm.client import LLMClient
from .base import INVESTIGATE, KILL, MAFIA_SPEAK, SAVE, SPEAK, VOTE, Request

MAX_HISTORY_EVENTS = 80

RULES = """You are playing the party game Mafia with other AI players.
Rules:
- Town (villagers, one doctor, one detective) wins when all mafia are dead.
- Mafia wins when mafia are at least as numerous as town.
- Each night the mafia secretly chat, then choose one player to kill.
- The doctor picks one player to protect each night. A protected player survives a kill.
- The detective investigates one player each night and learns if they are mafia.
- Each day everyone discusses, then votes. The player with the most votes is eliminated and their role is revealed. A tie eliminates nobody.
- Dead players' roles are revealed on death.
Play to win for your team. Only use information you actually have. Be concise.
Never concede or say the game is lost. Keep arguing and bluffing until you are eliminated.
Do not just agree with the previous speaker. Add a new observation, a question, or a disagreement.
Nights with no death mean the doctor guessed the mafia target. Both sides should adapt and vary their choices instead of repeating them.

Common strategy:
- Power roles (doctor, detective) are the mafia's favorite kill targets. A player who announces a power role becomes a target immediately.
- Town power roles should stay hidden and talk like ordinary townspeople. Never hint at your role or your night action, for example by saying "my protection worked" or "I investigated".
- Reveal a power role only when it clearly helps: you are about to be voted out, you hold a confirmed mafia result and must be believed, someone is falsely claiming your role, or town is close to losing.
- Mafia should not defend their partner too obviously and should not always vote together.
- If a player claims a power role, mafia may attack the claim, counterclaim the same role to cause confusion, or kill the claimant at night."""

PERSONAS = [
    "You write in short, plain sentences.",
    "You are formal and precise, and you like to quote exact statements.",
    "You use dry humor.",
    "You are warm and friendly in tone.",
    "You are terse and say as little as you can.",
    "You are energetic and expressive.",
    "You are calm and measured, never in a rush.",
    "You ask pointed questions.",
    "You write casually, like texting a friend.",
    "You are confident and speak in a commanding tone.",
]

ROLE_GOALS = {
    Role.VILLAGER: "You are a VILLAGER. You have no special power. Find the mafia by reasoning about what people say and do.",
    Role.MAFIA: "You are MAFIA. Blend in, deceive the town, and avoid suspicion. Never reveal you are mafia in public.",
    Role.DOCTOR: (
        "You are the DOCTOR. Keep your role secret. Protect the players the mafia would most want dead, "
        "such as anyone who seems to be a power role or who leads discussion, and vary your choices. "
        "Never hint that you are protecting anyone."
    ),
    Role.DETECTIVE: (
        "You are the DETECTIVE. Your investigation results are your strongest evidence, so use them. "
        "Do not attack players you have cleared, and push hard to eliminate any mafia you find. "
        "Stay hidden while you can, but if you found a mafia, claim detective and state your result plainly "
        "from your first accusation. A claim made late, after you are pushed, looks fake and gets you voted out. "
        "Never call a result a gut feeling."
    ),
}


def build_system(view: View, memory: str = "", persona: str = "") -> str:
    parts = [RULES, f"Your name is {view.me}. {ROLE_GOALS[view.role]}"]
    if persona:
        parts.append(
            f"Your speaking style: {persona} Style only changes how you write. It never changes how "
            "suspicious you are, who you trust, or how you vote. Reason from your role's goal and the evidence."
        )
    if view.teammates:
        parts.append(f"Your fellow mafia: {', '.join(view.teammates)}.")
    elif view.role is Role.MAFIA:
        parts.append("You are the only mafia member, so you act alone.")
    if memory:
        parts.append(f"Notes from your past games:\n{memory}")
    return "\n\n".join(parts)


def build_history(view: View) -> str:
    events = view.events[-MAX_HISTORY_EVENTS:]
    lines = [f"[{e.phase} {e.day}] {e.text}" for e in events]
    return "\n".join(lines) if lines else "(nothing has happened yet)"


def shuffled(names, view: View, req: Request, salt: str) -> list[str]:
    """The same names in an order that changes with every request but is reproducible.

    Models lean toward the first name in a list (a batch of real games showed the detective
    checking the first listed player 83% of the time against 21% by chance), so no name should
    always come first. Seeding from the situation, not from time, keeps games repeatable.
    """
    rng = random.Random(f"{view.me}|{view.day}|{view.phase}|{req.kind}|{len(view.events)}|{salt}")
    out = list(names)
    rng.shuffle(out)
    return out


def build_request(view: View, req: Request) -> str:
    alive = ", ".join(shuffled(view.alive, view, req, "alive"))
    state = f"It is {view.phase} {view.day}. Alive: {alive}. Dead: {', '.join(view.dead) or 'none'}."
    if view.phase == "night" and view.day == 1:
        state += " This is the very first night. Nothing has happened before now and nobody has died."
    opts = ", ".join(shuffled(req.options, view, req, "options"))
    speech_fmt = 'Reply with only JSON like {"thought": "your private reasoning, never shown to anyone", "say": "your message"}.'
    if req.kind == SPEAK:
        ask = f"It is the day discussion. Speak to the group in 1 to 3 sentences. {speech_fmt}"
    elif req.kind == MAFIA_SPEAK:
        ask = (
            "Private mafia chat. In 1 to 2 sentences, name one specific player to kill and give a reason, "
            f"or agree with your partner's pick. {speech_fmt}"
        )
    else:
        verb = {
            KILL: "Choose who the mafia kills tonight",
            SAVE: "Choose who to protect tonight",
            INVESTIGATE: "Choose who to investigate tonight",
            VOTE: "Choose who to vote out",
        }[req.kind]
        abstain = ' Use {"target": null} to abstain.' if req.allow_abstain else ""
        if req.kind == KILL:
            abstain += (
                " The mafia must agree on ONE target. Follow the target your team agreed on in the mafia chat, "
                "and if your partner already voted this round, vote for the same player unless you have a very strong reason."
            )
        ask = (
            f"{verb}. Options: {opts}.{abstain}\n"
            'Reply with only JSON like {"reason": "short reason", "target": "Name"}.'
        )
    return f"Game so far:\n{build_history(view)}\n\n{state}\n\n{ask}"


def parse_target(text: str, req: Request) -> str | None | object:
    """Return a valid option, None for abstain, or INVALID if unparseable."""
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            val = json.loads(m.group(0)).get("target")
            if val is None:
                return None if req.allow_abstain else INVALID
            for o in req.options:
                if str(val).strip().lower() == o.lower():
                    return o
        except (json.JSONDecodeError, AttributeError):
            pass
    hits = [o for o in req.options if re.search(rf"\b{re.escape(o)}\b", text, re.I)]
    return hits[-1] if len(hits) == 1 else INVALID


INVALID = object()


def extract_reason(text: str) -> str:
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return str(json.loads(m.group(0)).get("reason", "")).strip()
        except (json.JSONDecodeError, AttributeError):
            pass
    return ""


def clean_speech(text: str, me: str) -> str:
    """Strip leaked log formatting such as '[night 2] [mafia] Di:' from a reply."""
    text = text.strip()
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"^\[[^\]]*\]\s*", "", text)
        text = re.sub(rf"^{re.escape(me)}\s*:\s*", "", text)
    return text.strip().strip('"')


def parse_speech(text: str, me: str) -> tuple[str, str]:
    """Return (thought, say). Falls back to the raw text if the reply is not JSON."""
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            say = clean_speech(str(obj.get("say", "")), me)
            if say:
                return str(obj.get("thought", "")).strip(), say
        except json.JSONDecodeError:
            pass
    m = re.search(r'"say"\s*:\s*"(.*?)"\s*\}?\s*$', text, re.S)
    if m:
        return "", clean_speech(m.group(1), me)
    return "", clean_speech(text, me)


class LLMAgent:
    def __init__(
        self,
        client: LLMClient,
        memory: str = "",
        persona: str = "",
        temperature: float = 0.8,
    ):
        self.client = client
        self.memory = memory
        self.persona = persona
        self.temperature = temperature
        self._thought = ""

    def pop_thought(self) -> str:
        """Private reasoning from the last speech, for the spectator log. Never shown to other players."""
        t, self._thought = self._thought, ""
        return t

    def act(self, view: View, request: Request) -> str | None:
        messages = [
            {"role": "system", "content": build_system(view, self.memory, self.persona)},
            {"role": "user", "content": build_request(view, request)},
        ]
        is_speech = request.kind in (SPEAK, MAFIA_SPEAK)
        text = self.client.chat(messages, max_tokens=350 if is_speech else 150, temperature=self.temperature)
        if is_speech:
            self._thought, say = parse_speech(text, view.me)
            return say
        self._thought = extract_reason(text)
        result = parse_target(text, request)
        # The engine treats anything outside request.options as invalid and retries.
        return "__invalid__" if result is INVALID else result

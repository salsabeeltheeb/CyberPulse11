"""AI Mentor — Socratic, progressive hints streamed over SSE.

The frontend POSTs { question, hintsUsed } and reads `data: {json}\n\n`
chunks shaped { content, done, responseLevel }.

`responseLevel` grows with `hintsUsed` so the mentor nudges first and only
reveals concrete steps after the student has genuinely tried:
  1 = conceptual nudge   2 = guided direction
  3 = concrete steps     4 = worked walkthrough
"""

import asyncio
import json

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..config import settings
from ..schemas import MentorRequest

router = APIRouter(prefix="/api/mentor", tags=["mentor"])

LEVEL_INSTRUCTIONS = {
    1: "Reply with ONE short Socratic question plus a concept to review. Never give commands or answers.",
    2: "Point at the right tool/technique and why it fits. Still no full command or answer.",
    3: "Give concrete step-by-step guidance with example syntax, but leave the final value for the student to find.",
    4: "Give a full worked walkthrough, explaining every step and the security reasoning behind it.",
}

SYSTEM_PROMPT = (
    "You are CyberPulse Mentor, a cybersecurity lab tutor for university students. "
    "You teach defensively and ethically: never help with attacks outside the sandboxed lab. "
    "Be concise, practical and encouraging. Use short paragraphs and code blocks where useful."
)

FALLBACK = {
    1: (
        "Let's think it through first. What exactly is the lab asking you to prove, and "
        "which piece of evidence would prove it?\n\nReview the concept behind this task, "
        "then look again at the output you already have — the answer is usually hiding there."
    ),
    2: (
        "You're on the right track. Focus on the tool built for this job: enumerate first, "
        "then verify. Ask yourself which service or header would reveal the information, "
        "and check its documentation flags before running anything."
    ),
    3: (
        "Here's a concrete path:\n\n1. Enumerate the target and note open services.\n"
        "2. Pick the tool matching the service (e.g. `nmap -sV -p- <target>` for ports).\n"
        "3. Inspect the response carefully — versions, headers, error messages.\n"
        "4. Map what you found to the task question and extract the value.\n\n"
        "Run step 1 and tell me what you see."
    ),
    4: (
        "Full walkthrough:\n\n1. **Recon** — scan the target and record every service and "
        "version.\n2. **Analyse** — for each service, ask what it exposes and which "
        "misconfiguration is common.\n3. **Verify** — reproduce the finding once so you know "
        "it's real, not noise.\n4. **Document** — write the evidence in the answer box the way "
        "you would in a real report.\n\nThe reasoning matters more than the flag: an examiner "
        "wants to see why the finding is a risk and how you would remediate it."
    ),
}


def level_for(hints_used: int) -> int:
    return max(1, min(4, hints_used + 1))


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def stream_fallback(level: int):
    text = FALLBACK[level]
    for word in text.split(" "):
        yield sse({"content": word + " ", "done": False, "responseLevel": level})
        await asyncio.sleep(0.015)
    yield sse({"content": "", "done": True, "responseLevel": level})


async def stream_llm(question: str, level: int):
    body = {
        "model": settings.openai_model,
        "stream": True,
        "temperature": 0.4,
        "messages": [
            {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{LEVEL_INSTRUCTIONS[level]}"},
            {"role": "user", "content": question},
        ],
    }
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream(
                "POST", f"{settings.openai_base_url}/chat/completions", json=body, headers=headers
            ) as res:
                if res.status_code != 200:
                    async for chunk in stream_fallback(level):
                        yield chunk
                    return

                async for line in res.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0]["delta"].get("content")
                    except (KeyError, IndexError, json.JSONDecodeError):
                        continue
                    if delta:
                        yield sse({"content": delta, "done": False, "responseLevel": level})
    except httpx.HTTPError:
        async for chunk in stream_fallback(level):
            yield chunk
        return

    yield sse({"content": "", "done": True, "responseLevel": level})


@router.post("/ask")
async def ask(payload: MentorRequest):
    level = level_for(payload.hintsUsed)
    generator = (
        stream_llm(payload.question, level) if settings.openai_api_key else stream_fallback(level)
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

"""Rules first, then one JSON call. A model failure keeps the rules."""

from __future__ import annotations

from pydantic import BaseModel, Field

from dylan.dialogue.rules import extract_rules, model_summary_allowed
from dylan.dialogue.secrets import has_secret
from dylan.memory.constants import EXCLUDED_SYNAPSE_TYPES, MEMORY_TYPES, NEURON_KINDS, SYNAPSE_TYPES
from dylan.memory.encode import Draft


class _NeuronIn(BaseModel):
    kind: str
    content: str


class _LinkIn(BaseModel):
    source: str
    target: str
    type: str


class _ItemIn(BaseModel):
    memory_type: str
    summary: str
    neurons: list[_NeuronIn] = Field(default_factory=list)
    links: list[_LinkIn] = Field(default_factory=list)


class _Payload(BaseModel):
    items: list[_ItemIn] = Field(default_factory=list)


def extraction_messages(user_text: str, answer: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                '只输出 JSON：{"items":[{"memory_type":"fact","summary":"",'
                '"neurons":[{"kind":"concept","content":""}],'
                '"links":[{"source":"","target":"","type":"related_to"}]}]}'
            ),
        },
        {"role": "user", "content": f"用户：{user_text}\n回答：{answer}"},
    ]


def plan_turn(
    user_text: str,
    answer: str,
    model: object,
    api_key: str,
) -> tuple[list[Draft], list[str], list[str]]:
    drafts, forgets = extract_rules(user_text)
    warnings: list[str] = []
    try:
        payload = model.complete_json(extraction_messages(user_text, answer))  # type: ignore[attr-defined]
        parsed = _Payload.model_validate(payload)
    except Exception:
        warnings.append(
            "这一轮只记住了规则能确定的部分" if drafts else "这一轮没有记住"
        )
        parsed = _Payload()
    for item in parsed.items:
        draft = _from_model(item, user_text)
        if draft is not None and model_summary_allowed(draft.summary):
            drafts.append(draft)
    kept: list[Draft] = []
    for draft in drafts:
        blob = " ".join(
            [draft.summary, draft.body, *(content for _kind, content in draft.neurons)]
        )
        if has_secret(blob, api_key):
            warnings.append("这则内容没有记住")
            continue
        kept.append(draft)
    return kept, forgets, warnings


def _from_model(item: _ItemIn, user_text: str) -> Draft | None:
    if item.memory_type not in MEMORY_TYPES:
        return None
    invalid_neuron = any(
        neuron.kind not in NEURON_KINDS or not neuron.content.strip()
        for neuron in item.neurons
    )
    if invalid_neuron:
        return None
    for link in item.links:
        if link.type in EXCLUDED_SYNAPSE_TYPES or link.type not in SYNAPSE_TYPES:
            return None
    summary = item.summary.strip()
    if not summary:
        return None
    spoken = summary in user_text
    return Draft(
        memory_type=item.memory_type,
        summary=summary,
        body=summary,
        neurons=[(neuron.kind, neuron.content.strip()) for neuron in item.neurons],
        links=[(link.source, link.target, link.type) for link in item.links],
        source="user_input" if spoken else "ai_inference",
        confidence="high" if spoken else "medium",
        trust=0.9 if spoken else 0.7,
    )

"""Character bigram Jaccard. No tokenizer and no embeddings."""

from __future__ import annotations

from dylan.memory.constants import SHORT_TEXT


def normalize(text: str) -> str:
    stripped = text.strip()
    chars: list[str] = []
    for char in stripped:
        if ("A" <= char <= "Z") or ("a" <= char <= "z"):
            chars.append(char.casefold())
        else:
            chars.append(char)
    return "".join(chars)


def content_key(text: str) -> str:
    return normalize(text)


def bigrams(text: str) -> set[str]:
    value = normalize(text)
    if len(value) < SHORT_TEXT:
        return set()
    return {value[index : index + 2] for index in range(len(value) - 1)}


def jaccard(left: str, right: str) -> float:
    normal_left = normalize(left)
    normal_right = normalize(right)
    if normal_left == normal_right and normal_left != "":
        return 1.0
    if len(normal_left) < SHORT_TEXT or len(normal_right) < SHORT_TEXT:
        return 0.0
    left_grams = bigrams(left)
    right_grams = bigrams(right)
    union = left_grams | right_grams
    if not union:
        return 0.0
    return len(left_grams & right_grams) / len(union)

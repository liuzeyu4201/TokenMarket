"""CN mobile phone normalization (contracts/phone-normalization.md)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_CN_MOBILE = re.compile(r"^1[3-9]\d{9}$")
_PLUS_86 = re.compile(r"^\+?86(1[3-9]\d{9})$")
_FULLWIDTH_DIGIT_OFFSET = ord("０") - ord("0")


@dataclass(frozen=True)
class PhoneValidationError:
    field: str = "phone"
    message: str = "手机号格式不正确"


def _fullwidth_to_ascii_digits(text: str) -> str:
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if ord("０") <= code <= ord("９"):
            out.append(chr(code - _FULLWIDTH_DIGIT_OFFSET))
        else:
            out.append(ch)
    return "".join(out)


def _strip_whitespace(text: str) -> str:
    return "".join(ch for ch in text if not ch.isspace())


def normalize_cn_mobile(raw: str | None) -> str | PhoneValidationError:
    """Normalize to 11-digit CN mobile or return field error.

    Algorithm: NFKC → fullwidth digits → strip all whitespace → optional +86/86
    prefix when remainder is CN mobile → match ^1[3-9]\\d{9}$.
    """
    if raw is None:
        return PhoneValidationError()
    text = unicodedata.normalize("NFKC", raw)
    if not text.strip():
        return PhoneValidationError()
    text = _fullwidth_to_ascii_digits(text)
    text = _strip_whitespace(text)
    m = _PLUS_86.match(text)
    if m:
        text = m.group(1)
    if _CN_MOBILE.match(text):
        return text
    return PhoneValidationError()

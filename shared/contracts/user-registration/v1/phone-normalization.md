# Contract: CN Mobile Phone Normalization (v1)

**Owner**: API Service (user domain)  
**Consumers**: API Service validators, registration tests, frontend client-side hints (non-authoritative)  
**Version**: 1.0.0

## Purpose

Define the single testable normalization algorithm for V0.1 registration phone numbers (FR-002a–c).

## Algorithm

Input: Unicode string `raw`.

1. If `raw` is null/empty after trim of ends only for emptiness check → error `phone` invalid.
2. Apply Unicode NFKC.
3. Map full-width digits U+FF10–U+FF19 to ASCII `0`–`9`.
4. Remove all Unicode whitespace (categories Zs plus `\t\n\r\f\v`).
5. If the string matches `^\+?86(1[3-9]\d{9})$`, replace with capture group 1.
   - Accept both `+86` and `86` prefixes only when the remainder is already 11-digit CN mobile form.
6. If the string matches `^1[3-9]\d{9}$`, return it as `phone_normalized`.
7. Otherwise → field validation error on `phone` (format). Do **not** perform uniqueness or soft-delete checks.

## Examples

| Input | Output |
|-------|--------|
| `13800138000` | `13800138000` |
| ` 138 0013 8000 ` | `13800138000` |
| `+8613800138000` | `13800138000` |
| `8613800138000` | `13800138000` |
| full-width `１３８００１３８０００` | `13800138000` |
| `12345` | error |
| `+11234567890` | error |
| `12800138000` | error (second digit not 3–9) |

## Uniqueness key

Only `phone_normalized` is stored and compared. Two inputs that normalize equal are the same phone.

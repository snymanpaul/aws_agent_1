"""Verify decode_rle test cases with a known-correct reference implementation."""

def decode_rle_ref(s: str) -> str:
    """Reference: straightforward parser."""
    result = []
    i = 0
    while i < len(s):
        count_str = ""
        while i < len(s) and s[i].isdigit():
            count_str += s[i]
            i += 1
        count = int(count_str) if count_str else 1
        if i < len(s) and s[i].isalpha():
            result.append(s[i] * count)
            i += 1
    return "".join(result)

TEST_CASES = [
    ("",       ""),
    ("a",      "a"),
    ("3a",     "aaa"),
    ("1a",     "a"),
    ("2ab",    "aab"),
    ("3a2b",   "aaabb"),
    ("10a",    "aaaaaaaaaa"),
    ("2a3b1c", "aaabbbc"),     # CHECK THIS
    ("10a2b",  "aaaaaaaaaabb"),
    ("a2b3c",  "abbccc"),
]

for s, claimed_expected in TEST_CASES:
    actual = decode_rle_ref(s)
    ok = actual == claimed_expected
    flag = "✓" if ok else f"✗ WRONG — correct is {actual!r}"
    print(f"  decode_rle({s!r}) → {actual!r}  (claimed: {claimed_expected!r})  {flag}")

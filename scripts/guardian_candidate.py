"""Classify an untrusted AI patch as evidence without executing it.

An allowlisted path does not make AI-generated code safe. This tool never applies,
imports, tests, builds, pushes, or deploys a candidate. Human security review is
required before any future execution, even when this scope check passes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ALLOWLIST = {"apps/web/src/components/landing/WhatWeDonePage.tsx"}
MAX_PATCH_BYTES = 12_000
MAX_CHANGED_LINES = 80


def validate_patch(text: str) -> tuple[bool, str]:
    if not text.strip() or text.strip() == "NO_PATCH":
        return False, "No candidate was justified by the available evidence"
    if len(text.encode("utf-8")) > MAX_PATCH_BYTES:
        return False, "Candidate exceeds byte limit"
    if "GIT binary patch" in text or "Binary files " in text:
        return False, "Binary changes are forbidden"
    if re.search(r"^(?:new file mode|deleted file mode|old mode|new mode|rename |copy )", text, re.MULTILINE):
        return False, "File creation, deletion, rename, copy, and mode changes are forbidden"
    headers = re.findall(r"^diff --git a/(\S+) b/(\S+)$", text, re.MULTILINE)
    if len(headers) != 1 or headers[0][0] != headers[0][1] or headers[0][0] not in ALLOWLIST:
        return False, "Patch must change exactly one allowlisted public component"
    path = headers[0][0]
    if re.findall(r"^--- (.+)$", text, re.MULTILINE) != ["a/" + path]:
        return False, "Invalid source path"
    if re.findall(r"^\+\+\+ (.+)$", text, re.MULTILINE) != ["b/" + path]:
        return False, "Invalid destination path"
    changed = sum(line.startswith(("+", "-")) and not line.startswith(("+++", "---")) for line in text.splitlines())
    if changed > MAX_CHANGED_LINES:
        return False, "Candidate exceeds changed-line limit"
    return True, "Candidate is within the public UI path/size scope only; content is untrusted"


def main(path: str) -> int:
    text = Path(path).read_text(encoding="utf-8")
    accepted, reason = validate_patch(text)
    print(reason)
    if not accepted:
        return 2
    print("Candidate retained as evidence only; no application or execution")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))

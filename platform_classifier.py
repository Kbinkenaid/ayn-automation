#!/usr/bin/env python3
"""Reviewable, conservative game-platform classification."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_MAP = ROOT / "platform-map.json"
IGNORED_EXTENSIONS = frozenset({".txt", ".md"})

@dataclass(frozen=True)
class Classification:
    platform: str | None
    confidence: str
    reason: str
    candidates: tuple[str, ...] = ()
    def as_dict(self) -> dict[str, Any]:
        return {"platform": self.platform, "confidence": self.confidence,
                "reason": self.reason, "candidates": list(self.candidates)}

def load_map(path: Path = DEFAULT_MAP) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1:
        raise ValueError(f"unsupported platform map: {path}")
    return data

def load_decisions(path: Path | None) -> dict[str, str]:
    if path is None: return {}
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict) or raw.get("schema_version", 1) != 1:
        raise ValueError("decision file must be a schema_version 1 JSON object")
    decisions = raw.get("decisions", {k: v for k, v in raw.items() if k not in {"schema_version", "archive_members"}})
    if not isinstance(decisions, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in decisions.items()):
        raise ValueError("decisions must map a relative path or filename to a platform")
    archive_members = raw.get("archive_members", {})
    if not isinstance(archive_members, dict) or any(not isinstance(k, str) or not isinstance(v, dict) for k, v in archive_members.items()):
        raise ValueError("archive_members must map archive names to exact member selection objects")
    return {**{k: v for k, v in decisions.items() if k != "schema_version"}, "__archive_members__": archive_members}

def canonical_platforms(mapping: dict[str, Any]) -> frozenset[str]:
    values = list(mapping["platform_aliases"].values()) + list(mapping["extension_platforms"].values())
    values.extend(value for options in mapping["ambiguous_extensions"].values() for value in options)
    return frozenset(values)

def classify(path: Path, *, relative_path: str | None = None, decisions: dict[str, str] | None = None, platform_map: dict[str, Any] | None = None) -> Classification:
    mapping, decisions = platform_map or load_map(), decisions or {}
    suffix = path.suffix.casefold()
    # Metadata policy has priority over user placement rules. This prevents a
    # typo or compromised decision file from turning a README into a ROM.
    if suffix in IGNORED_EXTENSIONS:
        return Classification(None, "ignored", "user policy ignores text/Markdown metadata")
    for key in (relative_path, path.name, str(path)):
        if key and key in decisions:
            platform = decisions[key]
            if platform not in canonical_platforms(mapping):
                return Classification(None, "needs_review", f"decision uses non-canonical platform: {platform}")
            return Classification(platform, "explicit", f"user decision: {key}")
    aliases, candidates = mapping["platform_aliases"], tuple(mapping["ambiguous_extensions"].get(suffix, ()))
    parent = aliases.get(path.parent.name.casefold())
    if parent and (not candidates or parent in candidates):
        return Classification(parent, "contextual", f"known platform folder: {path.parent.name}")
    if suffix in mapping["extension_platforms"]:
        return Classification(mapping["extension_platforms"][suffix], "format", f"unique format: {suffix}")
    if candidates:
        return Classification(None, "needs_review", f"ambiguous format: {suffix}", candidates)
    return Classification(None, "unsupported", f"unsupported format: {suffix or '(none)'}")

def review_record(path: Path, classification: Classification, *, source: str) -> dict[str, Any]:
    return {"source": source, "path": str(path), "name": path.name, "extension": path.suffix.casefold(), **classification.as_dict()}

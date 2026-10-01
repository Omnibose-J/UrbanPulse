"""Feature flags. Combination states live in the yaml file, not in Python."""

from __future__ import annotations

from pathlib import Path

import yaml

GROUPS = frozenset({"a1", "a1_foreign", "a2"})
PURPOSES = frozenset({"sight", "food", "shop", "none"})
TOLERANCES = frozenset({"calm", "moderate", "busy_ok"})
STATES = frozenset({"on", "reference", "off"})
STRIPS = frozenset({"windows_only", "two_step"})
_COMBO_KEYS = ("group", "purpose", "tolerance", "state", "strip")

DEFAULT_PATH = Path(__file__).resolve().parent / "config" / "feature_flags.yaml"


class FlagFile:
    def __init__(self, combos: dict[tuple[str, str, str], tuple[str, str]], lively_min: dict[str, float]):
        self._combos = combos
        self.lively_min = lively_min

    def known(self, group: str, purpose: str, tolerance: str) -> bool:
        return (group, purpose, tolerance) in self._combos

    def lookup(self, group: str, purpose: str, tolerance: str) -> tuple[str, str]:
        return self._combos.get((group, purpose, tolerance), ("off", "windows_only"))


def load(path: Path | None = None) -> FlagFile:
    path = DEFAULT_PATH if path is None else path
    text = path.read_text(encoding="utf-8")
    try:
        node = yaml.compose(text)
    except yaml.YAMLError as exc:
        raise SystemExit(f"{path.name}: {exc}") from exc
    if not isinstance(node, yaml.MappingNode):
        _fail(path, 1, "expected a mapping")
    fields = {key.value: value for key, value in node.value}
    lively = _lively_min(path, fields.get("lively_min"))
    combos = _combos(path, fields.get("combos"))
    return FlagFile(combos, lively)


def _lively_min(path: Path, node) -> dict[str, float]:
    if not isinstance(node, yaml.MappingNode):
        _fail(path, 1, "lively_min must be a mapping")
    out: dict[str, float] = {}
    for key, value in node.value:
        line = key.start_mark.line + 1
        if key.value not in ("sight", "food", "shop"):
            _fail(path, line, f"unknown lively_min {key.value}")
        if not isinstance(value, yaml.ScalarNode):
            _fail(path, line, f"lively_min {key.value} must be a number")
        out[key.value] = float(value.value)
    for purpose in ("sight", "food", "shop"):
        if purpose not in out:
            _fail(path, node.start_mark.line + 1, f"missing lively_min {purpose}")
    return out


def _combos(path: Path, node) -> dict[tuple[str, str, str], tuple[str, str]]:
    if not isinstance(node, yaml.SequenceNode):
        _fail(path, 1, "combos must be a list")
    combos: dict[tuple[str, str, str], tuple[str, str]] = {}
    for item in node.value:
        line = item.start_mark.line + 1
        if not isinstance(item, yaml.MappingNode):
            _fail(path, line, "expected a combination")
        raw = {}
        for key, value in item.value:
            if not isinstance(value, yaml.ScalarNode):
                _fail(path, line, f"{key.value} must be a scalar")
            raw[key.value] = value.value
        unknown = [key for key in raw if key not in _COMBO_KEYS]
        if unknown:
            _fail(path, line, f"unknown field {unknown[0]}")
        for key in _COMBO_KEYS:
            if key not in raw:
                _fail(path, line, f"missing {key}")
        group, purpose, tolerance = raw["group"], raw["purpose"], raw["tolerance"]
        state, strip = raw["state"], raw["strip"]
        if group not in GROUPS:
            _fail(path, line, f"unknown group {group}")
        if purpose not in PURPOSES:
            _fail(path, line, f"unknown purpose {purpose}")
        if tolerance not in TOLERANCES:
            _fail(path, line, f"unknown tolerance {tolerance}")
        if state not in STATES:
            _fail(path, line, f"unknown state {state}")
        if strip not in STRIPS:
            _fail(path, line, f"unknown strip {strip}")
        combo = (group, purpose, tolerance)
        if combo in combos:
            _fail(path, line, f"duplicate {group} {purpose} {tolerance}")
        combos[combo] = (state, strip)
    return combos


def _fail(path: Path, line: int, message: str) -> None:
    raise SystemExit(f"{path.name}:{line}: {message}")

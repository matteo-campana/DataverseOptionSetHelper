"""
Data models and helpers shared across the application.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OptionSetInfo:
    """Lightweight representation of a global OptionSet (for the left table)."""
    name: str
    display_label: str
    option_set_type: str
    option_count: int
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class OptionValueInfo:
    """Lightweight representation of a single option (for the right table)."""
    value: int
    label: str


def extract_optionset_infos(
    raw_list: list[dict], language_code: int = 1033
) -> list[OptionSetInfo]:
    """Convert the Dataverse JSON array into a list of OptionSetInfo."""
    infos: list[OptionSetInfo] = []
    for item in raw_list:
        display = ""
        for lbl in item.get("DisplayName", {}).get("LocalizedLabels", []):
            if lbl.get("LanguageCode") == language_code:
                display = lbl["Label"]
                break
        infos.append(
            OptionSetInfo(
                name=item.get("Name", ""),
                display_label=display,
                option_set_type=item.get("OptionSetType", ""),
                option_count=len(item.get("Options", [])),
                raw=item,
            )
        )
    return sorted(infos, key=lambda x: x.name)


def extract_option_values(
    options: list[dict], language_code: int = 1033
) -> list[OptionValueInfo]:
    """Convert raw option dicts into OptionValueInfo list."""
    result: list[OptionValueInfo] = []
    for opt in options:
        lbl = ""
        for loc in opt.get("Label", {}).get("LocalizedLabels", []):
            if loc.get("LanguageCode") == language_code:
                lbl = loc["Label"]
                break
        result.append(OptionValueInfo(value=opt.get("Value", 0), label=lbl))
    return sorted(result, key=lambda x: x.value)

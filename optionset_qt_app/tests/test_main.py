"""Basic smoke tests for the OptionSet Qt application."""
from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure parent path is available
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from optionset_qt.models.optionset_model import (
    OptionSetInfo,
    OptionValueInfo,
    extract_option_values,
    extract_optionset_infos,
)
from optionset_qt.controllers.main_controller import load_options_from_file


class TestModels(unittest.TestCase):
    """Tests for data model helpers."""

    def test_extract_optionset_infos_empty(self):
        self.assertEqual(extract_optionset_infos([]), [])

    def test_extract_optionset_infos_single(self):
        raw = [
            {
                "Name": "test_os",
                "DisplayName": {
                    "LocalizedLabels": [
                        {"LanguageCode": 1033, "Label": "Test OS"},
                    ]
                },
                "OptionSetType": "Picklist",
                "Options": [{"Value": 1}, {"Value": 2}],
            }
        ]
        result = extract_optionset_infos(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "test_os")
        self.assertEqual(result[0].display_label, "Test OS")
        self.assertEqual(result[0].option_count, 2)

    def test_extract_option_values(self):
        raw = [
            {
                "Value": 100,
                "Label": {"LocalizedLabels": [{"LanguageCode": 1033, "Label": "Alpha"}]},
            },
            {
                "Value": 200,
                "Label": {"LocalizedLabels": [{"LanguageCode": 1033, "Label": "Beta"}]},
            },
        ]
        result = extract_option_values(raw)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].value, 100)
        self.assertEqual(result[0].label, "Alpha")

    def test_extract_option_values_missing_lang(self):
        raw = [
            {
                "Value": 1,
                "Label": {"LocalizedLabels": [{"LanguageCode": 1040, "Label": "Italian"}]},
            }
        ]
        result = extract_option_values(raw, language_code=1033)
        self.assertEqual(result[0].label, "")

    def test_optionset_info_dataclass(self):
        info = OptionSetInfo("n", "l", "Picklist", 3)
        self.assertEqual(info.name, "n")
        self.assertEqual(info.raw, {})


class TestFileLoader(unittest.TestCase):
    """Tests for CSV / JSON option loader."""

    def test_load_csv(self, tmp_path=None):
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".csv")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("label,value\nAlpha,100\nBeta,200\n")
            items = load_options_from_file(path)
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0].label, "Alpha")
            self.assertEqual(items[0].value, 100)
        finally:
            os.unlink(path)

    def test_load_json_list(self):
        import tempfile, os, json
        fd, path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump([{"label": "X", "value": 1}], f)
            items = load_options_from_file(path)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].label, "X")
        finally:
            os.unlink(path)

    def test_load_json_dict(self):
        import tempfile, os, json
        fd, path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"Foo": 10, "Bar": 20}, f)
            items = load_options_from_file(path)
            self.assertEqual(len(items), 2)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()

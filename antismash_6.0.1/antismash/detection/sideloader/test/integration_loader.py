# License: GNU Affero General Public License v3 or later
# A copy of GNU AGPL v3 should have been included in this software package in LICENSE.txt.

# for test files, silence irrelevant and noisy pylint warnings
# pylint: disable=no-self-use,protected-access,missing-docstring,too-many-public-methods

import unittest

import antismash
from antismash.common.test import helpers
from antismash.config import build_config, destroy_config
from antismash.detection import sideloader

from .test_loading import GOOD_FILE


class TestRegeneration(unittest.TestCase):
    def setUp(self):
        self.options = build_config(["--sideload", GOOD_FILE], isolated=True,
                                    modules=antismash.main.get_all_modules())

    def tearDown(self):
        destroy_config()

    def test_reuse(self):
        raw_results = sideloader.loader.load_validated_json(GOOD_FILE, sideloader.general._SCHEMA_FILE)

        nisin = helpers.get_path_to_nisin_genbank()
        results = helpers.run_and_regenerate_results_for_module(nisin, sideloader, self.options)

        assert results.record_id == raw_results["records"][0]["name"]

        record_section = raw_results["records"][0]
        for result, raw in zip(results.subregions, record_section["subregions"]):
            assert result.tool.name == raw_results["tool"]["name"]
            assert result.start == raw["start"]
            assert result.end == raw["end"]
            assert result.label == raw["label"]
            assert result.details == {
                "score": ["6.5"],
                "some_option_name": ["yes"],
                "some_other_detail": ["first", "second", "etc"]
            }

# License: GNU Affero General Public License v3 or later
# A copy of GNU AGPL v3 should have been included in this software package in LICENSE.txt.

# for test files, silence irrelevant and noisy pylint warnings
# pylint: disable=use-implicit-booleaness-not-comparison,protected-access,missing-docstring,consider-using-with

from argparse import Namespace
import glob
import json
import importlib
import os
import pkgutil
import unittest
from unittest.mock import patch

from Bio.Seq import Seq

from antismash.common import path
from antismash.common.hmm_rule_parser import rule_parser, cluster_prediction as hmm_detection  # TODO: redo tests
from antismash.common.hmm_rule_parser.test.helpers import check_hmm_signatures
from antismash.common.secmet import Record
from antismash.common.test.helpers import DummyCDS, DummyRecord, FakeHSPHit
from antismash.config import build_config, destroy_config
import antismash.detection.hmm_detection as core
from antismash.detection.hmm_detection import DynamicProfile, signatures


class HmmDetectionTest(unittest.TestCase):
    def setUp(self):
        self.config = build_config([])
        self.rules_file = path.get_full_path(__file__, "..", "cluster_rules", "strict.txt")
        self.signature_file = path.get_full_path(__file__, "..", "data", "hmmdetails.txt")
        self.signature_names = {sig.name for sig in core.get_signature_profiles()}.union(core.DYNAMIC_PROFILES)
        self.valid_categories = {cat.name for cat in core.get_rule_categories()}
        self.filter_file = path.get_full_path(__file__, "..", "filterhmmdetails.txt")
        self.results_by_id = {
            "GENE_1": [
                FakeHSPHit("modelA", "GENE_1", 0, 10, 50, 0),
                FakeHSPHit("modelB", "GENE_1", 0, 10, 50, 0)
            ],
            "GENE_2": [
                FakeHSPHit("modelC", "GENE_2", 0, 10, 50, 0),
                FakeHSPHit("modelB", "GENE_2", 0, 10, 50, 0)
            ],
            "GENE_3": [
                FakeHSPHit("modelC", "GENE_3", 0, 10, 50, 0),
                FakeHSPHit("modelF", "GENE_3", 0, 10, 50, 0)
            ],
            "GENE_4": [
                FakeHSPHit("modelA", "GENE_4", 0, 10, 50, 0),
                FakeHSPHit("modelE", "GENE_4", 0, 10, 50, 0)
            ],
            "GENE_5": [
                FakeHSPHit("modelA", "GENE_5", 0, 10, 50, 0),
                FakeHSPHit("modelG", "GENE_5", 0, 10, 50, 0)
            ]
        }
        self.feature_by_id = {
            "GENE_1": DummyCDS(0, 30000, locus_tag="GENE_1"),
            "GENE_2": DummyCDS(30000, 50000, locus_tag="GENE_2"),
            "GENE_3": DummyCDS(70000, 90000, locus_tag="GENE_3"),
            "GENE_X": DummyCDS(95000, 100000, locus_tag="GENE_X"),  # no hits
            "GENE_4": DummyCDS(125000, 140000, locus_tag="GENE_4"),
            "GENE_5": DummyCDS(130000, 150000, locus_tag="GENE_5")
        }

        self.test_names = {"modelA", "modelB", "modelC", "modelF", "modelG",
                           "a", "b", "c", "d"}

        self.categories = {"Cat"}

        self.rules = rule_parser.Parser("\n".join([
            "RULE MetaboliteA CATEGORY Cat CUTOFF 10 NEIGHBOURHOOD 5 CONDITIONS modelA",
            "RULE MetaboliteB CATEGORY Cat CUTOFF 10 NEIGHBOURHOOD 5 CONDITIONS cds(modelA and modelB)",
            "RULE MetaboliteC CATEGORY Cat CUTOFF 10 NEIGHBOURHOOD 5 CONDITIONS (modelA and modelB)",
            "RULE MetaboliteD CATEGORY Cat CUTOFF 20 NEIGHBOURHOOD 5 CONDITIONS minimum(2,[modelC,modelB]) and modelA",
            "RULE Metabolite0 CATEGORY Cat CUTOFF 1 NEIGHBOURHOOD 3 CONDITIONS modelF",
            "RULE Metabolite1 CATEGORY Cat CUTOFF 1 NEIGHBOURHOOD 3 CONDITIONS modelG"]),
            self.test_names, self.categories).rules
        self.record = Record()
        self.record._record.seq = Seq("A"*150000)
        for feature in self.feature_by_id.values():
            self.record.add_cds_feature(feature)

    def tearDown(self):
        # clear out any leftover config adjustments
        destroy_config()

    def test_overlaps_but_not_contains(self):
        # should get gene2 and gene3
        rules = rule_parser.Parser("\n".join([
                "RULE Overlap CATEGORY Cat CUTOFF 25 NEIGHBOURHOOD 5 CONDITIONS modelB and modelF "
                "RULE OverlapImpossible CATEGORY Cat CUTOFF 25 NEIGHBOURHOOD 5 CONDITIONS modelA and modelF"]),
                self.test_names, self.categories).rules
        detected_types, cluster_type_hits = hmm_detection.apply_cluster_rules(self.record, self.results_by_id, rules)
        assert detected_types == {"GENE_2": {"Overlap": {"modelB"}},
                                  "GENE_3": {"Overlap": {"modelF"}}}

        assert cluster_type_hits == {"Overlap": {"GENE_2", "GENE_3"}}

        # only 1 cluster should be found, since it requires both genes
        # if forming clusters by .is_contained_by(), 2 clusters will be formed
        # if finding rule hits uses .is_contained_by(), no clusters will be formed
        rules_by_name = {rule.name: rule for rule in rules}
        clusters = hmm_detection.find_protoclusters(self.record, cluster_type_hits, rules_by_name)
        assert len(clusters) == 1
        assert clusters[0].product == "Overlap"
        assert clusters[0].core_location.start == 30000
        assert clusters[0].core_location.end == 90000

    def test_core(self):
        # should be no failing prerequisites
        assert core.check_prereqs(self.config) == []
        # always runs
        assert core.is_enabled(None)

    def test_apply_cluster_rules(self):
        detected_types, cluster_type_hits = hmm_detection.apply_cluster_rules(self.record, self.results_by_id,
                                                                              self.rules)
        for gid in detected_types:
            detected_types[gid] = set(detected_types[gid])
        expected_types = {
            "GENE_1": set(["MetaboliteA", "MetaboliteB", "MetaboliteC", "MetaboliteD"]),
            "GENE_2": set(["MetaboliteC", "MetaboliteD"]),
            "GENE_3": set(["Metabolite0"]),
            "GENE_4": set(["MetaboliteA"]),
            "GENE_5": set(["Metabolite1", "MetaboliteA"])
        }
        assert detected_types == expected_types

        assert cluster_type_hits == {"MetaboliteA": {"GENE_1", "GENE_4", "GENE_5"},
                                     "MetaboliteB": {"GENE_1"},
                                     "MetaboliteC": {"GENE_1", "GENE_2"},
                                     'MetaboliteD': {'GENE_1', 'GENE_2'},
                                     'Metabolite0': {'GENE_3'},
                                     'Metabolite1': {'GENE_5'}}

    def test_find_protoclusters(self):
        cds_features_by_type = {"MetaboliteA": {"GENE_1", "GENE_4", "GENE_5"},
                                "MetaboliteB": {"GENE_1"},
                                "MetaboliteC": {"GENE_1", "GENE_2"},
                                'MetaboliteD': {'GENE_1', 'GENE_2'},
                                'Metabolite0': {'GENE_3'},
                                'Metabolite1': {'GENE_5'}}
        rules = {rule.name: rule for rule in self.rules}
        for cluster in hmm_detection.find_protoclusters(self.record, cds_features_by_type, rules):
            self.record.add_protocluster(cluster)
        assert len(self.record.get_protoclusters()) == 7
        cluster_products = sorted([cluster.product for cluster in self.record.get_protoclusters()])
        assert cluster_products == sorted([f"Metabolite{i}" for i in "01AABCD"])
        self.record.create_candidate_clusters()
        assert len(self.record.get_candidate_clusters()) == 3
        self.record.create_regions()
        assert len(self.record.get_regions()) == 3
        result_regions = []
        for region in self.record.get_regions():
            result_regions.append(sorted(cds.get_name() for cds in region.cds_children))

        expected_regions = [
            ["GENE_1", "GENE_2"],
            ["GENE_3"],
            ["GENE_4", "GENE_5"]
        ]
        assert result_regions == expected_regions

    def test_create_rules(self):
        aliases = {}
        rules = hmm_detection.create_rules(self.rules_file, self.signature_names,
                                           self.valid_categories, aliases)
        assert len(rules) == open(self.rules_file, encoding="utf-8").read().count("\nRULE")
        t1pks_rules = [rule for rule in rules if rule.name == "T1PKS"]
        assert len(t1pks_rules) == 1
        rule = t1pks_rules[0]
        assert rule.cutoff == 20000
        assert rule.neighbourhood == 20000

    def test_profiles_parsing(self):
        aliases = {}
        strict_rules_file = path.get_full_path(__file__, "..", "cluster_rules", "strict.txt")
        relaxed_rules_file = path.get_full_path(__file__, "..", "cluster_rules", "relaxed.txt")
        loose_rules_file = path.get_full_path(__file__, "..", "cluster_rules", "loose.txt")

        rules = hmm_detection.create_rules(strict_rules_file, self.signature_names,
                                           self.valid_categories, aliases)
        rules = hmm_detection.create_rules(relaxed_rules_file, self.signature_names,
                                           self.valid_categories, aliases, rules)
        rules = hmm_detection.create_rules(loose_rules_file, self.signature_names,
                                           self.valid_categories, aliases, rules)
        profiles_used = set()

        with open(self.filter_file, "r", encoding="utf-8") as handle:
            filter_lines = handle.readlines()
        for line in filter_lines:
            for sig in line.split(','):
                profiles_used.add(sig.strip())

        for rule in rules:
            profiles_used = profiles_used.union(rule.conditions.profiles)
            for related in rule.related:
                profiles_used.add(related)

        names = self.signature_names

        signatures_not_in_rules = names.difference(profiles_used)
        assert not signatures_not_in_rules, f"No rules use {signatures_not_in_rules}"

        profiles_without_signature = profiles_used.difference(names)
        assert not profiles_without_signature, f"No signature definitions for {profiles_without_signature}"

    def test_filter(self):
        # fake HSPs all in one CDS with overlap > 20 and query_ids from the same equivalence group

        # not overlapping by > 20
        first = FakeHSPHit("AMP-binding", "A", 50, 90, 0.1, None)
        second = FakeHSPHit("A-OX", "A", 70, 100, 0.5, None)
        new, by_id = hmm_detection.filter_results([first, second], {"A": [first, second]},
                                                  self.filter_file, self.signature_names)
        assert new == [first, second]
        assert by_id == {"A": [first, second]}

        # overlapping, in same group
        first.hit_end = 91
        assert hmm_detection.hsp_overlap_size(first, second) == 21
        new, by_id = hmm_detection.filter_results([first, second], {"A": [first, second]},
                                                  self.filter_file, self.signature_names)
        assert new == [second]
        assert by_id == {"A": [second]}

        # overlapping, not in same group
        second.query_id = "none"
        new, by_id = hmm_detection.filter_results([first, second], {"A": [first, second]},
                                                  self.filter_file, self.signature_names)
        assert new == [first, second]
        assert by_id == {"A": [first, second]}

        # not in the same CDS, but int he same group
        second.hit_id = "B"
        second.query_id = "A-OX"
        new, by_id = hmm_detection.filter_results([first, second], {"A": [first], "B": [second]},
                                                  self.filter_file, self.signature_names)
        assert new == [first, second]
        assert by_id == {"A": [first], "B": [second]}

    def test_filter_multiple(self):
        # all in one CDS no overlap and the same query_ids -> cull all but the best score

        # not overlapping, not same query_id
        first = FakeHSPHit("AMP-binding", "A", 50, 60, 0.1, None)
        second = FakeHSPHit("A-OX", "A", 70, 100, 0.5, None)
        both = [first, second]
        by_id = {"A": [first, second]}
        new, by_id = hmm_detection.filter_result_multiple(list(both), dict(by_id))
        assert new == [first, second]
        assert by_id == {"A": [first, second]}

        # not overlapping, same query_id
        first.query_id = "A-OX"
        new, by_id = hmm_detection.filter_result_multiple(list(both), dict(by_id))
        assert new == [second]
        assert by_id == {"A": [second]}

        # not in same CDS, same query_id
        second.hit_id = "B"
        by_id = {"A": [first], "B": [second]}
        new, by_id = hmm_detection.filter_result_multiple(list(both), dict(by_id))
        assert new == [first, second]
        assert by_id == {"A": [first], "B": [second]}

    def test_equivalence_groups(self):
        group_file = path.get_full_path(os.path.dirname(__file__), "filterhmmdetails.txt")
        sets = []
        with open(group_file, encoding="utf-8") as group_lines:
            sets = [set(line.strip().split(',')) for line in group_lines]

        # ensure they have at least two elements
        assert all(len(s) > 1 for s in sets)

        # ensure that the groups are disjoint
        for i, group in enumerate(sets):
            for other in sets[i + 1:]:
                assert group.isdisjoint(other)

    def test_hsp_overlap_size(self):
        overlap_size = hmm_detection.hsp_overlap_size
        first = FakeHSPHit("A", "A", 50, 60, 0., None)
        second = FakeHSPHit("B", "B", 70, 100, 0., None)
        # no overlap
        assert overlap_size(first, second) == 0
        first.hit_end = 70
        # still no overlap, end isn't inclusive
        assert overlap_size(first, second) == 0
        # a mix of second starting inside first
        for i in range(1, 30):
            first.hit_end += 1
            assert overlap_size(first, second) == i
        # second wholly contained
        first.hit_end = 110
        assert overlap_size(first, second) == 30

        # first inside second
        first.hit_start = 75
        assert overlap_size(first, second) == 25

        # first inside second, but direction reversed
        first.hit_end = 50
        with self.assertRaises(AssertionError):
            overlap_size(first, second)

    def test_hmm_files_and_details_match(self):
        data_dir = path.get_full_path(os.path.dirname(__file__), "data", "")
        details_files = {prof.path for prof in signatures.get_signature_profiles()}
        details_files = {filepath.replace(data_dir, "") for filepath in details_files}
        data_dir_contents = set(glob.glob(data_dir + "*.hmm"))
        data_dir_contents = {filepath.replace(data_dir, "") for filepath in data_dir_contents}
        # ignore bgc_seeds.hmm for the sake of comparison, it's a generated aggregate
        data_dir_contents.discard("bgc_seeds.hmm")
        missing_files = details_files - data_dir_contents
        assert not missing_files
        extra_files = data_dir_contents - details_files
        assert not extra_files
        # finally, just to be sure
        assert data_dir_contents == details_files


class TestSignatureFile(unittest.TestCase):
    def test_details(self):
        data_dir = path.get_full_path(os.path.dirname(__file__), 'data')
        check_hmm_signatures(os.path.join(data_dir, 'hmmdetails.txt'), data_dir)


class TestDynamicGather(unittest.TestCase):
    def _go(self, dummy_module):
        with patch.object(pkgutil, "walk_packages", return_value=[Namespace(name="dummy")]):
            with patch.object(importlib, "import_module", return_value=dummy_module):
                return core._get_dynamic_profiles()

    def test_gather(self):
        prof_a = DynamicProfile("A", "desc a", lambda rec: {})
        prof_b = DynamicProfile("b", "desc b", lambda rec: {})
        dynamics = self._go(Namespace(a=prof_a, b=prof_b, c="some text"))
        assert len(dynamics) == 2
        assert sorted(list(dynamics)) == ["A", "b"]
        assert dynamics["A"].name == "A"
        assert dynamics["b"].name == "b"

    def test_duplicates(self):
        prof_a = DynamicProfile("A", "desc a", lambda rec: {})
        prof_b = DynamicProfile("A", "desc b", lambda rec: {})
        with self.assertRaisesRegex(ValueError, "duplicate dynamic profile"):
            self._go(Namespace(a=prof_a, b=prof_b))

    def test_empty(self):
        with self.assertRaisesRegex(ValueError, "subpackage .* has no"):
            self._go(Namespace(a="7"))


class TestMultipliers(unittest.TestCase):
    def setUp(self):
        self.record = DummyRecord()
        self.record.add_cds_feature(DummyCDS())

    def tearDown(self):
        destroy_config()

    def run_through(self, options):
        with patch.object(core, "detect_protoclusters_and_signatures",
                          side_effect=RuntimeError("stop here")) as patched:
            with patch.object(core, "get_rule_categories", return_value=[]):
                with self.assertRaisesRegex(RuntimeError, "stop here"):
                    core.run_on_record(self.record, None, options)
            assert patched.called_once
            args, kwargs = patched.call_args
        return args, kwargs

    def test_bacteria_ignores_fungal_multi(self):
        options = build_config([
            "--taxon", "bacteria",
            "--hmmdetection-fungal-cutoff-multiplier", "7.0",
            "--hmmdetection-fungal-neighbourhood-multiplier", "3",
        ], modules=[core])
        _, used_kwargs = self.run_through(options)
        assert used_kwargs["multipliers"] == core.Multipliers(1.0, 1.0)

    def test_fungal_respects_multis(self):
        options = build_config([
            "--taxon", "fungi",
            "--hmmdetection-fungal-cutoff-multiplier", "0.5",
            "--hmmdetection-fungal-neighbourhood-multiplier", "3",
        ], modules=[core])
        _, used_kwargs = self.run_through(options)
        assert used_kwargs["multipliers"] == core.Multipliers(0.5, 3.0)

    def test_check_options(self):
        options = build_config([
            "--taxon", "fungi",
            "--hmmdetection-fungal-cutoff-multiplier", "0",
            "--hmmdetection-fungal-neighbourhood-multiplier", "-5",
        ], modules=[core])
        assert core.check_options(options) == [
            "Invalid fungal cutoff multiplier: 0.0",
            "Invalid fungal neighbourhood multiplier: -5.0",
        ]

    def test_reuse_changes(self):
        options = build_config([
            "--taxon", "fungi",
            "--hmmdetection-fungal-cutoff-multiplier", "1",
            "--hmmdetection-fungal-neighbourhood-multiplier", "1.5",
        ], modules=[core])
        results = core.run_on_record(self.record, None, options)
        as_json = json.loads(json.dumps(results.to_json()))

        regenerated = core.regenerate_previous_results(as_json, self.record, options)
        assert regenerated.rule_results.multipliers == results.rule_results.multipliers

        # ensure a changed cutoff multiplier breaks results reuse
        options = build_config([
            "--taxon", "fungi",
            "--hmmdetection-fungal-cutoff-multiplier", "2.0",
        ], modules=[core])
        with self.assertRaisesRegex(RuntimeError, "cutoff multiplier .* incompatible"):
            core.regenerate_previous_results(as_json, self.record, options)

        options = build_config([
            "--taxon", "fungi",
            "--hmmdetection-fungal-neighbourhood-multiplier", "0.5",
        ], modules=[core])
        with self.assertRaisesRegex(RuntimeError, "neighbourhood multiplier .* incompatible"):
            core.regenerate_previous_results(as_json, self.record, options)

# License: GNU Affero General Public License v3 or later
# A copy of GNU AGPL v3 should have been included in this software package in LICENSE.txt.

# for test files, silence irrelevant and noisy pylint warnings
# pylint: disable=no-self-use,protected-access,missing-docstring

import unittest

import antismash
from antismash.config import build_config
from antismash.common.test import helpers
from antismash.detection import nrps_pks_domains


class TestAnalyses(unittest.TestCase):
    def setUp(self):
        # skipping clusterhmmer and the p450 potential hits for speed
        self.options = build_config(["--minimal"],
                                    isolated=True,
                                    modules=antismash.get_all_modules())

    def test_regeneration(self):
        datafile = helpers.get_path_to_balhymicin_genbank()
        results = helpers.run_and_regenerate_results_for_module(datafile, nrps_pks_domains, self.options)
        assert results
        assert len(results.cds_results) == 9

        expected_types = {'bpsC': 'NRPS', 'pks': 'other', 'bpsD': 'NRPS-like protein',
                          'dpgD': 'other', 'pgat': 'other', 'dpgB': 'other',
                          'bpsA': 'Glycopeptide NRPS', 'bpsB': 'Glycopeptide NRPS', 'dpgC': 'other'}

        for cds, cds_result in results.cds_results.items():
            assert isinstance(cds_result, nrps_pks_domains.domain_identification.CDSResult)
            # motifs can be empty, but domains cannot be
            assert cds_result.domain_hmms
            assert cds_result.type
            # ensure results were added as they regenerated, as it's a detection module
            assert len(cds_result.domain_hmms) == len(cds.nrps_pks.domains)
            assert len(cds_result.motif_hmms) == len(cds.motifs)
            assert cds.nrps_pks.type == cds_result.type

        found_types = {cds.get_name(): result.type for cds, result in results.cds_results.items()}
        assert found_types == expected_types

    def test_add_when_regenerating(self):
        record = helpers.DummyRecord(seq="A"*3800)
        record.id = 'Y16952.3.trimmed'
        record.add_cds_feature(helpers.DummyCDS(start=0, end=1800, locus_tag="two_domains"))
        record.add_cds_feature(helpers.DummyCDS(start=1900, end=4000, locus_tag="one_domain"))
        record.add_cds_feature(helpers.DummyCDS(start=4100, end=4400, locus_tag="no_hits"))

        a_domain = {'bitscore': 360.7, 'query_end': 428, 'evalue': 2.1e-110, 'hit_id': 'AMP-binding', 'query_start': 35}
        pcp = {'bitscore': 66.0, 'query_end': 569, 'evalue': 6.3e-21, 'hit_id': 'PCP', 'query_start': 504}

        two_domain_json = {'domain_hmms': [a_domain, pcp],
                           'motif_hmms': [],
                           'modules': [{"components": [
                                           {"domain": a_domain},
                                           {"domain": pcp},
                                        ]
                                        }],
                           "ks_subtypes": [],
                           'type': 'NRPS'}
        one_domain_json = {'domain_hmms': [{'bitscore': 76.9, 'query_end': 382, 'evalue': 3.9e-24, 'hit_id': 'ECH', 'query_start': 170}],
                           'motif_hmms': [{'query_start': 18, 'evalue': 4.7e-05, 'query_end': 30, 'bitscore': 16.1, 'hit_id': 'C1_dual_004-017'},
                                          {'query_start': 38, 'evalue': 1.4e-19, 'query_end': 78, 'bitscore': 62.4, 'hit_id': 'C2_DCL_024-062'}],
                           "modules": [],  # arbitrarily none
                           "ks_subtypes": [],
                           'type': 'other'}

        json = {'cds_results': {'two_domains': two_domain_json,
                                'one_domain': one_domain_json},
                'record_id': record.id,
                'modules': [],
                'schema_version': nrps_pks_domains.domain_identification.NRPSPKSDomains.schema_version}

        assert not record.get_antismash_domains()
        assert not record.get_cds_motifs()

        results = nrps_pks_domains.domain_identification.NRPSPKSDomains.from_json(json, record)
        assert len(results.cds_results) == 2
        assert len(record.get_cds_motifs()) == 2
        assert len(record.get_antismash_domains()) == 3

        two_domains = record.get_cds_by_name("two_domains")
        assert two_domains.nrps_pks.type == "NRPS"
        assert len(two_domains.nrps_pks.domains) == 2
        assert not two_domains.motifs
        modules = results.cds_results[two_domains].modules
        assert modules
        assert modules[0]._loader._domain.hit_id == "AMP-binding"
        assert modules[0]._carrier_protein._domain.hit_id == "PCP"
        assert not two_domains.modules  # added in add_to_record

        one_domain = record.get_cds_by_name("one_domain")
        assert one_domain.nrps_pks.type == "other"
        assert len(one_domain.nrps_pks.domains) == 1
        assert len(one_domain.motifs) == 2
        assert not results.cds_results[one_domain].modules
        assert not one_domain.modules

        no_hits = record.get_cds_by_name("no_hits")
        assert not no_hits.nrps_pks

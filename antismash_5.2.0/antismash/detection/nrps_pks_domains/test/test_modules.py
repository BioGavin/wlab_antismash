# License: GNU Affero General Public License v3 or later
# A copy of GNU AGPL v3 should have been included in this software package in LICENSE.txt.

# for test files, silence irrelevant and noisy pylint warnings
# pylint: disable=no-self-use,protected-access,missing-docstring,too-many-public-methods

import json
import unittest

from antismash.common import path
from antismash.common.test.helpers import DummyHMMResult
from antismash.detection import nrps_pks_domains
from antismash.detection.nrps_pks_domains.module_identification import (
    CLASSIFICATIONS,
    Component,
    Module,
    build_modules_for_cds,
    classify,
)

# chosen arbitrarily, these exist to make future profile renames easier
NRPS_START = "Cglyc"
NRPS_LOAD = "AMP-binding"
PKS_START = "PKS_KS"
PKS_LOAD = "PKS_AT"
TRANS_AT_SUBTYPE = "Trans-AT-KS"
CP = "ACP"


def add_component(module, name, sub="", start=1, end=10):
    module.add_component(Component(DummyHMMResult(name, start, end), sub))


def build_module(names, subtypes=None, first_in_cds=True):
    module = Module(first_in_cds=first_in_cds)
    subs = iter(subtypes or [])
    for domain in names:
        sub = next(subs) if domain == PKS_START and subtypes else ""
        add_component(module, domain, sub)
    return module


class TestClassify(unittest.TestCase):
    def test_existing(self):
        assert CLASSIFICATIONS
        for classification, group in CLASSIFICATIONS.items():
            for label in group:
                assert classify(label) == classification

    def test_all_domains_classified(self):
        domain_names = []
        with open(path.get_full_path(nrps_pks_domains.__file__, "data", "nrpspksdomains.hmm")) as handle:
            for line in handle:
                if line.startswith("NAME"):
                    domain_names.append(line.strip().split()[1])
        missing = [name for name in domain_names if not classify(name)]
        assert not missing, missing

    def test_unclassifiable(self):
        with self.assertRaisesRegex(ValueError, "could not classify"):
            classify("bad-domain-name")


class TestComponent(unittest.TestCase):
    def test_construction(self):
        domain = DummyHMMResult("ACP")
        component = Component(domain)
        assert component.domain == domain
        assert component.label == domain.hit_id
        assert component.subtype == ""
        assert component.classification == "CP"

        domain._hit_id = PKS_START
        component = Component(domain, "some-subtype")
        assert component.subtype == "some-subtype"
        assert component.classification == "KS"

    def test_json(self):
        component = Component(DummyHMMResult(PKS_START), subtype=TRANS_AT_SUBTYPE)
        intermediate = component.to_json()
        new = Component.from_json(json.loads(json.dumps(intermediate)))
        assert new.to_json() == intermediate
        assert new.domain == component.domain
        assert new.subtype == TRANS_AT_SUBTYPE
        assert new.classification == component.classification

    def test_condensation(self):
        for cond in CLASSIFICATIONS["C"]:
            assert Component(DummyHMMResult(cond)).is_condensation()
        assert not Component(DummyHMMResult(NRPS_LOAD)).is_condensation()

    def test_loader(self):
        for cond in [PKS_LOAD, "AMP-binding", "A-OX"]:
            assert Component(DummyHMMResult(cond)).is_loader()
        assert not Component(DummyHMMResult(NRPS_START)).is_loader()


class TestModule(unittest.TestCase):
    def setUp(self):
        self.pks = Module()
        for i, domain in enumerate([PKS_START, PKS_LOAD, CP]):
            start = (i + 1) * 10
            add_component(self.pks, domain, start=start, end=start + 5)
        assert self.pks.is_pks()

        self.nrps = Module()
        for i, domain in enumerate([NRPS_START, NRPS_LOAD, CP]):
            start = (i + 1) * 10
            add_component(self.nrps, domain, start=start, end=start + 5)
        assert self.nrps.is_nrps()

    def test_json(self):
        intermediate = self.pks.to_json()
        assert intermediate
        new = Module.from_json(json.loads(json.dumps(intermediate)))
        assert new.to_json() == intermediate
        assert new._starter.label == PKS_START
        assert not new._end

    def test_methylations(self):
        pks = build_module([PKS_START, PKS_LOAD])
        # mmal is a methylated malonyl-CoA, so it should look the same
        assert pks.get_monomer("mmal") == "Me-mal"
        add_component(pks, "PKS_KR")
        assert pks.get_monomer("mmal") == "Me-ohmal"
        add_component(pks, "nMT")
        assert pks.get_monomer("mmal") == "NMe-Me-ohmal"
        assert pks.get_monomer("mal") == "NMe-ohmal"
        add_component(pks, "oMT")
        assert pks.get_monomer("mal") == "NMe-OMe-ohmal"
        assert pks.get_monomer("pk") == "NMe-OMe-?"

        nrps = build_module([NRPS_START, NRPS_LOAD])
        assert nrps.get_monomer("ala") == "ala"
        add_component(nrps, "cMT")
        assert nrps.get_monomer("ala") == "Me-ala"

        # even with an unknown, the methylation should be indicated
        assert nrps.get_monomer("X") == "Me-?"

    def test_methylation_before_load(self):
        # methylation before an A domain, currently impossible
        with self.assertRaisesRegex(ValueError, "loader after other non-starter"):
            build_module([NRPS_START, "cMT", NRPS_LOAD])

    def test_epimerase(self):
        # should always add a D- at the beginning
        nrps = build_module([NRPS_START, NRPS_LOAD, CP])
        assert nrps.get_monomer("ile") == "ile"
        add_component(nrps, "Epimerization")
        assert nrps.get_monomer("ile") == "D-ile"

        nrps = build_module([NRPS_START, NRPS_LOAD, "cMT", CP])
        assert nrps.get_monomer("gly") == "Me-gly"
        nrps = build_module([NRPS_START, NRPS_LOAD, "cMT", CP, "Epimerization"])
        assert nrps.get_monomer("gly") == "D-Me-gly"

    def test_start(self):
        assert self.pks.start == 10
        self.pks._starter.domain._query_start = 9
        assert self.pks.start == 9
        self.pks._components.pop(0)
        assert self.pks.start == self.pks._loader.domain.query_start

    def test_end(self):
        assert self.nrps.end == 35
        add_component(self.nrps, "Epimerization", start=40, end=60)
        assert self.nrps.end == 60
        self.nrps._end = None
        self.nrps._components.pop(-1)
        assert self.nrps.end == 35
        # TE/TD not included in the length, but are included in the module
        add_component(self.nrps, "Thioesterase", start=70, end=80)
        assert self.nrps.end == 35

    def test_termination(self):
        domains = [NRPS_LOAD, CP]
        module = build_module(domains)
        assert not module.is_terminated()

        add_component(module, "Epimerization")
        assert module.is_terminated()
        assert not module.is_termination_module()

        module = build_module(domains + ["Thioesterase"])
        assert module.is_terminated()
        assert module.is_termination_module()

    def test_starter_module(self):
        assert not self.pks.is_starter_module()
        for starter in ["Condensation_Starter", "CAL_domain", "SAT", NRPS_LOAD]:
            assert build_module([starter]).is_starter_module(), starter

        for domains in [[NRPS_START, NRPS_LOAD],
                         [PKS_START, PKS_LOAD],
                         [CP],
                         ]:
            assert not build_module(domains).is_starter_module(), domains

    def test_no_monomer(self):
        assert self.pks.get_monomer() == ""
        assert self.pks.get_monomer("") == ""

    def test_pk_nrp_indicated(self):
        assert self.pks.get_monomer("pk") == "?"
        assert self.pks.get_monomer("mal") != "?"
        assert self.nrps.get_monomer("X") == "?"
        assert self.nrps.get_monomer("ala") != "?"

    def test_monomer_trans_at_default(self):
        self.pks._starter.subtype = TRANS_AT_SUBTYPE
        self.pks._loader = None
        assert self.pks.is_trans_at()
        assert self.pks.get_monomer("") == "mal"

    def test_trans_at(self):
        assert not self.pks.is_trans_at()
        assert self.pks.is_complete()

        self.pks._starter.subtype = TRANS_AT_SUBTYPE
        assert not self.pks.is_trans_at()

        self.pks._loader = None
        self.pks._starter.subtype = ""
        assert not self.pks.is_trans_at()
        assert not self.pks.is_complete()

        self.pks._starter.subtype = TRANS_AT_SUBTYPE
        assert self.pks.is_trans_at()
        assert self.pks.is_complete()

    def test_trailing_modifiers(self):
        error = "modification domain after carrier protein"
        # not allowed for NRPSs and PKSs
        with self.assertRaisesRegex(ValueError, error):
            build_module([NRPS_START, NRPS_LOAD, CP, "nMT"])
        with self.assertRaisesRegex(ValueError, error):
            build_module([PKS_START, PKS_LOAD, CP, "nMT"])
        # except for trans-at-pks, and only KR
        assert build_module([PKS_START, CP, "PKS_KR"], [TRANS_AT_SUBTYPE]).is_trans_at()
        with self.assertRaisesRegex(ValueError, error):
            assert build_module([PKS_START, CP, "nMT"], [TRANS_AT_SUBTYPE])

    def test_pks_chaining(self):
        module = Module()
        for comp in list(self.pks)[:-1]:
            module.add_component(comp)
        assert module.get_monomer("mal") == "mal"
        add_component(module, "PKS_KR")
        assert module.get_monomer("mal") == "ohmal"
        add_component(module, "PKS_DH")
        assert module.get_monomer("mal") == "ccmal"
        add_component(module, "PKS_ER")
        assert module.get_monomer("mal") == "redmal"

        # and that the order doesn't matter
        module = build_module([PKS_START, PKS_LOAD, "PKS_ER", "PKS_DH", "PKS_KR"])
        assert module.get_monomer("mal") == "redmal"

    def test_completness(self):
        for complete in [[PKS_START, PKS_LOAD, CP],
                         [NRPS_START, NRPS_LOAD, CP],
                         [PKS_LOAD, CP],
                         [NRPS_LOAD, CP],
                         ]:
            assert build_module(complete).is_complete()

        for incomplete in [
                           [PKS_START, CP],
                           [NRPS_START, CP],
                           [NRPS_START, NRPS_LOAD],
                           [NRPS_START, CP],
                           [NRPS_LOAD],
                           ["PKS_KR"],
                           ]:
            assert not build_module(incomplete).is_complete(), incomplete

    def test_is_iterative(self):
        module = build_module(["PKS_KS"], ["Iterative-KS"])
        assert module.is_iterative()

        for other in ["", "Trans-AT-KS", "Modular-KS"]:
            module._starter.subtype = other
            assert not module.is_iterative()

    def test_component_after_end(self):
        add_component(self.nrps, "Epimerization")
        assert self.nrps.is_terminated()
        for other in [NRPS_LOAD, NRPS_START, "nMT"]:
            with self.assertRaisesRegex(ValueError, "adding extra component after end"):
                add_component(self.nrps, other)

    def test_starter_after_others(self):
        with self.assertRaisesRegex(ValueError, "starter after other components"):
            add_component(self.nrps, NRPS_START)

    def test_duplicate_loader(self):
        assert self.nrps._loader
        with self.assertRaisesRegex(ValueError, "duplicate loader"):
            add_component(self.nrps, NRPS_LOAD)

    def test_incompatible_loader(self):
        nrps = build_module([NRPS_START])
        with self.assertRaisesRegex(ValueError, "adding a PKS loader to a NRPS starter"):
            add_component(nrps, PKS_LOAD)

        pks = build_module([PKS_START])
        with self.assertRaisesRegex(ValueError, "adding a NRPS loader to a PKS starter"):
            add_component(pks, NRPS_LOAD)

    def test_duplicate_carrier(self):
        assert self.nrps._carrier_protein
        with self.assertRaisesRegex(ValueError, "duplicate carrier protein"):
            add_component(self.nrps, CP)

    def test_adding_ignored(self):
        start = len(self.nrps._components)
        add_component(self.nrps, "ACPS")
        assert len(self.nrps._components) == start

    def test_unknown_component_type(self):
        component = Component(DummyHMMResult(NRPS_LOAD))
        component._domain._hit_id = "unclassifiable"
        component.classification = "unclassifiable"
        with self.assertRaisesRegex(ValueError, "unhandled"):
            Module().add_component(component)


class TestBuildModules(unittest.TestCase):
    def test_mismatching_ks_subtypes(self):
        with self.assertRaises(StopIteration):
            build_modules_for_cds([DummyHMMResult(PKS_START)], [])

    def test_no_empties(self):
        assert build_modules_for_cds([], []) == []
        assert build_modules_for_cds([DummyHMMResult("ACPS")], []) == []

    def test_unclassifiable(self):
        with self.assertRaisesRegex(ValueError, "could not classify domain"):
            build_modules_for_cds([DummyHMMResult("UNCLASSIFIABLE")], [])

    def test_module_for_each_starter(self):
        modules = build_modules_for_cds([DummyHMMResult("Condensation_DCL"), DummyHMMResult("Condensation_LCL")], [])
        assert len(modules) == 2

    def test_module_for_orphans(self):
        for name in [NRPS_START, NRPS_LOAD, PKS_START, PKS_LOAD, "cMT", "ACP", "Trans-AT_docking"]:
            modules = build_modules_for_cds([DummyHMMResult(name)], [DummyHMMResult("")])
            assert len(modules) == 1
            assert not modules[0].is_complete()

    def test_bad_add_makes_new_module(self):
        modules = build_modules_for_cds([DummyHMMResult(NRPS_LOAD)] * 2, [])
        assert len(modules) == 2
        assert not modules[0].is_complete()

    def test_starters(self):
        for domain_type in [NRPS_LOAD, PKS_LOAD]:
            domains = [DummyHMMResult(i) for i in [domain_type, "ACP", domain_type, "ACP"]]
            modules = build_modules_for_cds(domains, [])
            print(modules)
            assert len(modules) == 2
            assert modules[0]._first_in_cds
            assert modules[0].is_complete()
            assert not modules[1]._first_in_cds
            print(modules[1], modules[1].is_complete())
            print(modules[1]._starter, modules[1]._loader, modules[1]._carrier_protein, modules[1]._starter is modules[1]._loader)
            assert not modules[1].is_complete()

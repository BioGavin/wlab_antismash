# License: GNU Affero General Public License v3 or later
# A copy of GNU AGPL v3 should have been included in this software package in LICENSE.txt.

""" A class for region features """

from collections import OrderedDict
import os
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar
from typing import Set  # used in comment hints, pylint: disable=unused-import
import warnings

from Bio.SeqFeature import SeqFeature
from Bio.SeqRecord import SeqRecord
from helperlibs.bio import seqio

from .cdscollection import CDSCollection, CDSFeature
from .protocluster import Protocluster
from .feature import Feature
from .subregion import SubRegion
from .candidate_cluster import CandidateCluster
from ..locations import (
    build_location_from_others,
    combine_locations,
    FeatureLocation,
    location_from_string,
)

T = TypeVar("T", bound="Region")


class Region(CDSCollection):
    """ A feature that represents a region of interest made up of overlapping
        CandidateCluster features and/or SubRegion features.

        At least one CandidateCluster or SubRegion is required to make up a Region.

        Region features cannot overlap.
    """
    __slots__ = ["_subregions", "_candidate_clusters", "clusterblast",
                 "knownclusterblast", "subclusterblast"]
    FEATURE_TYPE = "region"

    def __init__(self, candidate_clusters: List[CandidateCluster] = None,
                 subregions: List[SubRegion] = None) -> None:
        if not candidate_clusters and not subregions:
            raise ValueError("A Region requires at least one child SubRegion or CandidateCluster")

        children = []  # type: List[CDSCollection]

        if subregions is None:
            subregions = []
        if candidate_clusters is None:
            candidate_clusters = []

        for region in subregions:
            assert isinstance(region, SubRegion), type(region)
            children.append(region)
        for cluster in candidate_clusters:
            assert isinstance(cluster, CandidateCluster), type(cluster)
            children.append(cluster)

        location = combine_locations(child.location for child in children)

        super().__init__(location, feature_type=self.FEATURE_TYPE, child_collections=children)
        self._subregions = subregions
        self._candidate_clusters = candidate_clusters

        self.clusterblast = None  # type: Optional[List[str]]
        self.knownclusterblast = None  # type: Any
        self.subclusterblast = None  # type: Optional[List[str]]

    @property
    def subregions(self) -> Tuple[SubRegion, ...]:
        """ Returns a list of SubRegion features used to create this region
        """
        return tuple(self._subregions)

    @property
    def candidate_clusters(self) -> Tuple[CandidateCluster, ...]:
        """ Returns a list of CandidateCluster features used to create this region
        """
        return tuple(self._candidate_clusters)

    @property
    def products(self) -> List[str]:
        """ Returns a list of unique products collected from all contained
            CandidateClusters
        """
        products = OrderedDict()  # type: Dict[str, None]
        for cluster in self._candidate_clusters:
            for product in cluster.products:
                products[product] = None
        return list(products) or ["unknown"]

    def get_product_string(self) -> str:
        """ Returns a string of all unique products collected from all
            contained CandidateClusters
        """
        return ",".join(sorted(self.products))

    @property
    def detection_rules(self) -> List[str]:
        """ Returns a list of unique detection rules collected from all
            contained CandidateClusters
        """
        rules = OrderedDict()  # type: Dict[str, str]
        for cluster in self._candidate_clusters:
            for product, rule in zip(cluster.products, cluster.detection_rules):
                rules[product] = rule
        return list(rules.values())

    @property
    def probabilities(self) -> List[float]:
        """ Returns a list of probabilities collected from all contained
            SubRegions that have a probability
        """
        return [sub.probability for sub in self._subregions if sub.probability is not None]

    def add_cds(self, cds: CDSFeature) -> None:
        """ Adds a CDS to the Region and all relevant child collections. Links
            the CDS back to this region
        """
        super().add_cds(cds)
        cds.region = self

    def get_region_number(self) -> int:
        """ Returns the region's numeric ID, only guaranteed to be consistent
            when the same clusters and subregions are defined in the parent record
        """
        if not self._parent_record:
            raise ValueError("Region not in a record")
        return self._parent_record.get_region_number(self)

    def get_unique_protoclusters(self) -> List[Protocluster]:
        """ Returns all Protoclusters contained by CandidateClusters in this region,
            without duplicating them if multiple CandidateClusters contain the same
            Protocluster
        """
        clusters = set()  # type: Set[Protocluster]
        for candidate_cluster in self._candidate_clusters:
            clusters.update(candidate_cluster.protoclusters)
        return sorted(clusters)

    def write_to_genbank(self, filename: str = None, directory: str = None, record: SeqRecord = None) -> None:
        """ Writes a genbank file containing only the information contained
            within the Region.
        """
        if not filename:
            filename = "%s.region%03d.gbk" % (self.parent_record.id, self.get_region_number())
        if directory:
            filename = os.path.join(directory, filename)

        if record is None:
            record = self.parent_record.to_biopython()
        assert isinstance(record, SeqRecord)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cluster_record = record[self.location.start:self.location.end]

        cluster_record.annotations["date"] = record.annotations.get("date", '')
        cluster_record.annotations["source"] = record.annotations.get("source", '')
        cluster_record.annotations["organism"] = record.annotations.get("organism", '')
        cluster_record.annotations["taxonomy"] = record.annotations.get("taxonomy", [])
        cluster_record.annotations["data_file_division"] = record.annotations.get("data_file_division", 'UNK')
        cluster_record.annotations["comment"] = record.annotations.get("comment", '')

        # update the antiSMASH annotation to include some cluster details
        comment_end_marker = "##antiSMASH-Data-END"
        cluster_comment = ("NOTE: This is a single cluster extracted from a larger record!\n"
                           "Orig. start  :: {start}\n"
                           "Orig. end    :: {end}\n"
                           "{end_marker}").format(start=self.location.start,
                                                  end=self.location.end,
                                                  end_marker=comment_end_marker)
        original = cluster_record.annotations["comment"]
        cluster_record.annotations["comment"] = original.replace(comment_end_marker, cluster_comment)

        # our cut-out clusters are always linear
        cluster_record.annotations["topology"] = "linear"

        # renumber clusters, candidate_clusters and regions to reflect changes
        # also update positions of RiPP component locations
        if self.candidate_clusters:
            first_candidate_cluster = min(sc.get_candidate_cluster_number() for sc in self.candidate_clusters)
            first_cluster = min(cluster.get_protocluster_number() for cluster in self.get_unique_protoclusters())
        else:
            first_candidate_cluster = 0
            first_cluster = 0
        first_subregion = min(sub.get_subregion_number() for sub in self.subregions) if self.subregions else 0
        for feature in cluster_record.features:
            if feature.type == Region.FEATURE_TYPE:
                candidates = feature.qualifiers.get("candidate_cluster_numbers")
                if not candidates:
                    continue
                candidates = [str(int(num) - first_candidate_cluster + 1) for num in candidates]
                feature.qualifiers["candidate_cluster_numbers"] = candidates
            elif feature.type == CandidateCluster.FEATURE_TYPE:
                new = str(int(feature.qualifiers["candidate_cluster_number"][0]) - first_candidate_cluster + 1)
                feature.qualifiers["candidate_cluster_number"] = [new]
                new_clusters = [str(int(num) - first_cluster + 1) for num in feature.qualifiers["protoclusters"]]
                feature.qualifiers["protoclusters"] = new_clusters
            elif feature.type in ["protocluster", "proto_core"]:
                new = str(int(feature.qualifiers["protocluster_number"][0]) - first_cluster + 1)
                feature.qualifiers["protocluster_number"] = [new]
            elif feature.type == "subregion":
                new = str(int(feature.qualifiers["subregion_number"][0]) - first_subregion + 1)
                feature.qualifiers["subregion_number"] = [new]
            elif feature.type == "CDS_motif":
                for qual in ["leader_location", "tail_location"]:
                    if qual not in feature.qualifiers:
                        continue
                    loc = location_from_string(feature.qualifiers[qual][0])
                    parts = []
                    for part in loc.parts:
                        new_start = part.start - self.location.start
                        new_end = part.end - self.location.start
                        parts.append(FeatureLocation(new_start, new_end, part.strand))
                    feature.qualifiers[qual] = [str(build_location_from_others(parts))]

        seqio.write([cluster_record], filename, 'genbank')

    def to_biopython(self, qualifiers: Optional[Dict[str, List[str]]] = None) -> List[SeqFeature]:
        if not qualifiers:
            qualifiers = {}
        if self._parent_record:
            qualifiers["region_number"] = [str(self.get_region_number())]
        qualifiers["product"] = self.products
        qualifiers["rules"] = self.detection_rules
        qualifiers["probabilities"] = ["%.4f" % prob for prob in self.probabilities]
        qualifiers["subregion_numbers"] = [str(sub.get_subregion_number()) for sub in self._subregions]
        candidates = [str(cand.get_candidate_cluster_number()) for cand in self._candidate_clusters]
        qualifiers["candidate_cluster_numbers"] = candidates

        return super().to_biopython(qualifiers)

    @classmethod
    def from_biopython(cls: Type[T], bio_feature: SeqFeature, feature: T = None,
                       leftovers: Dict[str, List[str]] = None, record: Any = None) -> T:
        if leftovers is None:
            leftovers = Feature.make_qualifiers_copy(bio_feature)

        candidate_numbers = [int(num) for num in leftovers.pop("candidate_cluster_numbers", [])]
        subregion_numbers = [int(num) for num in leftovers.pop("subregion_numbers", [])]

        if not record:
            raise ValueError("record instance required for regenerating Region from biopython")

        all_candidates = record.get_candidate_clusters()
        all_subs = record.get_subregions()

        if candidate_numbers and max(candidate_numbers) > len(all_candidates):
            raise ValueError("record does not contain all expected candidate clusters")
        if subregion_numbers and max(subregion_numbers) > len(all_subs):
            raise ValueError("record does not contain all expected subregions")

        candidates = [all_candidates[num - 1] for num in candidate_numbers]
        subs = [all_subs[num - 1] for num in subregion_numbers]

        return cls(candidates, subs)

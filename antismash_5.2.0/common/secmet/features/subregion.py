# License: GNU Affero General Public License v3 or later
# A copy of GNU AGPL v3 should have been included in this software package in LICENSE.txt.

""" A class for subregion features """

from typing import Any, Dict, List, Optional, Type, TypeVar

from Bio.SeqFeature import SeqFeature

from .cdscollection import CDSCollection
from .feature import FeatureLocation, Feature

T = TypeVar("T", bound="SubRegion")


class SubRegion(CDSCollection):
    """ A feature which marks a specific region of a record as interesting,
        without being considered a cluster.
    """
    __slots__ = ["tool", "probability", "label"]
    FEATURE_TYPE = "subregion"

    def __init__(self, location: FeatureLocation, tool: str, probability: float = None, label: str = "") -> None:
        super().__init__(location, feature_type=self.FEATURE_TYPE)
        self.tool = tool
        self.probability = probability
        self.label = label  # if anchored to a gene/CDS, this is the name

    def get_subregion_number(self) -> int:
        """ Returns the subregion's numeric ID, only guaranteed to be consistent
            when the same subregions are defined in the parent record
        """
        if not self._parent_record:
            raise ValueError("SubRegion not in a record")
        return self._parent_record.get_subregion_number(self)

    def to_biopython(self, qualifiers: Optional[Dict[str, List[str]]] = None) -> List[SeqFeature]:
        if qualifiers is None:
            qualifiers = {}
        if self._parent_record:
            qualifiers["subregion_number"] = [str(self.get_subregion_number())]
        qualifiers["aStool"] = [self.tool]
        if self.probability is not None:
            qualifiers["probability"] = [str(self.probability)]
        if self.label:
            qualifiers["label"] = [self.label]
        return super().to_biopython(qualifiers)

    @classmethod
    def from_biopython(cls: Type[T], bio_feature: SeqFeature, feature: T = None,
                       leftovers: Optional[Dict] = None, record: Any = None) -> T:
        if leftovers is None:
            leftovers = Feature.make_qualifiers_copy(bio_feature)

        tool = leftovers.pop("aStool")[0]
        probability = None
        if "probability" in leftovers:
            probability = float(leftovers.pop("probability")[0])
        label = leftovers.pop("label", [""])[0]
        if not label:
            label = leftovers.pop("anchor", [""])[0]  # backwards compatibility
        if not feature:
            feature = cls(bio_feature.location, tool, probability, label)

        # remove the subregion_number, as it's not relevant
        leftovers.pop("subregion_number", "")

        # grab parent optional qualifiers
        super().from_biopython(bio_feature, feature=feature, leftovers=leftovers, record=record)
        return feature

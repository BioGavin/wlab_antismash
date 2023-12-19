# License: GNU Affero General Public License v3 or later
# A copy of GNU AGPL v3 should have been included in this software package in LICENSE.txt.

""" A feature to represent a TIGRFam domain match """

from collections import OrderedDict
from typing import Any, Dict, List, Optional, Type, TypeVar

from Bio.SeqFeature import SeqFeature

from antismash.common.secmet.features.antismash_domain import (
    AntismashDomain,
    Feature,
    Location,
    generate_protein_location_from_qualifiers,
    pop_locus_qualifier,
    register_asdomain_variant,
)


T = TypeVar("T", bound="TIGRDomain")

TOOL = "tigrfam"


class TIGRDomain(AntismashDomain):
    """ A feature representing a TIGRFam domain match.
    """

    __slots__ = ('description', 'identifier', 'version')

    def __init__(self, location: Location, description: str, protein_location: Location,
                 identifier: str, locus_tag: str, domain: Optional[str] = None,
                 ) -> None:

        """ Arguments:
                location: the DNA location of the feature
                description: a string with a description from the TIGRFam database
                protein_location: the location within the parent CDS translation
                identifier: the TIGRFam identifier
                locus_tag: the name of the parent CDS feature
                domain: the name for the domain (e.g. Lanthipeptide_RRE)
        """
        super().__init__(location, TOOL, protein_location, locus_tag, domain=domain)
        if not isinstance(description, str):
            raise TypeError(f"TIGRDomain description must be a string, not {type(description)}")
        if not description:
            raise ValueError("TIGRDomain description cannot be empty")
        self.description = description

        if not identifier:
            raise ValueError("TIGRFam identifier cannot be empty")

        if not (len(identifier) == 9 and identifier.startswith('TIGR') and identifier[4:].isdecimal()):
            raise ValueError(f"invalid TIGRFam identifier: {identifier}")
        self.identifier = identifier

    def to_biopython(self, qualifiers: Dict[str, List[str]] = None) -> List[SeqFeature]:
        mine: Dict[str, List[str]] = OrderedDict()
        mine["description"] = [self.description]
        mine["identifier"] = [self.identifier]
        if qualifiers:
            mine.update(qualifiers)
        return super().to_biopython(mine)

    @classmethod
    def from_biopython(cls: Type[T], bio_feature: SeqFeature, feature: T = None,
                       leftovers: Dict[str, List[str]] = None, record: Any = None) -> T:

        if leftovers is None:
            leftovers = Feature.make_qualifiers_copy(bio_feature)

        tool = leftovers.pop("aSTool")[0]
        if tool != TOOL:
            raise ValueError(f"incompatible tool type for {cls}: {tool}")
        protein_location = generate_protein_location_from_qualifiers(leftovers, record)
        # Remove the protein_start and protein_end from the leftovers
        leftovers.pop('protein_start')
        leftovers.pop('protein_end')

        description = leftovers.pop('description')[0]
        locus_tag = pop_locus_qualifier(leftovers, allow_missing=False)
        assert locus_tag
        identifier = leftovers.pop('identifier')[0]
        feature = cls(bio_feature.location, description, protein_location, identifier, locus_tag)

        # grab parent optional qualifiers
        super().from_biopython(bio_feature, feature=feature, leftovers=leftovers, record=record)
        assert feature.domain  # populated in the superclasses
        return feature


register_asdomain_variant(TOOL, TIGRDomain)

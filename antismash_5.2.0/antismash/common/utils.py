# License: GNU Affero General Public License v3 or later
# A copy of GNU AGPL v3 should have been included in this software package in LICENSE.txt.

""" A collection of functions and classes that are used by multiple modules
    within antismash but aren't large enough to justify their own module within
    antismash.common.
"""

from typing import Dict, List

import Bio.Data.IUPACData
from Bio.SeqUtils.ProtParam import ProteinAnalysis
from Bio.SeqFeature import FeatureLocation

from .fasta import read_fasta
from .secmet import Feature, Record


class RobustProteinAnalysis(ProteinAnalysis):
    """ A simple subclass of ProteinAnalysis that can deal with
        a protein sequence containing invalid characters.

        If ignoring invalid characters, the molecular weight is increased by
        the average weight of an amino-acid (i.e. 110) for each invalid case.
    """
    PROTEIN_LETTERS = set(Bio.Data.IUPACData.protein_letters)

    def __init__(self, prot_sequence: str, monoisotopic: bool = False,
                 ignore_invalid: bool = True) -> None:
        if not isinstance(ignore_invalid, bool):
            raise TypeError("ignore_invalid must be a boolean")
        self._ignore_invalid = ignore_invalid

        prot_sequence = prot_sequence.upper()

        self.original_sequence = prot_sequence
        # remove all invalids
        prot_sequence = "".join(filter(lambda x: x in RobustProteinAnalysis.PROTEIN_LETTERS,
                                       self.original_sequence))
        super(RobustProteinAnalysis, self).__init__(prot_sequence, monoisotopic)

    def molecular_weight(self) -> float:
        weight = super(RobustProteinAnalysis, self).molecular_weight()
        if not self._ignore_invalid:
            aa_difference = len(self.original_sequence) - len(self.sequence)
            weight += 110 * aa_difference
        return weight


def extract_by_reference_positions(query: str, reference: str, ref_positions: List[int]) -> str:
    """ Extracts the given positions from a query alignment. The positions are
        adjusted to account for any gaps in the reference sequence.

        Arguments:
            query: the aligned query
            reference: the aligned reference
            ref_positions: the positions of interest in the unaligned reference

        Returns:
            a string containing the sequence elements at the adjusted reference
            positions
    """
    # adjust position of interest to account for gaps in the ref sequence alignment
    positions = []
    position_skipping_gaps = 0
    for i, amino in enumerate(reference):
        if amino in "-.":
            continue
        if position_skipping_gaps in ref_positions:
            positions.append(i)
        position_skipping_gaps += 1
    assert len(positions) == len(ref_positions)
    # extract positions from query sequence
    return "".join([query[i] for i in positions])


def distance_to_pfam(record: Record, query: Feature, hmmer_profiles: List[str]) -> int:
    """ Checks how many nucleotides a gene is away from another gene with one
        of the given Pfams.

        Arguments:
            record: the secmet.Record containing the query and other genes to compare
            query: a secmet.Feature to use the location of
            hmmer_profiles: a list of profile names to search for in CDSFeature
                            domain lists

        Returns:
            the distance (in bases) to the closest gene with one of the profiles
            or -1 if no gene matching was found
    """
    max_range = 40000
    search_range = FeatureLocation(query.location.start - max_range,
                                   query.location.end + max_range)
    close_cds_features = record.get_cds_features_within_location(search_range, with_overlapping=True)
    def distance_between(first: Feature, second: Feature) -> int:
        """ Calculates smallest distance between two feature endpoints """
        return min([abs(first.location.start - second.location.end),
                    abs(first.location.end - second.location.start),
                    abs(first.location.start - second.location.start),
                    abs(first.location.end - second.location.end)
                    ])

    # For nearby CDS features, check if they have hits to the pHMM
    profiles = set(hmmer_profiles)
    closest_distance = -1
    for cds in close_cds_features:
        if cds.sec_met is None:
            continue
        if set(cds.sec_met.domain_ids).intersection(profiles):
            distance = distance_between(query, cds)
            if closest_distance == -1 or distance < closest_distance:
                closest_distance = distance
    return closest_distance


def get_hmm_lengths(hmm_file: str) -> Dict[str, int]:
    """ Finds the lengths of all HMM profiles in the provided HMM file.

        Arguments:
            hmm_file: the HMM file to read

        Returns:
            a dictionary mapping each NAME field in the file to it's LENG field
    """
    lengths = {}
    with open(hmm_file, "r") as handle:
        contents = handle.read()
    contents = contents.replace("\r", "")
    hmms = contents.split("//")[:-1]
    for hmm in hmms:
        namepart = hmm.split("NAME  ")[1]
        name = namepart.split("\n")[0]
        lengthpart = hmm.split("LENG  ")[1]
        length = lengthpart.split("\n")[0]
        lengths[name] = int(length)
    return lengths


def get_fasta_lengths(fasta_file: str) -> Dict[str, int]:
    """ Finds the lengths of all sequences in the provided FASTA file.

        Arguments:
            hmm_file: the FASTA file to read

        Returns:
            a dictionary mapping sequence identifier to sequence length
    """
    fasta = read_fasta(fasta_file)
    return {key: len(val) for key, val in fasta.items()}

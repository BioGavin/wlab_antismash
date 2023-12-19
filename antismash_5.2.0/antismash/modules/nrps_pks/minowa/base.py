# License: GNU Affero General Public License v3 or later
# A copy of GNU AGPL v3 should have been included in this software package in LICENSE.txt.

""" The core of the Minowa method. Removes duplication between similar methods
    (e.g. CAL and AT domain analyses).
"""

import logging
from os import path
from typing import Any, Dict, List, Tuple

from jinja2 import Markup

from antismash.common import subprocessing, utils
from antismash.modules.nrps_pks.data_structures import Prediction


class MinowaPrediction(Prediction):
    """ Holds Minowa results for a domain """
    def __init__(self, results: List[Tuple[str, float]]) -> None:
        super().__init__("minowa")
        assert results
        self.predictions = results

    def get_classification(self) -> List[str]:
        return [self.predictions[0][0]]

    def to_json(self) -> Dict[str, Any]:
        return {"method": "minowa",
                "predictions": self.predictions}

    def as_html(self) -> Markup:
        raw_start = (
            "\n"
            "<dl><dt>Prediction, score:</dt>\n"
            " <dd>\n"
            "  <dl>\n"
        )
        core = "\n".join("  <dd></dd><dt>%s: %.1f</dt>\n" % (name, score) for name, score in self.predictions)
        raw_end = (
            "\n"
            "  </dl>\n"
            " </dd>\n"
            "</dl>\n"
        )
        return Markup("%s%s%s" % (raw_start, core, raw_end))

    @staticmethod
    def from_json(json: Dict[str, Any]) -> "MinowaPrediction":
        assert json["method"] == "minowa"
        return MinowaPrediction(json["predictions"])


def hmmsearch(fasta_format: str, hmm: str) -> float:
    """ Runs hmmsearch, only taking a single value from the output """
    result = subprocessing.execute(["hmmsearch", "--noali", hmm, "-"], stdin=fasta_format)
    if not result.successful():
        logging.error("hmmsearch stderr: %s", result.stderr)
        raise RuntimeError("hmmsearch exited non-zero")

    if "[No targets detected" in result.stdout:
        return 0.

    text = result.stdout
    start = text.find('Domain annotation for each sequence:')
    end = text[start:].find('Internal pipeline statistics summary:')
    lines = text[start:start + end].splitlines()
    return float(lines[4].split()[2])


def get_positions(filename: str, startpos: int) -> List[int]:
    """ Reads the signature positions from the file provided """
    with open(filename, "r") as handle:
        text = handle.read().strip().replace(' ', '_')
    return [int(i) - startpos for i in text.split("\t")]


def run_minowa(sequence_info: Dict[str, str], startpos: int, muscle_ref: str, ref_sequence: str,
               positions_file: str, data_dir: str, hmm_names: List[str]) -> Dict[str, Prediction]:
    """
        Scores query sequences against a set of provided HMM profiles. The scoring
        is calculated by aligning each query against the reference set, then extracting
        a signature by using the sequence positions provided, finally hmmsearch is
        used to compare the signature with the provided set of HMM profiles.

        Arguments:
            sequence_info: a dict mapping sequence id to sequence
            startpos: an int to subtract from those positions in positions_file
            muscle_ref: the path of a file containing reference sequence to align against
            ref_sequence: the reference sequence to base extractions on
            positions_file: the path of a file containing signature extraction positions
            data_dir: the directory containing HMM profiles for the current method
            hmm_names: the names of the HMM profiles for the current method

        Returns:
            an instance of MinowaResults, which is a subclass of dict
                mapping query sequence id to MinowaPrediction
    """
    positions = get_positions(positions_file, startpos)

    results_by_query = {}  # type: Dict[str, Prediction]

    for query_id, query_seq in sequence_info.items():
        muscle = subprocessing.run_muscle_single(query_id, query_seq, muscle_ref)

        # count residues in ref sequence and put positions in list
        # extract positions from query sequence and create fasta formatted seq
        # to use as input for hmm searches
        seq = utils.extract_by_reference_positions(muscle[query_id], muscle[ref_sequence], positions)
        fasta_format = ">%s\n%s\n" % (query_id, seq.replace("-", "X"))

        # then use list to extract positions from every sequence -> HMMs (one time, without any query sequence)
        hmm_scores = {}
        for hmmname in hmm_names:
            hmm_scores[hmmname] = hmmsearch(fasta_format, path.join(data_dir, hmmname + ".hmm"))

        results = sorted(hmm_scores.items(), reverse=True, key=lambda x: (x[1], x[0]))
        results_by_query[query_id] = MinowaPrediction(results)
    return results_by_query

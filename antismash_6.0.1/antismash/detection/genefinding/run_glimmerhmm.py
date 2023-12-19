# License: GNU Affero General Public License v3 or later
# A copy of GNU AGPL v3 should have been included in this software package in LICENSE.txt.

"""Gene finding using GlimmerHMM

   mostly for fungi/eukaryotes
"""

from io import StringIO
import logging

from helperlibs.bio import seqio
from helperlibs.wrappers.io import TemporaryDirectory

from antismash.common import path
from antismash.common.gff_parser import get_features_from_file
from antismash.common.secmet import Record
from antismash.common.subprocessing import execute


def write_search_fasta(record: Record) -> str:
    """ Constructs a FASTA representation of a record and writes it to a
        file in the current directory.

        Returns:
            the name of the file created
    """
    filename = "{}.fasta".format(record.id)
    with open(filename, 'w') as handle:
        seqio.write([record.to_biopython()], handle, 'fasta')
    return filename


def run_external(fasta_filename: str) -> str:
    """ Runs glimmerhmm on the provided fasta file and returns the stdout output
        from glimmerhmm.
    """
    glimmerhmm = ['glimmerhmm', fasta_filename,
                  path.get_full_path(__file__, "data/train_crypto"), "-g"]
    run_result = execute(glimmerhmm)
    if run_result.stderr.find('ERROR') > -1:
        logging.error("Failed to run GlimmerHMM: %r", run_result.stderr)
        raise RuntimeError("Failed to run GlimmerHMM: %s" % run_result.stderr)
    return run_result.stdout


def run_glimmerhmm(record: Record) -> None:
    """ Run glimmerhmm on the record, parse the results and add all detected
        genes to the record
    """
    with TemporaryDirectory(change=True):
        # glimmerHMM/gff_parser handles some record names poorly (e.g. leading - or only '.')
        orig_id = record.id
        record.id = "input"
        # Write FASTA file and run GlimmerHMM
        fasta_file = write_search_fasta(record)
        record.id = orig_id
        results_text = run_external(fasta_file)

    if not "CDS" in results_text:
        return

    handle = StringIO(results_text)
    features = get_features_from_file(handle)["input"]
    for feature in features:
        record.add_biopython_feature(feature)

# License: GNU Affero General Public License v3 or later
# A copy of GNU AGPL v3 should have been included in this software package in LICENSE.txt.

""" Reads GFF files and updates records with the contained information.
"""


import logging
from typing import Dict, IO, List, Set

from Bio.SeqFeature import FeatureLocation, CompoundLocation, SeqFeature
from Bio.SeqRecord import SeqRecord
from BCBio import GFF

from antismash.common.errors import AntismashInputError

# whether to use phase (codon start) to modify reported locations
# Augustus, NCBI, and glimmerhmm report phase but have already adjusted the
# locations and since they're the bulk of inputs, disable further modification
MODIFY_LOCATIONS_BY_PHASE = False


def check_gff_suitability(gff_file: str, sequences: List[SeqRecord]) -> None:
    """
        Checks that the provided GFF3 file is acceptable

        If only a single record is contained in both sequences and GFF, they
        are assumed to be the same.

        Arguments:
            gff_file: the path of the GFF file to check
            sequences: a list of SeqRecords

        Returns:
            None
    """
    try:
        examiner = GFF.GFFExaminer()
        # file handle is automatically closed by GFF lib
        gff_data = examiner.available_limits(open(gff_file))
        # Check if at least one GFF locus appears in sequence
        gff_ids = set([n[0] for n in gff_data['gff_id']])

        if len(gff_ids) == 1 and len(sequences) == 1:
            # If both inputs only have one record, assume is the same,
            # but first check coordinate compatibility
            logging.info("GFF3 and sequence have only one record. Assuming is "
                         "the same as long as coordinates are compatible.")
            limit_info = dict(gff_type=['CDS'])

            record_iter = GFF.parse(open(gff_file), limit_info=limit_info)
            try:
                record = next(record_iter)
            except StopIteration:
                raise AntismashInputError("could not parse records from GFF3 file")

            if not record.features:
                raise AntismashInputError('GFF3 record %s contains no features' % record.id)

            coord_max = max([n.location.end.real for n in record.features])
            if coord_max > len(sequences[0]):
                logging.error('GFF3 record and sequence coordinates are not compatible.')
                raise AntismashInputError('incompatible GFF record and sequence coordinates')

        elif not gff_ids.intersection({seq.id for seq in sequences}):
            logging.error('No GFF3 record IDs match any sequence record IDs.')
            raise AntismashInputError("GFF3 record IDs don't match sequence file record IDs.")

        # Check GFF contains CDSs
        if not ('CDS',) in gff_data['gff_type']:
            logging.error('GFF3 does not contain any CDS.')
            raise AntismashInputError("no CDS features in GFF3 file.")

        # Check CDS are childless but not parentless
        if 'CDS' in set([n for key in examiner.parent_child_map(open(gff_file)) for n in key]):
            logging.error('GFF3 structure is not suitable. CDS features must be childless but not parentless.')
            raise AntismashInputError('GFF3 structure is not suitable.')

    except AssertionError as err:
        # usually the assertion "assert len(parts) >= 8, line"
        # so strip the newline and improve the error message
        message = str(err).strip()
        raise AntismashInputError("parsing GFF failed with invalid format: %r" % message) from err


def get_features_from_file(handle: IO) -> Dict[str, List[SeqFeature]]:
    """ Generates new SeqFeatures from a GFF file.

        Arguments:
            handle: a file handle/stream with the GFF contents

        Returns:
            a dictionary mapping record ID to a list of SeqFeatures for that record
    """
    try:
        gff_records = list(GFF.parse(handle))
    except Exception as err:
        raise AntismashInputError("could not parse records from GFF3 file") from err

    results = {}
    for gff_record in gff_records:
        features = []
        for feature in gff_record.features:
            if feature.type == 'CDS':
                new_features = [feature]
            else:
                new_features = check_sub(feature)
                if not new_features:
                    continue

            name = feature.id
            locus_tag = feature.qualifiers.get("locus_tag")

            for qtype in ["gene", "name", "Name"]:
                if qtype in feature.qualifiers:
                    name_tmp = feature.qualifiers[qtype][0]
                    # Assume name/Name to be sane if they don't contain a space
                    if " " in name_tmp:
                        continue
                    name = name_tmp
                    break

            for i, new_feature in enumerate(new_features):
                variant = name
                if len(new_features) > 1:
                    variant = "{0}_{1}".format(name, i)
                new_feature.qualifiers['gene'] = [variant]
                if locus_tag is not None:
                    new_feature.qualifiers["locus_tag"] = locus_tag
                features.append(new_feature)
        results[gff_record.id] = features
    return results


def run(gff_file: str) -> Dict[str, List[SeqFeature]]:
    """ The entry point of gff_parser.
        Generates new features and adds them to the provided record.

        Arguments:
            options: an antismash.Config object, used only for fetching the GFF path

        Returns:
            a dictionary mapping record ID to a list of SeqFeatures in that record
    """
    with open(gff_file) as handle:
        return get_features_from_file(handle)


def generate_details_from_subfeature(sub_feature: SeqFeature,
                                     existing_qualifiers: Dict[str, List[str]],
                                     locations: List[FeatureLocation],
                                     trans_locations: List[FeatureLocation]) -> Set[str]:
    """ Finds the locations of a subfeature and any mismatching qualifiers

        Arguments:
            sub_feature: the GFF subfeature to work on
            existing_qualifiers: a dict of any existing qualifiers from other
                                 subfeatures
            locations: a list of any existing FeatureLocations from other
                       subfeatures
            trans_locations: a list of any existing FeatureLocations for
                             translations

        Returns:
            a set of qualifiers from the subfeature for which an existing
            qualifier existed but had a different value
    """
    mismatching_qualifiers = set()
    start = sub_feature.location.start.real
    end = sub_feature.location.end.real
    if MODIFY_LOCATIONS_BY_PHASE:
        phase = int(sub_feature.qualifiers.get('phase', [0])[0])
        if sub_feature.strand == 1:
            start += phase
        else:
            end -= phase
    try:
        locations.append(FeatureLocation(start, end, strand=sub_feature.strand))
    except ValueError as err:
        raise AntismashInputError(str(err)) from err
    # Make sure CDSs lengths are multiple of three. Otherwise extend to next full codon.
    # This only applies for translation.
    modulus = (end - start) % 3
    if modulus and sub_feature.strand == 1:
        end += 3 - modulus
    elif modulus and sub_feature.strand == -1:
        start -= 3 - modulus
    trans_locations.append(FeatureLocation(start, end, strand=sub_feature.strand))
    # For split features (CDSs), the final feature will have the same qualifiers as the children ONLY if
    # they're the same, i.e.: all children have the same "protein_ID" (key and value).
    for qual in sub_feature.qualifiers:
        if qual not in existing_qualifiers:
            existing_qualifiers[qual] = sub_feature.qualifiers[qual]
        elif existing_qualifiers[qual] != sub_feature.qualifiers[qual]:
            mismatching_qualifiers.add(qual)
    return mismatching_qualifiers


def check_sub(feature: SeqFeature) -> List[SeqFeature]:
    """ Recursively checks a GFF feature for any subfeatures and generates any
        appropriate SeqFeature instances from them.
    """
    new_features = []
    locations = []  # type: List[FeatureLocation]
    trans_locations = []  # type: List[FeatureLocation]
    qualifiers = {}  # type: Dict[str, List[str]]
    mismatching_qualifiers = set()  # type: Set[str]
    for sub in feature.sub_features:
        if sub.sub_features:  # If there are sub_features, go deeper
            new_features.extend(check_sub(sub))
        elif sub.type == 'CDS':
            sub_mismatch = generate_details_from_subfeature(sub, qualifiers,
                                                            locations, trans_locations)
            mismatching_qualifiers.update(sub_mismatch)

    for qualifier in mismatching_qualifiers:
        del qualifiers[qualifier]
    if 'Parent' in qualifiers:
        del qualifiers['Parent']

    # if nothing to work on
    if not new_features and not locations:
        return []

    # Only works in tip of the tree, when there's no new_feature built yet. If there is,
    # it means the script just came out of a check_sub and it's ready to return.
    if not new_features:
        new_loc = locations[0]
        # construct a compound location if required
        if len(locations) > 1:
            locations = sorted(locations, key=lambda x: x.start.real)
            trans_locations = sorted(trans_locations, key=lambda x: x.start.real)
            if locations[0].strand == 1:
                new_loc = CompoundLocation(locations)
            else:
                new_loc = CompoundLocation(list(reversed(locations)))
                trans_locations = list(reversed(trans_locations))
        new_feature = SeqFeature(new_loc)
        new_feature.qualifiers = qualifiers
        new_feature.type = 'CDS'
        new_features.append(new_feature)

    return new_features

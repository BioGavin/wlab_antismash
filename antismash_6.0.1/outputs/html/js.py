# License: GNU Affero General Public License v3 or later
# A copy of GNU AGPL v3 should have been included in this software package in LICENSE.txt.

""" A collection of functions for converting records, features, and domains into
    JSON for use by the webpage javascript
"""

import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

from antismash.common import html_renderer, path
from antismash.common.module_results import ModuleResults
from antismash.common.secmet import CDSFeature, Feature, Record, Region
from antismash.common.secmet.qualifiers.gene_functions import GeneFunction
from antismash.common.secmet.qualifiers.go import GOQualifier
from antismash.common.secmet.features.cdscollection import CDSCollection
from antismash.common.secmet.features.protocluster import SideloadedProtocluster
from antismash.common.secmet.features.subregion import SideloadedSubRegion
from antismash.config import ConfigType
from antismash.detection.tigrfam.tigr_domain import TIGRDomain
from antismash.modules import clusterblast, tta
from antismash.outputs.html.generate_html_table import generate_html_table

searchgtr_links: Dict[str, str] = {}  # TODO: refactor away from global
GO_URL = 'http://amigo.geneontology.org/amigo/term/'


def convert_records(records: List[Record], results: List[Dict[str, ModuleResults]],
                    options: ConfigType) -> List[Dict[str, Any]]:
    """ Convert multiple Records to JSON """
    json_records = []
    for record, result in zip(records, results):
        json_records.append(convert_record(record, options, result))
    return json_records


def convert_record(record: Record, options: ConfigType, result: Optional[Dict[str, ModuleResults]] = None
                   ) -> Dict[str, Any]:
    """ Convert a Record to JSON """
    if result is None:
        result = {}
    return {
        'length': len(record.seq),
        'seq_id': record.id,
        'regions': convert_regions(record, options, result)
    }


def fetch_tta_features(region: Region, result: Dict[str, ModuleResults]) -> List[Feature]:
    """ Returns a list of all TTA features that overlap with the region """
    hits: List[Feature] = []
    tta_results = result.get(tta.__name__)
    if not tta_results:
        return hits

    assert isinstance(tta_results, tta.TTAResults), type(tta_results)
    for feature in tta_results.features:
        if feature.overlaps_with(region):
            hits.append(feature)

    return hits


def convert_regions(record: Record, options: ConfigType, result: Dict[str, ModuleResults]) -> List[Dict[str, Any]]:
    """Convert Region features to JSON"""
    js_regions = []
    mibig_results: Dict[int, Dict[str, List[clusterblast.results.MibigEntry]]] = {}

    clusterblast_results = result.get(clusterblast.__name__)
    if clusterblast_results is not None:
        assert isinstance(clusterblast_results, clusterblast.results.ClusterBlastResults)
        if clusterblast_results.knowncluster:
            mibig_results = clusterblast_results.knowncluster.mibig_entries

    assert record.record_index  # shouldn't get here without ensuring this
    for region in record.get_regions():
        tta_codons = fetch_tta_features(region, result)

        js_region: Dict[str, Any] = {}
        js_region['start'] = int(region.location.start) + 1
        js_region['end'] = int(region.location.end)
        js_region['idx'] = region.get_region_number()
        mibig_entries = mibig_results.get(js_region['idx'], {})
        js_region['orfs'] = convert_cds_features(record, region.cds_children, options, mibig_entries)
        js_region['clusters'] = get_clusters_from_region(region)
        js_region['ttaCodons'] = convert_tta_codons(tta_codons, record)
        js_region['type'] = region.get_product_string()
        js_region['products'] = region.products
        js_region['anchor'] = "r%dc%d" % (record.record_index, region.get_region_number())

        js_regions.append(js_region)

    return js_regions


def convert_cds_features(record: Record, features: Iterable[CDSFeature], options: ConfigType,
                         mibig_entries: Dict[str, List[clusterblast.results.MibigEntry]]
                         ) -> List[Dict[str, Any]]:
    """ Convert CDSFeatures to JSON """
    js_orfs = []
    for feature in features:
        gene_function = feature.gene_function
        # resistance genes have special markers, not just a colouring, so revert to OTHER
        if gene_function == GeneFunction.RESISTANCE:
            gene_function = GeneFunction.OTHER
        mibig_hits: List[clusterblast.results.MibigEntry] = []
        mibig_hits = mibig_entries.get(feature.get_name(), [])
        description = get_description(record, feature, str(gene_function), options, mibig_hits)
        js_orfs.append({
            "start": feature.location.start + 1,
            "end": feature.location.end,
            "strand": feature.strand or 1,
            "locus_tag": feature.get_name(),
            "type": str(gene_function),
            "description": description,
        })
        if feature.gene_functions.get_by_tool("resist"):  # don't add to every gene for size reasons
            js_orfs[-1]["resistance"] = True
    return js_orfs


def _find_non_overlapping_cluster_groups(collections: Iterable[CDSCollection],
                                         padding: int = 100) -> Dict[CDSCollection, int]:
    """ Finds a group number for each given collection for which no collection in one
        group overlaps with any other collection in the same group.

        Group numbers start at 0 and the leftmost cluster will be in group 0.
        Assumes that the collections provided are sorted.

        Args:
            collections: the collections to group
            padding: the number of base pairs to have as a minimum gap between
                     collections in a group

        Returns:
            a dictionary mapping each CDSCollection to its group number
    """
    if padding < 0:
        raise ValueError("padding cannot be negative")
    if not collections:
        return {}
    groups: List[List[CDSCollection]] = []
    for collection in collections:
        found_group = False
        for group in groups:
            if collection.location.start > group[-1].location.end + padding:
                group.append(collection)
                found_group = True
                break
        if not found_group:  # then start a new group
            groups.append([collection])

    results = {}
    for group_number, group in enumerate(groups):
        for collection in group:
            results[collection] = group_number
    return results


def get_clusters_from_region(region: Region) -> List[Dict[str, Any]]:
    """ Converts all Protoclusters in a collection of CandidateCluster features to JSON """
    js_clusters = []
    candidate_clusters = sorted(region.candidate_clusters, key=lambda x: (x.location.start, -len(x.location)))
    candidate_cluster_groupings = _find_non_overlapping_cluster_groups(candidate_clusters)
    start_index = 0
    for candidate_cluster in candidate_clusters:
        # if it's the only candidate_cluster in the region and it's single, don't draw it to minimise noise
        parent = candidate_cluster.parent
        assert isinstance(parent, Region), type(parent)
        if len(parent.candidate_clusters) == 1 and not parent.subregions and len(candidate_cluster.protoclusters) == 1:
            continue
        js_cluster = {"start": candidate_cluster.location.start + 1,
                      "end": candidate_cluster.location.end - 1,
                      "tool": "",
                      "neighbouring_start": candidate_cluster.location.start,
                      "neighbouring_end": candidate_cluster.location.end,
                      "product": "CC %d: %s" % (candidate_cluster.get_candidate_cluster_number(),
                                                candidate_cluster.kind),
                      "kind": "candidatecluster",
                      "prefix": ""}
        js_cluster['height'] = candidate_cluster_groupings[candidate_cluster]
        js_clusters.append(js_cluster)

    if candidate_cluster_groupings:
        start_index += max(candidate_cluster_groupings.values())

    for subregion in sorted(region.subregions, key=lambda x: (x.location.start, -len(x.location), x.tool)):
        start_index += 1
        prefix = ""
        tool = ""
        if isinstance(subregion, SideloadedSubRegion):
            prefix = subregion.tool + (":" if subregion.label else "")
        else:
            tool = subregion.tool
        js_cluster = {"start": subregion.location.start,
                      "end": subregion.location.end,
                      "tool": tool,
                      "neighbouring_start": subregion.location.start,
                      "neighbouring_end": subregion.location.end,
                      "product": subregion.label,
                      "height": start_index,
                      "prefix": prefix,
                      "kind": "subregion"}
        js_clusters.append(js_cluster)

    start_index += 2  # allow for label above
    clusters = region.get_unique_protoclusters()
    cluster_groupings = _find_non_overlapping_cluster_groups(clusters)
    for cluster in clusters:
        prefix = ""
        if isinstance(cluster, SideloadedProtocluster):
            prefix = f"{cluster.tool}:"
        js_cluster = {"start": cluster.core_location.start,
                      "end": cluster.core_location.end,
                      "tool": cluster.tool,
                      "neighbouring_start": cluster.location.start,
                      "neighbouring_end": cluster.location.end,
                      "product": cluster.product,
                      "height": cluster_groupings[cluster] * 2 + start_index,
                      "kind": "protocluster",
                      "prefix": prefix}
        js_clusters.append(js_cluster)

    return js_clusters


def convert_tta_codons(tta_codons: List[Feature], record: Record) -> List[Dict[str, Any]]:
    """Convert found TTA codon features to JSON"""
    js_codons = []
    for codon in tta_codons:
        cdses = record.get_cds_features_within_location(codon.location, with_overlapping=True)
        js_codons.append({
            'start': codon.location.start + 1,
            'end': codon.location.end,
            'strand': codon.strand if codon.strand is not None else 1,
            'containedBy': [cds.get_name() for cds in cdses]
        })
    return js_codons


def build_pfam2go_links(go_qualifier: Optional[GOQualifier], prefix: str = "") -> List[str]:
    """ A helper for generating Pfam2GO HTML fragments with links and descriptions

        Arguments:
            go_qualifier: the GOQualifier to use for building the links
            prefix: an optional string to prefix the link with

        Returns:
            a list of strings, each being an HTML formatted link prefixed by
            the given prefix and followed by the description of the GO term

    """
    if go_qualifier is None:  # a pfam may have no matching GO terms
        return []
    template = "{prefix}<a class='external-link' href='{url}{go_id}' target='_blank'>{go_id}</a>: {desc}"
    return [template.format(prefix=prefix, url=GO_URL, go_id=go_id, desc=desc)
            for go_id, desc in go_qualifier.go_entries.items()]


def generate_pfam2go_tooltip(record: Record, feature: CDSFeature) -> List[html_renderer.Markup]:
    """Create tooltip text for Pfam to Gene Ontologies results."""
    go_notes = []
    unique_pfams_with_gos = {}
    for pfam in record.get_pfam_domains_in_cds(feature):
        if pfam.gene_ontologies:
            pfam_id = pfam.full_identifier
            unique_pfams_with_gos[pfam_id] = pfam.gene_ontologies
    for unique_id, go_qualifier in sorted(unique_pfams_with_gos.items()):
        go_notes.extend(build_pfam2go_links(go_qualifier, prefix=f"{unique_id}: "))
    return list(map(html_renderer.Markup, go_notes))


def generate_asf_tooltip_section(record: Record, feature: CDSFeature) -> Dict[Tuple[str, int, int], List[str]]:
    """ Construct tooltip text for activesitefinder annotations """
    asf_notes = {}
    for domain in feature.nrps_pks.domains:
        hits = record.get_domain_by_name(domain.feature_name).asf.hits
        if hits:
            asf_notes[(domain.name, domain.start, domain.end)] = hits
    for pfam in record.get_pfam_domains_in_cds(feature):
        if not pfam.domain:
            continue
        if pfam.asf.hits:
            asf_notes[(pfam.domain, pfam.protein_location.start, pfam.protein_location.end)] = pfam.asf.hits
    return asf_notes


def generate_pfam_tooltip(record: Record, feature: CDSFeature) -> List[str]:
    """ Construct tooltip text for PFAM annotations """
    pfam_notes = []
    for pfam in record.get_pfam_domains_in_cds(feature):
        pfam_notes.append(f"{pfam.full_identifier} ({pfam.description}): {pfam.protein_location}"
                          f"(score: {pfam.score}, e-value: {pfam.evalue})")
    return pfam_notes


def generate_tigr_tooltip(record: Record, feature: CDSFeature) -> List[str]:
    """ Construct tooltip text for TIGRFam annotations """
    tigr_notes = []
    for tigr in record.get_antismash_domains_in_cds(feature):
        if not isinstance(tigr, TIGRDomain):
            continue
        tigr_notes.append(f"{tigr.identifier} ({tigr.description}): {tigr.protein_location}"
                          f"(score: {tigr.score}, e-value: {tigr.evalue})")
    return tigr_notes


def get_description(record: Record, feature: CDSFeature, type_: str,
                    options: ConfigType, mibig_result: List[clusterblast.results.MibigEntry]) -> str:
    "Get the description text of a CDS feature"

    urls = {
        "blastp": ("http://blast.ncbi.nlm.nih.gov/Blast.cgi?PAGE=Proteins&"
                   "PROGRAM=blastp&BLAST_PROGRAMS=blastp&QUERY=%s&"
                   "LINK_LOC=protein&PAGE_TYPE=BlastSearch") % feature.translation,
        "mibig": "",
        "transport": "",
        "smcog_tree": ""
    }

    genomic_context_url = "http://www.ncbi.nlm.nih.gov/projects/sviewer/?" \
                          "Db=gene&DbFrom=protein&Cmd=Link&noslider=1&"\
                          "id=%s&from=%s&to=%s"

    if mibig_result:
        assert feature.region
        region_number = feature.region.get_region_number()
        mibig_homology_file = os.path.join(options.output_dir, "knownclusterblast",
                                           "region%d" % region_number,
                                           feature.get_accession() + '_mibig_hits.html')
        generate_html_table(mibig_homology_file, mibig_result)
        urls["mibig"] = mibig_homology_file[len(options.output_dir) + 1:]

    if type_ == 'transport':
        urls["transport"] = ("http://blast.jcvi.org/er-blast/index.cgi?project=transporter;"
                             "program=blastp;database=pub/transporter.pep;"
                             "sequence=sequence%%0A%s") % feature.translation

    urls["context"] = genomic_context_url % (record.id,
                                             max(feature.location.start - 9999, 0),
                                             min(feature.location.end + 10000, len(record)))

    if options.smcog_trees:
        for note in feature.notes:  # TODO find a better way to store image urls
            if note.startswith('smCOG tree PNG image:'):
                urls["smcog_tree"] = note.split(':')[-1]
                break

    asf_notes = generate_asf_tooltip_section(record, feature)
    go_notes = generate_pfam2go_tooltip(record, feature)
    pfam_notes = generate_pfam_tooltip(record, feature)
    tigr_notes = generate_tigr_tooltip(record, feature)

    urls["searchgtr"] = searchgtr_links.get("{}_{}".format(record.id, feature.get_name()), "")
    template = html_renderer.FileTemplate(path.get_full_path(__file__, "templates", "cds_detail.html"))
    ec_numbers = ""
    ec_number_qual = feature.get_qualifier("EC_number")
    if isinstance(ec_number_qual, list):
        ec_numbers = ",".join(ec_number_qual)
    return template.render(feature=feature, ec_numbers=ec_numbers, go_notes=go_notes,
                           asf_notes=asf_notes, pfam_notes=pfam_notes, tigr_notes=tigr_notes,
                           record=record, urls=urls)

# License: GNU Affero General Public License v3 or later
# A copy of GNU AGPL v3 should have been included in this software package in LICENSE.txt.

""" Manages HTML construction for the Lassopeptide module
"""

from typing import List

from antismash.common import path
from antismash.common.html_renderer import HTMLSections, FileTemplate
from antismash.common.layers import RecordLayer, RegionLayer, OptionsLayer

from .specific_analysis import LassoResults


def will_handle(products: List[str]) -> bool:
    """ Returns True if the products provided are relevant to the module """
    return 'lassopeptide' in products


def generate_html(region_layer: RegionLayer, results: LassoResults,
                  record_layer: RecordLayer, _options_layer: OptionsLayer) -> HTMLSections:
    """ Generates HTML for the module """
    html = HTMLSections("lassopeptides")

    motifs_in_region = {}
    for locus in results.motifs_by_locus:
        if record_layer.get_cds_by_name(locus).is_contained_by(region_layer.region_feature):
            motifs_in_region[locus] = results.motifs_by_locus[locus]

    detail_tooltip = ("Lists the possible core peptides for each biosynthetic enzyme, including the predicted class. "
                      "Each core peptide shows the leader and core peptide sequences, separated by a dash.")

    template = FileTemplate(path.get_full_path(__file__, "templates", "details.html"))
    html.add_detail_section("Lasso peptides", template.render(results=motifs_in_region, tooltip=detail_tooltip))

    side_tooltip = ("Lists the possible core peptides in the region. "
                    "Each core peptide lists the number of disulfide bridges, possible molecular weights, "
                    "and the scores for cleavage site prediction and RODEO.")
    template = FileTemplate(path.get_full_path(__file__, "templates", "sidepanel.html"))
    html.add_sidepanel_section("Lasso peptides", template.render(results=motifs_in_region, tooltip=side_tooltip))

    return html

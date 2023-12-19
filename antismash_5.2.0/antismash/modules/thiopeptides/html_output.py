# License: GNU Affero General Public License v3 or later
# A copy of GNU AGPL v3 should have been included in this software package in LICENSE.txt.

""" HTML generation for the thiopeptides module """

from typing import List

from antismash.common import path
from antismash.common.html_renderer import HTMLSections, FileTemplate
from antismash.common.layers import RegionLayer, RecordLayer, OptionsLayer
from antismash.common.secmet import Region, Prepeptide

from .specific_analysis import ThioResults


def will_handle(products: List[str]) -> bool:
    """ HTML generation only occurs if this function reutrns True """
    return 'thiopeptide' in products


class ThiopeptideLayer(RegionLayer):
    """ A wrapper of RegionLayer to allow for tracking the ThiopeptideMotifs """
    def __init__(self, record: RecordLayer, results: ThioResults, region_feature: Region) -> None:
        RegionLayer.__init__(self, record, region_feature)
        self.motifs = []  # type: List[Prepeptide]
        for motif in results.motifs:
            if motif.is_contained_by(self.region_feature) and isinstance(motif, Prepeptide):
                self.motifs.append(motif)


def generate_html(region_layer: RegionLayer, results: ThioResults,
                  record_layer: RecordLayer, options_layer: OptionsLayer
                  ) -> HTMLSections:
    """ Generates HTML for the module """
    html = HTMLSections("thiopeptides")

    if not results:
        return html

    thio_layer = ThiopeptideLayer(record_layer, results, region_layer.region_feature)

    detail_tooltip = ("Lists the possible core peptides for each biosynthetic enzyme, including the predicted class. "
                      "Each core peptide shows the leader and core peptide sequences, separated by a dash. "
                      "Predicted tail sequences are also shown.")
    template = FileTemplate(path.get_full_path(__file__, "templates", "details.html"))
    details = template.render(record=record_layer,
                              cluster=thio_layer,
                              options=options_layer,
                              tooltip=detail_tooltip)
    html.add_detail_section("Thiopeptides", details)

    side_tooltip = ("Lists the possible core peptides in the region. "
                    "Each core peptide lists its possible molecular weights "
                    "and the scores for cleavage site prediction and RODEO. "
                    "If relevant, other features, such as macrocycle and amidation, will also be listed.")
    template = FileTemplate(path.get_full_path(__file__, "templates", "sidepanel.html"))
    sidepanel = template.render(record=record_layer,
                                cluster=thio_layer,
                                options=options_layer,
                                tooltip=side_tooltip)
    html.add_sidepanel_section("Thiopeptides", sidepanel)
    return html

# License: GNU Affero General Public License v3 or later
# A copy of GNU AGPL v3 should have been included in this software package in LICENSE.txt.

""" Responsible for creating the single web page results """

import importlib
import json
import pkgutil
import string
import os
from typing import cast, Any, Dict, List, Tuple, Union, Optional

from antismash.common import path
from antismash.common.html_renderer import (
    FileTemplate,
    HTMLSections,
    docs_link,
    get_antismash_js_version,
    get_antismash_js_url,
)
from antismash.common.layers import RecordLayer, RegionLayer, OptionsLayer
from antismash.common.module_results import ModuleResults
from antismash.common.secmet import Record
from antismash.common.json import JSONOrf
from antismash.config import ConfigType
from antismash.modules import tfbs_finder as tfbs, tta
from antismash.outputs.html import js
from antismash.custom_typing import AntismashModule, VisualisationModule

from .visualisers import gene_table

TEMPLATE_PATH = path.get_full_path(__file__, "templates")


def _get_visualisers() -> List[VisualisationModule]:
    """ Gather all the visualisation-only submodules """
    modules = []
    for module_data in pkgutil.walk_packages([path.get_full_path(__file__, "visualisers")]):
        module = importlib.import_module(f"antismash.outputs.html.visualisers.{module_data.name}")
        assert hasattr(module, "has_enough_results"), f"bad visualisation module: {module_data.name}"
        modules.append(cast(VisualisationModule, module))
    return modules


VISUALISERS = _get_visualisers()


def build_json_data(records: List[Record], results: List[Dict[str, ModuleResults]],
                    options: ConfigType, all_modules: List[AntismashModule]) -> Tuple[
                        List[Dict[str, Any]],
                        List[Dict[str, Union[str, List[JSONOrf]]]],
                        Dict[str, Dict[str, Dict[str, Any]]]
                    ]:
    """ Builds JSON versions of records and domains for use in drawing SVGs with
        javascript.

        Arguments:
            records: a list of Records to convert
            results: a dictionary mapping record id to a list of ModuleResults to convert
            options: antiSMASH options

        Returns:
            a tuple of
                a list of JSON-friendly dicts representing records
                a list of JSON-friendly dicts representing domains
    """

    js_records = js.convert_records(records, results, options)

    js_domains: List[Dict[str, Union[str, List[JSONOrf]]]] = []
    js_results = {}

    for i, record in enumerate(records):
        json_record = js_records[i]
        json_record['seq_id'] = "".join(char for char in json_record['seq_id'] if char in string.printable)
        for region, json_region in zip(record.get_regions(), json_record['regions']):
            handlers = find_plugins_for_cluster(all_modules, json_region)
            region_results = {}
            for handler in handlers:
                # if there's no results for the module, don't let it try
                if handler.__name__ not in results[i]:
                    continue
                if "generate_js_domains" in dir(handler):
                    domains_by_region = handler.generate_js_domains(region, record)
                    if domains_by_region:
                        js_domains.append(domains_by_region)
                if hasattr(handler, "generate_javascript_data"):
                    data = handler.generate_javascript_data(record, region, results[i][handler.__name__])
                    region_results[handler.__name__] = data

            for aggregator in VISUALISERS:
                if not hasattr(aggregator, "generate_javascript_data"):
                    continue
                if aggregator.has_enough_results(record, region, results[i]):
                    data = aggregator.generate_javascript_data(record, region, results[i])
                    region_results[aggregator.__name__] = data

            if region_results:
                js_results[RegionLayer.build_anchor_id(region)] = region_results

    return js_records, js_domains, js_results


def write_regions_js(records: List[Dict[str, Any]], output_dir: str,
                     js_domains: List[Dict[str, Any]],
                     module_results: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
    """ Writes out the cluster and domain JSONs to file for the javascript sections
        of code"""

    with open(os.path.join(output_dir, "regions.js"), "w", encoding="utf-8") as handle:
        handle.write(f"var recordData = {json.dumps(records, indent=1)};\n")
        regions: Dict[str, Any] = {"order": []}
        for record in records:
            for region in record['regions']:
                regions[region['anchor']] = region
                regions['order'].append(region['anchor'])
        handle.write(f"var all_regions = {json.dumps(regions, indent=1)};\n")

        details = {
            "nrpspks": {region["id"]: region for region in js_domains},
        }
        handle.write(f"var details_data = {json.dumps(details, indent=1)};\n")
        handle.write(f"var resultsData = {json.dumps(module_results, indent=1)};\n")


def generate_html_sections(records: List[RecordLayer], results: Dict[str, Dict[str, ModuleResults]],
                           options: ConfigType) -> Dict[str, Dict[int, List[HTMLSections]]]:
    """ Generates a mapping of record->region->HTMLSections for each record, region and module

        Arguments:
            records: a list of RecordLayers to pass through to the modules
            results: a dictionary mapping record name to
                        a dictionary mapping each module name to its results object
            options: the current antiSMASH config

        Returns:
            a dictionary mapping record id to
                a dictionary mapping region number to
                    a list of HTMLSections, one for each module
    """
    details = {}
    for record in records:
        record_details = {}
        record_result = results[record.id]
        for region in record.regions:
            sections = []
            for handler in region.handlers:
                if handler.will_handle(region.products, region.product_categories):
                    handler_results = record_result.get(handler.__name__)
                    if handler_results is None:
                        continue
                    sections.append(handler.generate_html(region, handler_results, record, options))
            for aggregator in VISUALISERS:
                if not hasattr(aggregator, "generate_html"):
                    continue
                if aggregator.has_enough_results(record.seq_record, region.region_feature, record_result):
                    section = aggregator.generate_html(region, record_result, record, options)
                    # as a special case, the first section of a region should always be the gene table
                    if aggregator is gene_table:
                        sections.insert(0, section)
                    else:
                        sections.append(section)
            record_details[region.get_region_number()] = sections
        details[record.id] = record_details
    return details


def find_local_antismash_js_path(options: ConfigType) -> Optional[str]:
    """ Finds the a path to a local copy of antismash.js, if possible,
        otherwise returns None.
    """
    # is a copy in the js directory?
    js_path = path.locate_file(path.get_full_path(__file__, "js", "antismash.js"), silent=True)
    if js_path:
        return js_path

    # is it in the databases?
    version = get_antismash_js_version()
    js_path = path.locate_file(os.path.join(options.database_dir, "as-js", version, "antismash.js"), silent=True)
    if js_path:
        return js_path

    # then it doesn't exist
    return None


def build_antismash_js_url(options: ConfigType) -> str:
    """ Build the URL to the javascript that will be embedded in the HTML.
        If a local version is available, it will be copied into the output directory,
        otherwise a full remote URL will be used.

        Arguments:
            options: the antiSMASH config

        Returns:
            a string of the URL, whether relative or absolute
    """
    if find_local_antismash_js_path(options):
        return "js/antismash.js"  # generic local path after copy
    return get_antismash_js_url()


def generate_webpage(records: List[Record], results: List[Dict[str, ModuleResults]],
                     options: ConfigType, all_modules: List[AntismashModule]) -> str:
    """ Generates the HTML itself """

    generate_searchgtr_htmls(records, options)
    json_records, js_domains, js_results = build_json_data(records, results, options, all_modules)
    write_regions_js(json_records, options.output_dir, js_domains, js_results)

    template = FileTemplate(os.path.join(TEMPLATE_PATH, "overview.html"))

    options_layer = OptionsLayer(options, all_modules)
    record_layers_with_regions = []
    record_layers_without_regions = []
    results_by_record_id: Dict[str, Dict[str, ModuleResults]] = {}
    for record, record_results in zip(records, results):
        if record.get_regions():
            record_layers_with_regions.append(RecordLayer(record, None, options_layer))
        else:
            record_layers_without_regions.append(RecordLayer(record, None, options_layer))
        results_by_record_id[record.id] = record_results

    regions_written = sum(len(record.get_regions()) for record in records)
    job_id = os.path.basename(options.output_dir)
    page_title = options.output_basename
    if options.html_title:
        page_title = options.html_title

    html_sections = generate_html_sections(record_layers_with_regions, results_by_record_id, options)

    svg_tooltip = ("Shows the layout of the region, marking coding sequences and areas of interest. "
                   "Clicking a gene will select it and show any relevant details. "
                   "Clicking an area feature (e.g. a candidate cluster) will select all coding "
                   "sequences within that area. Double clicking an area feature will zoom to that area. "
                   "Multiple genes and area features can be selected by clicking them while holding the Ctrl key."
                   )
    doc_target = "understanding_output/#the-antismash-5-region-concept"
    svg_tooltip += f"<br>More detailed help is available {docs_link('here', doc_target)}."

    as_js_url = build_antismash_js_url(options)

    content = template.render(records=record_layers_with_regions, options=options_layer,
                              version=options.version, extra_data=js_domains,
                              regions_written=regions_written, sections=html_sections,
                              results_by_record_id=results_by_record_id,
                              config=options, job_id=job_id, page_title=page_title,
                              records_without_regions=record_layers_without_regions,
                              svg_tooltip=svg_tooltip, get_region_css=js.get_region_css,
                              as_js_url=as_js_url, tta_name=tta.__name__, tfbs_name=tfbs.__name__,
                              )
    return content


def find_plugins_for_cluster(plugins: List[AntismashModule],
                             cluster: Dict[str, Any]) -> List[AntismashModule]:
    "Find a specific plugin responsible for a given gene cluster type"
    products = cluster['products']
    categories = set(cluster['product_categories'])
    handlers = []
    for plugin in plugins:
        if not hasattr(plugin, 'will_handle'):
            continue
        if plugin.will_handle(products, categories):
            handlers.append(plugin)
    return handlers


def load_searchgtr_search_form_template() -> List[str]:
    """ for SEARCHGTR HTML files, load search form template """
    with open(os.path.join(TEMPLATE_PATH, "searchgtr_form.html"),
              "r", encoding="utf-8") as handle:
        template = handle.read().replace("\r", "\n")
    return template.split("FASTASEQUENCE")


def generate_searchgtr_htmls(records: List[Record], options: ConfigType) -> None:
    """ Generate lists of COGs that are glycosyltransferases or transporters """
    gtrcoglist = ['SMCOG1045', 'SMCOG1062', 'SMCOG1102']
    searchgtrformtemplateparts = load_searchgtr_search_form_template()
    # TODO store somewhere sane
    js.searchgtr_links = {}
    for record in records:
        for feature in record.get_cds_features():
            smcog_functions = feature.gene_functions.get_by_tool("smcogs")
            if not smcog_functions:
                continue
            smcog = smcog_functions[0].description.split(":")[0]
            if smcog not in gtrcoglist:
                continue
            html_dir = os.path.join(options.output_dir, "html")
            if not os.path.exists(html_dir):
                os.mkdir(html_dir)
            formfileloc = os.path.join(html_dir, feature.get_name() + "_searchgtr.html")
            link_loc = os.path.join("html", feature.get_name() + "_searchgtr.html")
            gene_id = feature.get_name()
            js.searchgtr_links[record.id + "_" + gene_id] = link_loc
            with open(formfileloc, "w", encoding="utf-8") as formfile:
                specificformtemplate = searchgtrformtemplateparts[0].replace("GlycTr", gene_id)
                formfile.write(specificformtemplate)
                formfile.write(f"{gene_id}\n{feature.translation}")
                formfile.write(searchgtrformtemplateparts[1])

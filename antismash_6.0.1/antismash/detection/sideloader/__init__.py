# License: GNU Affero General Public License v3 or later
# A copy of GNU AGPL v3 should have been included in this software package in LICENSE.txt.

""" A collection of sideloaders
"""

import argparse
import os
from typing import Any, AnyStr, Dict, List, Optional

from antismash.common.module_results import DetectionResults
from antismash.common.secmet import Record
from antismash.config import ConfigType
from antismash.config.args import ModuleArgs, MultipleFullPathAction

from .data_structures import SideloadedResults, SideloadSimple
from .general import load_single_record_annotations
from .html_output import generate_html, will_handle

NAME = "sideloader"
SHORT_DESCRIPTION = "Side-loaded annotations"


def _parse_arg(option: str) -> SideloadSimple:
    """ Parses a string in the form ACCESSION:START-END into a matching
        SideloadSimple instance
    """
    error = ValueError("invalid format, expected ACCESSION:START-END")
    parts = option.split(":")
    if len(parts) != 2:
        raise error
    if not parts[0]:
        raise error
    positions = parts[1].split("-")
    if len(positions) != 2:
        raise error
    try:
        start = int(positions[0])
        end = int(positions[1])
    except ValueError:
        raise ValueError("positions are not numeric")
    if start >= end:
        raise ValueError("start must be before end")
    return SideloadSimple(parts[0], start, end)


class SideloadAction(argparse.Action):
    """ An argparse.Action to ensure the sideload-simple argument is valid
        before antiSMASH starts a run.
    """
    def __call__(self, parser: argparse.ArgumentParser, namespace: argparse.Namespace,  # type: ignore
                 values: AnyStr, option_string: str = None) -> None:
        try:
            result = _parse_arg(str(values))
        except Exception as err:
            raise argparse.ArgumentError(self, str(err))
        setattr(namespace, self.dest, result)


def get_arguments() -> ModuleArgs:
    """ Constructs commandline arguments and options for this module
    """
    args = ModuleArgs("Advanced options", "sideload")
    args.add_option("sideload",
                    dest="sideload",
                    metavar="JSON",
                    action=MultipleFullPathAction,
                    default=[],
                    help=("Sideload annotations from the JSON file in the given paths. "
                          "Multiple files can be provided, separated by a comma."))
    args.add_option("sideload-simple",
                    dest="sideload_simple",
                    metavar="ACCESSION:START-END",
                    action=SideloadAction,
                    default="",
                    help=("Sideload a single subregion in record ACCESSION from START "
                          "to END. Positions are expected to be 0-indexed, "
                          "with START inclusive and END exclusive."))
    return args


def check_options(options: ConfigType) -> List[str]:
    """ Checks the options to see if there are any issues before
        running any analyses
    """
    errors = []
    for filename in options.sideload:
        if not os.path.exists(filename):
            errors.append("Extra annotation JSON cannot be found at '%s'" % filename)
    if len(set(options.sideload)) != len(options.sideload):
        errors.append("Sideloaded filenames contain duplicates")

    return errors


def is_enabled(options: ConfigType) -> bool:
    """  Uses the supplied options to determine if the module should be run
    """
    return options.sideload or options.sideload_simple


def regenerate_previous_results(results: Dict[str, Any], record: Record,
                                _options: ConfigType) -> Optional[SideloadedResults]:
    """ Regenerate previous results. """
    if not results:
        return None

    return SideloadedResults.from_json(results, record)


def run_on_record(record: Record, previous_results: Optional[SideloadedResults],
                  options: ConfigType) -> Optional[DetectionResults]:
    """ Finds the external annoations for the given record """

    if previous_results:
        return previous_results

    return load_single_record_annotations(options.sideload, record.id, options.sideload_simple)


def check_prereqs(_options: ConfigType) -> List[str]:
    """ Checks that prerequisites are satisfied.
    """
    return []

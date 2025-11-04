# ----------------------------------------------------------------------------
# Copyright (c) 2016-2025, QIIME 2 development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file LICENSE, distributed with this software.
# ----------------------------------------------------------------------------
import abc
import os
import pandas as pd
import pathlib
import tempfile
import warnings
import yaml
from zipfile import ZipFile

from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
from typing import Any, Dict, List, Optional, Set, Tuple

import bibtexparser as bp
import networkx as nx

from ._checksum_validator import (
    ValidationCode, ChecksumDiff, validate_checksums
)
from .util import parse_version
from ..provenance import MetadataInfo
from qiime2.sdk import Result


@dataclass
class Config():
    '''
    Dataclass that stores user-selected configuration options.

    Attributes
    ----------
    perform_checksum_validation : bool
        Whether to opt in or out of checksum validation.
    parse_study_metadata : bool
        Whether to parse study metadata stored in provenance.
    recurse : bool
        Whether to recursively parse nested directories that contain artifacts.
    verbose : bool
        Whether to print status messages to stdout during processing.
    '''
    perform_checksum_validation: bool = True
    parse_study_metadata: bool = True
    recurse: bool = False
    verbose: bool = False


@dataclass
class ParserResults():
    '''
    Results generated and returned by a ParserVx.

    Attributes
    ----------
    parsed_artifact_uuids : set of str
        The uuids of the artifacts directly parsed by a parser. Does not
        include the uuids of artifact parsed from provenance. When parsing
        a single archive this is a single member set of that uuid. When
        parsing a directory, it is the set of all artifact uuids in that
        directory.
    prov_digraph : nx.Digraph
        The directed acyclic graph representation of the parsed provenance as
        an nx.DiGraph object.
    provenance_is_valid : ValidationCode
        A flag indicating the level of checksum validation.
    checksum_diff : ChecksumDiff or None
        A tuple of three dictionaries indicating the uuids of files that have
        been 1) added 2) removed or 3) changed in the archive since the
        archive was checksummed.
        None if no checksum validation was perfomed, e.g. when opted out or
        impossible because archive version did not support checksums, or when
        checksums.md5 missing from archive where it was expected.
        Interpretable only in conjunction with provenance_is_valid.
    '''
    parsed_artifact_uuids: Set[str]
    prov_digraph: nx.DiGraph
    provenance_is_valid: ValidationCode
    checksum_diff: Optional[ChecksumDiff]


class ProvNode:
    '''
    One node of a provenance DAG, describing one QIIME2 Result.
    '''

    @property
    def _uuid(self) -> str:
        return self._result_md.uuid

    @_uuid.setter
    def _uuid(self, new_uuid: str):
        '''
        ProvNode's UUID. Safe for use as getter. Prefer ProvDAG.relabel_nodes
        as a setter because it preserves alignment between ids across the dag
        and its ProvNodes.
        '''
        self._result_md.uuid = new_uuid

    @property
    def type(self) -> str:
        return self._result_md.type

    @property
    def format(self) -> Optional[str]:
        return self._result_md.format

    @property
    def archive_version(self) -> str:
        return self._archive_version

    @property
    def framework_version(self) -> str:
        return self._framework_version

    @property
    def has_provenance(self) -> bool:
        if '.' in self.archive_version:
            return float(self.archive_version) >= 7.0
        else:
            return int(self.archive_version) > 1

    @property
    def citations(self) -> Dict:
        citations = {}
        if hasattr(self, '_citations'):
            citations = self._citations.citations
        return citations

    @property
    def metadata(self) -> Optional[Dict[str, pd.DataFrame]]:
        '''
        A dict containing {parameter_name: metadata_dataframe} pairs where
        parameter_name is the registered name of the parameter the Metadata
        or MetadataColumn was passed to.

        Returns an empty dict if this action takes no Metadata or
        MetadataColumn.

        Returns None if this action has no metadata because the archive has no
        provenance, or the user opted out of metadata parsing.
        '''
        self._metadata: Optional[Dict[str, pd.DataFrame]]

        md = None
        if hasattr(self, '_metadata'):
            md = self._metadata
        return md

    @property
    def _parents(self) -> Optional[List[Dict[str, str]]]:
        '''
        A list of single-item {Type: UUID} dicts describing this
        action's inputs, including Artifacts passed as Metadata parameters.

        Returns [] if this action is an Import.

        NOTE: This property is private because it is slightly unsafe,
        reporting original node IDs that are not updated if the user renames
        nodes using the networkx API instead of ProvDAG.relabel_nodes.
        ProvDAG and its extensions should use the networkx.DiGraph itself to
        work with ancestry when possible.
        '''
        if not self.has_provenance:
            return None

        inputs = self.action._action_details.get('inputs')
        parents = []
        if inputs is not None:
            # Inputs are a list of single-item dicts
            for input in inputs:
                (name, value), = input.items()
                # value is usually a uuid, but may be a collection of uuids
                # the following are specced in qiime2/core/type/collection
                if type(value) in (set, list, tuple):
                    for i in range(len(value)):
                        # Make these unique in case the single-item dicts get
                        # merged into a single dict downstream
                        if type(value[i]) is dict:
                            unq_name, = value[i].keys()
                            v, = value[i].values()
                        else:
                            unq_name = f'{name}_{i}'
                            v = value[i]
                        parents.append({unq_name: v})
                elif value is not None:
                    parents.append({name: value})
                else:
                    # skip None-by-default optional inputs
                    pass

        return parents + self._artifacts_passed_as_md

    def __init__(
        self,
        cfg: Config,
        zf: ZipFile,
        node_fps: List[pathlib.Path]
    ):
        '''
        Constructs a ProvNode from a zipfile and the collected
        provenance-relevant filepaths for a single result within it.
        '''
        for fp in node_fps:
            if fp.name == 'VERSION':
                self._archive_version, self._framework_version = \
                    parse_version(zf)
            elif fp.name == 'metadata.yaml':
                self._result_md = _ResultMetadata(zf, str(fp))
            elif fp.name == 'action.yaml':
                self.action = _Action(zf, str(fp))
            elif fp.name == 'citations.bib':
                self._citations = _Citations(zf, str(fp))
            elif fp.name == 'checksums.md5':
                # Handled in ProvDAG
                pass

        if self.has_provenance:
            all_metadata_fps, self._artifacts_passed_as_md = \
                self._get_metadata_from_Action(self.action._action_details)
            if cfg.parse_study_metadata:
                self._metadata = self._parse_metadata(zf, all_metadata_fps)

    def _get_metadata_from_Action(
        self, action_details: Dict[str, List]
    ) -> Tuple[Dict[str, str], List[Dict[str, str]]]:
        '''
        Gathers data related to Metadata and MetadataColumn-based metadata
        files from the parsed action.yaml file.

        Captures filepath and parameter-name data for all study metadata
        files, so that these can be located for parsing, and then associated
        with the correct parameters during replay. It captures uuids for all
        artifacts passed to this action as metadata so they can be included as
        parents of this node.

        Parameters
        ----------
        action_details : dict
            The parsed dictionary of the `action` section from action.yaml.

        Returns
        -------
        tuple of (all_metadata, artifacts_as_metadata)
            Where all_metadata is a dict of
            {parameter_name: filename}.
            Where artifacts_as_metadata is a list of single-items dict of the
            structure {'artifact_passed_as_metadata': <uuid>}.

        Notes
        -----
        When Artifacts are passed as Metadata, they are captured in
        action['parameters'], rather than in action['inputs'] with the other
        Artifacts. Semantic Type data is thus not captured. This function
        returns a filler 'Type' for all UUIDs discovered here:
        'artifact_passed_as_metadata'. Because Artifacts passed (viewed) as
        Metadata retain their provenance, downstream Artifacts are linked to
        their real parent Artifact nodes with the proper Type information.
        '''
        all_metadata = dict()
        artifacts_as_metadata = []
        if (all_params := action_details.get('parameters')) is not None:
            for param in all_params:
                param_val, = param.values()
                if isinstance(param_val, MetadataInfo):
                    param_name, = param.keys()
                    md_fp = param_val.relative_fp
                    all_metadata.update({param_name: md_fp})

                    artifacts_as_metadata += [
                        {'artifact_passed_as_metadata': uuid} for uuid in
                        param_val.input_artifact_uuids
                    ]

        return all_metadata, artifacts_as_metadata

    def _parse_metadata(
        self, zf: ZipFile, metadata_fps: Dict[str, str]
    ) -> Dict[str, pd.DataFrame]:
        '''
        Parses all metadata files captured from Metadata and MetadataColumns
        (identifiable by !metadata tags) into pd.DataFrames.

        Parameters
        ----------
        zf : ZipFile
            The zipfile object of the archive.
        metadata_fps : dict
            A dict of parameter names to metadata filenames for metadata
            paramters.

        Returns
        -------
        dict
            A dict of parameter names to dataframe objects that is loaded from
            the corresponding metadata file.

            An empty dict if there is no metadata.
        '''
        if metadata_fps == {}:
            return {}

        root_uuid = get_root_uuid(zf)
        pfx = pathlib.Path(root_uuid) / 'provenance'
        if root_uuid == self._uuid:
            pfx = pfx / 'action'
        else:
            pfx = pfx / 'artifacts' / self._uuid / 'action'

        all_md = dict()
        for param_name in metadata_fps:
            filepath = str(pfx / metadata_fps[param_name])
            with zf.open(filepath) as fh:
                df = pd.read_csv(BytesIO(fh.read()), sep='\t')
                all_md[param_name] = df

        return all_md

    def __repr__(self) -> str:
        return repr(self._result_md)

    __str__ = __repr__

    def __hash__(self) -> int:
        return hash(self._uuid)

    def __eq__(self, other) -> bool:
        return (
            self.__class__ == other.__class__ and self._uuid == other._uuid
        )


class _Action:
    '''Provenance data from action.yaml for a single QIIME2 Result.'''

    @property
    def action_id(self) -> str:
        '''The UUID of the Action itself.'''
        return self._execution_details['uuid']

    @property
    def action_type(self) -> str:
        '''
        The type of Action represented e.g. Method, Pipeline, et al.
        '''
        return self._action_details['type']

    @property
    def runtime(self) -> timedelta:
        '''The elapsed run time of the Action, as a datetime object.'''
        end = self._execution_details['runtime']['end']
        start = self._execution_details['runtime']['start']
        return end - start

    @property
    def runtime_str(self) -> str:
        ''' The elapsed run time of the Action in seconds and microseconds.'''
        return self._execution_details['runtime']['duration']

    @property
    def action_name(self) -> str:
        '''
        The name of the action itself. Imports return 'import'.
        '''
        if self.action_type == 'import':
            return 'import'
        return self._action_details.get('action')

    @property
    def plugin(self) -> str:
        '''
        The plugin which executed this Action. Returns 'framework' if this is
        an import.
        '''
        if self.action_type == 'import':
            return 'framework'

        plugin = self._action_details.get('plugin')
        return plugin.replace('-', '_')

    @property
    def inputs(self) -> dict:
        '''
        Creates a dict of artifact inputs to this action.

        Returns
        -------
        dict
            A mapping of input name to the data type passed for that input
            (either uuid, list of uuid, or dict), see below for details.

        Notes
        -----
        One of three structures may be encountered when parsing this section of
        action.yaml, described below:

        case 1:

            inputs:
            - some_input_name: some_uuid
            - some_other_input_name: some_other_uuid
            (...)

        case 2:

            inputs:
            - some_input_name:
                - some_uuid
                - some_other_uuid
            (...)

        case 3 (result collection):

            inputs:
            - result_collection_name:
                - some_key: some_uuid
                - some_other_key: some_other_uuid
            (...)

            and thus is a different structure entirely.
        '''
        inputs = self._action_details.get('inputs')
        results = {}
        if inputs is not None:
            for input_ in inputs:
                nest_lvl_1 = next(iter(input_.values()))
                if type(nest_lvl_1) is list and type(nest_lvl_1[0]) is dict:
                    # result collection
                    rc = {}
                    for member in nest_lvl_1:
                        rc.update(member)

                    input_name = next(iter(input_))
                    results.update({input_name: rc})
                else:
                    # not result collection
                    results.update(input_)

        return results

    @property
    def input_result_collections(self):
        '''
        Collects all result collections passed as inputs (if any). Used for
        constructing the result collection namespace.

        Returns
        -------
        list of str
            A list of the names of the result collections passed as input.
            The names are as registered in the method registration.
        '''
        result_collection_names = []
        for key, value in self.inputs:
            if type(value) is dict:
                result_collection_names.append(key)

        return result_collection_names

    @property
    def parameters(self) -> dict:
        '''Returns a dict of parameters passed to this action.'''
        params = self._action_details.get('parameters')
        results = {}
        if params is not None:
            for item in params:
                results.update(item.items())
        return results

    @property
    def output_name(self) -> Optional[str]:
        '''
        Gets the output name of the node.

        Returns
        -------
        str or None
            The name of the output as parsed from action.yaml, or None if there
            is no output-name section.
        '''
        output_name = self._action_details.get('output-name')

        if type(output_name) is list:
            output_name = output_name[0]

        return output_name

    @property
    def result_collection_key(self) -> Optional[str]:
        '''
        Gets the result collection key if the artifact is part of a result
        collection.

        Returns
        -------
        str
            The result collection key if the artifact was output as part of
            a result collection, none otherwise.

        Notes
        -----
        We know if the artifact comes from a ResultCollection because
        outputs from a ResultCollection look like:

        output-name:
        - output
        - key
        - position/total positions
        '''
        output_name = self._action_details.get('output-name')

        if type(output_name) is not list:
            return None

        return output_name[1]

    @property
    def format(self) -> Optional[str]:
        '''Returns this action's format field if any.'''
        return self._action_details.get('format')

    @property
    def transformers(self) -> Optional[Dict]:
        '''Returns this action's transformers dictionary if any.'''
        return self._action_dict.get('transformers')

    def __init__(self, zf: ZipFile, fp: str):
        with tempfile.TemporaryDirectory() as tempdir:
            zf.extractall(tempdir)
            action_fp = os.path.join(tempdir, fp)
            with open(action_fp) as fh:
                self._action_dict = yaml.safe_load(fh)

        self._action_details = self._action_dict['action']
        self._execution_details = self._action_dict['execution']

    def __repr__(self):
        return (
            f'_Action(action_id={self.action_id}, type={self.action_type},'
            f' plugin={self.plugin}, action={self.action_name})'
        )


class _Citations:
    '''
    Citations for a single QIIME2 Result, as a dict of citation dicts keyed
    on the citation's bibtex ID.
    '''

    def __init__(self, zf: ZipFile, fp: str):
        bib_db = bp.loads(zf.read(fp))
        self.citations = bib_db.get_entry_dict()

    def __repr__(self):
        keys = list(self.citations.keys())
        return f'Citations({keys})'


class _ResultMetadata:
    '''Basic metadata about a single QIIME2 Result from metadata.yaml.'''

    def __init__(self, zf: ZipFile, md_fp: str):
        _md_dict = yaml.safe_load(zf.read(md_fp))
        self.uuid = _md_dict['uuid']
        self.type = _md_dict['type']
        self.format = _md_dict['format']

    def __repr__(self):
        return (
            f'UUID:\t\t{self.uuid}\n'
            f'Type:\t\t{self.type}\n'
            f'Data Format:\t{self.format}'
        )


class Parser(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def parse_prov(self, cfg: Config, data: Any) -> ParserResults:
        '''
        Parse provenance to return a ParserResults.
        '''


class ArchiveParser(Parser):
    '''
    Parser for Result archives.
    '''
    def parse_prov(self, cfg: Config, result: Result) -> ParserResults:
        '''
        Parses an Result's provenance into a directed acyclic graph.

        For each Result in provenance, gathers all corresponding
        provenance-relevant files and constructs a ProvNode. Once all
        ProvNodes are constructed, creates the provenance graph.

        Parameters
        ----------
        cfg : Config
            A dataclass that stores four boolean flags: whether to perform
            checksum validation, whether to parse study metadata, whether to
            recursively parse nested directories, and whether to enable verbose
            mode.
        result : Result
            A QIIME 2 Result to parse provenance from.

        Returns
        -------
        ParserResults
            A dataclass that stores the parsed artifact uuids, the parsed
            networkx graph, the provenance-is-valid flag, and the
            checksum diff.
        '''
        # Keep this around as a skeleton so we can get the ValidationCode
        if cfg.perform_checksum_validation:
            provenance_is_valid, checksum_diff = \
                validate_checksums(result)
        else:
            provenance_is_valid = ValidationCode.VALIDATION_OPTOUT
            checksum_diff = None

        # We don't actually have a straightforward way to parse the version
        # file other than this lol
        archive_version, _ = parse_version()

        if archive_version == '0' or archive_version == '1':
            # No provenance
            #
            # Although action.yaml was introduced for this archive version, we
            # are pretending that it was introduced in V2 because of
            # difficulties untangling provenance without output names. V1
            # archives are treated as having no provenance, like V0 archive
            graph= self._parse_pre_prov(result)
        else:
            # Is archiver version >=2
            graph = self._parse_prov(result)

        return ParserResults(
            {result.uuid},
            graph,
            provenance_is_valid,
            checksum_diff
        )


    def _parse_pre_prov(self, result):
        '''
        Parses an artifact's provenance into a directed acyclic graph.

        In the case of v0 archives, the only provenance information is that
        which is attached to the artifact itself; information about ancestor
        nodes does not exist. The parsed dag contains only a single node.

        In the case of v1 archives, ancestor nodes do exist in the
        archive. However, because the corresponding action.yaml does not track
        output names, when two outputs share the same semantic type, it is not
        possible to untangle provenance. Instead of wrangling with this and
        in consideration of the expected rarity of v1 archives, it was decided
        to treat v1 archives as v0 archives.

        Parameters
        ----------
        cfg : Config
            A dataclass that stores four boolean flags: whether to perform
            checksum validation, whether to parse study metadata, whether to
            recursively parse nested directories, and whether to enable verbose
            mode.
        archive : str
            A path to the artifact to be parsed.

        Returns
        -------
        ParserResults
            A dataclass that stores the parsed artifact uuids, the parsed
            networkx graph, the provenance-is-valid flag, and the
            checksum diff.
        '''
        warnings.warn(
            f'Artifact {result.uuid} was created prior to provenance '
            'tracking. Provenance data will be incomplete.',
            UserWarning
        )

        nodes = {result.uuid: ProvNode(cfg, zf, node_fps)}
        graph = self._digraph_from_archive_contents(nodes)

        return graph

    def _parse_prov(self, result):
        '''
        Parses an artifact's provenance into a directed acyclic graph.

        For each artifact in provenance, gathers all corresponding
        provenance-relevant files and constructs a ProvNode. Once all
        ProvNodes are constructed, creates the provenance graph.

        Parameters
        ----------
        cfg : Config
            A dataclass that stores four boolean flags: whether to perform
            checksum validation, whether to parse study metadata, whether to
            recursively parse nested directories, and whether to enable verbose
            mode.
        archive_data : str
            A path to the artifact to be parsed.

        Returns
        -------
        ParserResults
            A dataclass that stores the parsed artifact uuids, the parsed
            networkx graph, the provenance-is-valid flag, and the
            checksum diff.
        '''
        with ZipFile(archive) as zf:
            if cfg.perform_checksum_validation:
                provenance_is_valid, checksum_diff = \
                    self._validate_checksums(zf)
            else:
                provenance_is_valid = ValidationCode.VALIDATION_OPTOUT
                checksum_diff = None

            prov_fps = self._get_provenance_fps(zf)
            root_uuid = get_root_uuid(zf)

            # make a provnode for each UUID
            archive_contents = {}

            for fp in prov_fps:
                exp_node_fps = []
                if 'artifacts' not in fp.parts:
                    node_uuid = root_uuid
                    prefix = pathlib.Path(node_uuid) / 'provenance'
                    root_only_expected_fps = []
                    for exp_filename in self.expected_files_root_only:
                        root_only_expected_fps.append(
                            pathlib.Path(node_uuid) / exp_filename
                        )
                    exp_node_fps += root_only_expected_fps
                else:
                    node_uuid = get_nonroot_uuid(fp)
                    # /root-uuid/provenance/artifacts/node-uuid
                    prefix = pathlib.Path(*fp.parts[0:4])

                if node_uuid in archive_contents:
                    continue

                # different artifact versions have different expected files
                if 'artifacts' in fp.parts:
                    #      0         1          2        3
                    # /root-uuid/provenance/artifacts/node-uuid
                    nested_path = pathlib.Path(*fp.parts[1:4])
                    archive_version, _ = parse_version(zf, nested_path)
                    parser = FORMAT_REGISTRY[archive_version]
                else:
                    parser = self.__class__

                for expected_file in parser.expected_files_all_nodes:
                    exp_node_fps.append(prefix / expected_file)

                self._assert_expected_files_present(
                    zf, exp_node_fps, prov_fps
                )

                # we have confirmed that all expected fps for this node exist
                node_fps = exp_node_fps

                archive_contents[node_uuid] = ProvNode(cfg, zf, node_fps)

        graph = self._digraph_from_archive_contents(archive_contents)

        return graph

    def _digraph_from_archive_contents(
        self, archive_contents: Dict[str, 'ProvNode']
    ) -> nx.DiGraph:
        '''
        Builds a networkx.DiGraph from a {UUID: ProvNode} dictionary.

        1. Create an empty nx.digraph.
        2. Gather nodes and their required attributes and add them to the
           DiGraph.
        3. Add edges to graph (including all !no-provenance nodes)
        4. Create guaranteed node attributes for these no-provenance nodes,
           which wouldn't otherwise have them.

        Parameters
        ----------
        archive_contents : dict of {str to ProvNode}
            A dictionary of node uuids to their representative ProvNode
            objects.

        Returns
        -------
        nx.DiGraph
            The directed, acyclic graph representation of the provenance of
            the archive. Edge directionality is from parent to child. Parents
            may have multiple children and children may have multiple parents.
        '''
        dag = nx.DiGraph()
        nodes = []
        for node_uuid, node in archive_contents.items():
            node_info = {
                'node_data': node,
                'has_provenance': node.has_provenance
            }
            nodes.append((node_uuid,  node_info))
        dag.add_nodes_from(nodes)

        edges = []
        for node_uuid, attrs in dag.nodes(data=True):
            if parents := attrs['node_data']._parents:
                for parent in parents:
                    parent_uuid, = parent.values()
                    edges.append((parent_uuid, node_uuid))
        dag.add_edges_from(edges)

    # def _get_provenance_fps(self, zf: ZipFile) -> List[pathlib.Path]:
    #     '''
    #     Collect filepaths of all provenance-relevant files in an archive.
    #     Relevant is defined by `self.expected_files_all_nodes` and
    #     `self.expected_files_root_only`.

    #     Parameters
    #     ----------
    #     zf : ZipFile
    #         The zipfile object of the archive.

    #     Returns
    #     -------
    #     list of pathlib.Path
    #         Filepaths relative to root of zipfile for each file of interest.
    #     '''
    #     fps = []
    #     for fp in zf.namelist():
    #         for expected_filename in self.expected_files_all_nodes:
    #             if 'provenance' in fp and expected_filename in fp:
    #                 fps.append(pathlib.Path(fp))

    #     root_uuid = get_root_uuid(zf)
    #     for expected_filename in self.expected_files_root_only:
    #         fps.append(pathlib.Path(root_uuid) / expected_filename)

    #     return fps

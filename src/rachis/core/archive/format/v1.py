# ----------------------------------------------------------------------------
# Copyright (c) 2016-2026, QIIME 2 development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file LICENSE, distributed with this software.
# ----------------------------------------------------------------------------

from pathlib import Path

import yaml

import rachis.core.archive.format.v0 as v0


class ActionYamlLoader(yaml.SafeLoader):
    pass


def metadata_path_skip_constructor(loader, node):
    return loader.construct_scalar(node)


ActionYamlLoader.add_constructor('!metadata', metadata_path_skip_constructor)
class ArchiveFormat(v0.ArchiveFormat):
    PROVENANCE_DIR = 'provenance'

    @classmethod
    def write(cls, archive_record, type, format,
              data_initializer, provenance_capture):
        # contents of data dir written first
        super().write(archive_record, type, format,
                      data_initializer, provenance_capture)

        root = archive_record.root

        # now we write the contents of provenance
        prov_dir = root / cls.PROVENANCE_DIR
        prov_dir.mkdir()

        provenance_capture.finalize(
            prov_dir, [root / cls.METADATA_FILE, archive_record.version_fp])

    def __init__(self, archive_record, *args, replay=False):
        super().__init__(archive_record, *args, replay=replay)

        self.provenance_dir = archive_record.root / self.PROVENANCE_DIR

    @classmethod
    def load_action_yaml(cls, archive):
        action_yaml_path = Path(cls.PROVENANCE_DIR) / 'action' / 'action.yaml'
        with archive.open(action_yaml_path) as fh:
            return yaml.load(fh, Loader=ActionYamlLoader)

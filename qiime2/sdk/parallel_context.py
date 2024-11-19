# ----------------------------------------------------------------------------
# Copyright (c) 2016-2023, QIIME 2 development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file LICENSE, distributed with this software.
# ----------------------------------------------------------------------------

from qiime2.sdk import Context
from qiime2.sdk.parallel_config import PARALLEL_CONFIG


class ParallelContext(Context):
    def __init__(self, parent=None):
        super(ParallelContext, self).__init__(parent=parent)

        if parent is not None:
            self.action_executor_mapping = parent.action_executor_mapping
            self.executor_name_type_mapping = parent.executor_name_type_mapping
        else:
            self.action_executor_mapping = \
                PARALLEL_CONFIG.action_executor_mapping
            self.executor_name_type_mapping = \
                None if PARALLEL_CONFIG.parallel_config is None \
                else {v.label: v.__class__.__name__
                      for v in PARALLEL_CONFIG.parallel_config.executors}

    def _bind(self, action_obj, args, kwargs):
        # We need to bind this action with a child context to indicate that it
        # is not the root pipeline. This is particularly important to parallel
        # pipelines because the root pipeline needs to wait for its returns
        # to resolve while the children do not.
        return action_obj._bind_parsl(
            ParallelContext(parent=self), *args, **kwargs)

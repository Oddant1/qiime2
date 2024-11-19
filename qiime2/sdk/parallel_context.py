# ----------------------------------------------------------------------------
# Copyright (c) 2016-2023, QIIME 2 development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file LICENSE, distributed with this software.
# ----------------------------------------------------------------------------

from qiime2.sdk import Context
from qiime2.sdk.proxy import Proxy
from qiime2.sdk.parallel_config import PARALLEL_CONFIG


class ParallelContext(Context):
    def __init__(self, action_obj, parent=None):
        super(ParallelContext, self).__init__(action_obj, parent=parent)

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

    def deferred_action(self, *args, **kwargs):
        # The function is the first arg, we ditch that
        args = args[1:]

        # If we have a named_pool, we need to check for cached results that
        # we can reuse.
        #
        # We can short circuit our index checking if any of our arguments
        # are proxies because if we got a proxy as an argument, we know it
        # is a new thing we are computing from a prior step in the pipeline
        # and thus will not be cached.
        if self.cache.named_pool is not None and \
                not self._contains_proxies(*args, **kwargs) and \
                (cached_results := self._check_cache(args, kwargs)):
            return cached_results

        # If we didn't have cached results to reuse, we need to execute
        # the action.
        return self._dispatch(args, kwargs)

    def _contains_proxies(self, *args, **kwargs):
        """Returns True if any of the args or kwargs are proxies
        """
        return any(isinstance(arg, Proxy) for arg in args) \
            or any(isinstance(value, Proxy) for
                   value in kwargs.values())

    def _dispatch(self, args, kwargs):
        # We need to bind this action with a child context to indicate that it
        # is not the root pipeline. This is particularly important to parallel
        # pipelines because the root pipeline needs to wait for its returns
        # to resolve while the children do not.
        return self.action_obj._bind_parsl(self, *args, **kwargs)

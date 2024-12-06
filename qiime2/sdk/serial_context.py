# ----------------------------------------------------------------------------
# Copyright (c) 2016-2023, QIIME 2 development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file LICENSE, distributed with this software.
# ----------------------------------------------------------------------------

from qiime2.sdk.context import Context


class SerialContext(Context):
    def deferred_action(self, *args, **kwargs):
        # The function is the first arg, we ditch that
        args = args[1:]

        # If we have a named_pool, we need to check for cached results that
        # we can reuse.
        if self.cache.named_pool is not None and \
                (cached_results := self._check_cache(args, kwargs)):
            return cached_results

        # If we didn't have cached results to reuse, we need to execute
        # the action.
        return self.dispatch(args, kwargs)

    def dispatch(self, args, kwargs):
        return self.action_obj._bind(lambda: self)(*args, **kwargs)

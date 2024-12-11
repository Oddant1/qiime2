# ----------------------------------------------------------------------------
# Copyright (c) 2016-2023, QIIME 2 development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file LICENSE, distributed with this software.
# ----------------------------------------------------------------------------

from .context import Context


class SerialContext(Context):
    def _dispatch_(self, args, kwargs):
        exe = self.action_obj._bind(lambda: self)
        results = exe(*args, **kwargs)

        return results

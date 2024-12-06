# ----------------------------------------------------------------------------
# Copyright (c) 2016-2023, QIIME 2 development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file LICENSE, distributed with this software.
# ----------------------------------------------------------------------------

from qiime2.sdk.context import Context


class SerialContext(Context):
    def dispatch(self, args, kwargs):
        return self.action_obj._bind(lambda: self)(*args, **kwargs)

# ----------------------------------------------------------------------------
# Copyright (c) 2016-2025, QIIME 2 development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file LICENSE, distributed with this software.
# ----------------------------------------------------------------------------

import unittest
import tempfile


from rachis.core.testing.format import SingleIntFormat
from rachis.core.testing.util import get_dummy_plugin
from rachis.plugin.testing import TestPluginBase


class TestTesting(TestPluginBase):
    package = 'rachis.sdk.tests'

    def setUp(self):
        self.plugin = get_dummy_plugin()

        # TODO standardize temporary directories created by QIIME 2
        # create a temporary data_dir for sample Visualizations
        self.test_dir = tempfile.TemporaryDirectory(prefix='rachis-test-temp-')

    def tearDown(self):
        self.test_dir.cleanup()

    def test_transformer_in_other_plugin(self):
        _, obs = self.transform_format(SingleIntFormat, str,
                                       filename='singleint.txt')

        self.assertEqual('42', obs)

    def test_examples(self):
        self.execute_examples()


if __name__ == '__main__':
    unittest.main()

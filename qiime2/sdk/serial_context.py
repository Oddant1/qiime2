# ----------------------------------------------------------------------------
# Copyright (c) 2016-2023, QIIME 2 development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file LICENSE, distributed with this software.
# ----------------------------------------------------------------------------

from qiime2.core.util import create_collection_name

from qiime2.sdk.context import Context
from qiime2.sdk.result import ResultCollection, Result


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

    def clean_pipeline_outputs(self, outputs, output_types, provenance):
        outputs = self._coerce_pipeline_outputs(outputs)

        message = "Pipelines must return `Result` objects, not %s"
        for output in outputs:
            if isinstance(output, ResultCollection):
                for elem in output.values():
                    if not isinstance(elem, Result):
                        raise TypeError(message % type(elem))
            elif not isinstance(output, Result):
                raise TypeError(message % type(output))

        results = []

        # If we don't have a Result, we should have a collection, if we
        # have neither, or our types just don't match up, something bad
        # happened
        for output, (name, spec) in zip(outputs, output_types.items()):
            if isinstance(output, Result) and \
                    (output.type <= spec.qiime_type):
                aliased_result = output._alias(name, provenance, self)

                results.append(aliased_result)
            elif spec.qiime_type.name == 'Collection' and \
                    output.collection in spec.qiime_type:
                size = len(output)
                aliased_output = ResultCollection()

                for idx, (key, value) in enumerate(output.items()):
                    collection_name = create_collection_name(
                        name=name, key=key, idx=idx, size=size)
                    aliased_result = \
                        value._alias(collection_name, provenance, self)

                    aliased_output[str(key)] = aliased_result
                results.append(aliased_output)
            else:
                _type = output.type if isinstance(output, Result) \
                    else type(output)
                raise TypeError(
                    "Expected output type %r, received %r" %
                    (spec.qiime_type, _type))

        return tuple(results)

    def _coerce_pipeline_outputs(self, outputs):
        """Ensure all collections are of type ResultCollection
        """
        coerced_outputs = []

        for output in outputs:
            # Handle collection outputs
            if isinstance(output, dict) or \
                    isinstance(output, list):
                output = ResultCollection(output)

            coerced_outputs.append(output)

        return tuple(coerced_outputs)

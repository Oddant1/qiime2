# ----------------------------------------------------------------------------
# Copyright (c) 2016-2026, QIIME 2 development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file LICENSE, distributed with this software.
# ----------------------------------------------------------------------------
import abc


class IContext(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def _dispatch_(self, args, kwargs):
        """Submit an action for execution
        """

    @abc.abstractmethod
    def get_action(self, plugin: str, action: str):
        """Return a function matching the callable API of an action.
        This function is aware of the pipeline context and manages its own
        cleanup as appropriate.
        """

    @abc.abstractmethod
    def _callable_action_(self, *args, **kwargs):
        """The actual executable called when running an action
        """

    @abc.abstractmethod
    def _check_cache(self, args, kwargs):
        """Check if a given Result is in the cache
        """

    @abc.abstractmethod
    def _load_cache(self, invocation):
        """Load cached results
        """

    @abc.abstractmethod
    def make_artifact(self, type, view, view_type=None):
        """Return a new artifact from a given view.

        This artifact is automatically tracked and cleaned by the pipeline
        context.
        """

    @abc.abstractmethod
    def make_report(self, template, collection):
        """Create a report based on a template and a collection of
            visualizations
        """

    # NOTE: We end up with both the artifact and the pipeline alias of artifact
    # in the named cache in the end. We only have the pipeline alias in the
    # process pool
    @abc.abstractmethod
    def add_reference(self, ref):
        """Add a reference to something destructable that will be owned by the
           parent scope. The reason it needs to be tracked is so that on
           failure, a context can still identify what will (no longer) be
           returned.
        """

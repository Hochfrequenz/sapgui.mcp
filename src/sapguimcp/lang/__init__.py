"""Language packs: every SAP-language-dependent text in one place (#1044).

Re-exports the former ``lang.py`` constants from :mod:`sapguimcp.lang._legacy` until the phase-3
migrations remove their last importer.
"""

from sapguimcp.lang import _legacy
from sapguimcp.lang._legacy import *  # noqa: F403  # re-export of the former lang.py constants

__all__: list[str] = []
__all__ += _legacy.__all__

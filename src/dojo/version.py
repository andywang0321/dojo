"""The version that gates debug-log retention.

Bump MAJOR_VERSION whenever a major stage ships (v0.9 → v0.10): the next
real run clears data/logs/ (see dojo/debuglog.py) so the debug log can
never grow unbounded.
"""

MAJOR_VERSION = "0.10"

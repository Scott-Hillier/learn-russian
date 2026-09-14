import os
import tempfile

# Keep tests away from the real practice history: point the app at a throwaway database
# before any app module reads the configuration.
os.environ.setdefault("PROGRESS_DB", os.path.join(tempfile.mkdtemp(prefix="learn-russian-tests-"), "progress.db"))

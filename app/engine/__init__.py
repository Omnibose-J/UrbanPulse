"""UrbanPulse engine.

Runs as `python -m engine <job>`. Every job is a batch run started by a scheduler (locally: Windows Task
Scheduler; in the cloud: Cloud Run Jobs + Cloud Scheduler). `ENGINE_ENV_FILE` selects the env file;
`RAW_DIR` may be a local folder or a `gs://` prefix. Nothing here serves HTTP; the web app only reads
the tables these jobs write (build contract §1, design principle 1).
"""

ROOT_ENV_FILE = ".env"

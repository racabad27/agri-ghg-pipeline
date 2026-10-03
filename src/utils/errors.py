"Custom errors, so a failure message says which part of the pipeline broke."


class PipelineError(Exception):
    "Base class for all pipeline errors."


class ExtractionError(PipelineError):
    "A download failed, or the downloaded file is broken or incomplete."


class DataQualityError(PipelineError):
    "One or more data-quality checks failed."


class LoadError(PipelineError):
    "Loading into PostgreSQL failed."
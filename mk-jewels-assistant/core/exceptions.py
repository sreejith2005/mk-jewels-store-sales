class PipelineError(Exception):
    pass


class STTError(PipelineError):
    pass


class TriageError(PipelineError):
    pass


class AlertError(PipelineError):
    pass


class DatabaseError(PipelineError):
    pass

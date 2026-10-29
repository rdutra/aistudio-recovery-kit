"""Client error types."""


class AceStepError(RuntimeError):
    """Base error raised by the ACE-Step client."""


class ApiError(AceStepError):
    """An HTTP or malformed API response error."""


class GenerationFailed(AceStepError):
    """The server reported a failed generation task."""


class PollTimeout(AceStepError):
    """A task did not finish before the configured polling deadline."""

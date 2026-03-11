"""Project exceptions."""


class PairingError(RuntimeError):
    """Raised when a pairing step can not be completed as requested."""


class ExactSearchUnavailableError(PairingError):
    """Raised when heuristic-free Dutch solving is not yet available."""

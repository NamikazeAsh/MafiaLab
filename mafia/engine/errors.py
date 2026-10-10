class AbortGame(Exception):
    """Raised by a caller's error hook to abandon a game, for example after repeated LLM failures."""


class GameStopped(Exception):
    """Raised inside Game when the caller's should_stop callback asks it to end early."""

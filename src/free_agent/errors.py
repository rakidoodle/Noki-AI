class AgentError(Exception):
    """An actionable agent failure."""


class ConfigurationError(AgentError):
    pass


class AuthenticationError(AgentError):
    pass


class RateLimitError(AgentError):
    pass


class ProviderUnavailableError(AgentError):
    pass


class ModelCapabilityError(AgentError):
    pass


class BudgetExceeded(AgentError):
    pass


class MaxStepsExceeded(AgentError):
    pass

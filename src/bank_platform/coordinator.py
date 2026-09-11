from bank_platform.agents import (
    AccountsAgent,
    AgentRequest,
    AgentResponse,
    AgentType,
    ServiceAgent,
    TransactionAgent,
)

_AGENTS = {
    AgentType.ACCOUNTS: AccountsAgent(),
    AgentType.TRANSACTION: TransactionAgent(),
    AgentType.SERVICE: ServiceAgent(),
}


class Coordinator:
    """Rule-based router: dispatches on the explicit '<agent>.<operation>' intent prefix."""

    def route(self, request: AgentRequest) -> AgentResponse:
        if not request.intent or "." not in request.intent:
            return AgentResponse(
                agent=AgentType.COORDINATOR,
                success=False,
                message="intent must be '<agent>.<operation>', e.g. 'accounts.create'",
                error="invalid_intent",
            )

        agent_name = request.intent.split(".", 1)[0]

        try:
            agent_type = AgentType(agent_name)
        except ValueError:
            return AgentResponse(
                agent=AgentType.COORDINATOR,
                success=False,
                message=f"Unknown agent: {agent_name}",
                error="unknown_agent",
            )

        agent = _AGENTS.get(agent_type)
        if agent is None:
            return AgentResponse(
                agent=AgentType.COORDINATOR,
                success=False,
                message=f"No agent registered for: {agent_name}",
                error="unknown_agent",
            )

        return agent.handle(request)

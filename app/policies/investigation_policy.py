from app.policies.agent_policy import AgentPolicy


def create_investigation_policy() -> AgentPolicy:
    return AgentPolicy(
        allowed_tools={
            "read_file",
            "search_code",
            "git_log",
        }
    )
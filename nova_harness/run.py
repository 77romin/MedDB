"""Competition entry point. No development key, sample scripts, or local .env loading."""
from nova_sdk import run_agent
from nova_agent.runtime import prepare, consult


if __name__ == '__main__':
    run_agent(prepare, consult)

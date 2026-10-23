from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    model: str = 'openai/gpt-6-luna'
    max_turns: int = 45  # leaves five server turns as reserve; not a target
    max_calls: int = 160  # below server's 200-call hard limit
    input_budget: int = 450_000
    output_budget: int = 85_000
    reserve_calls: int = 8
    reserve_input: int = 40_000
    reserve_output: int = 12_000
    time_margin: int = 360
    step_tokens: int = 2048
    record_tokens: int = 4096
    reasoning_effort: str = 'medium'
    planner_reasoning_effort: str = 'medium'  # low remains an explicit development experiment
    closure_audit: bool = False  # experimental; C01 did not improve with it enabled
    decision_review: bool = True  # one bounded review of decision scope before ordinary DONE
    closure_review_limit: int = 2  # only while time and collection turns remain
    meddb: bool = True
    coverage: bool = True
    compact_context: bool = True
    guidelines: bool = False  # optional ablation, not a clinically validated default
    structured_closing: bool = True
    closing_turns: int = 12  # multiple complete sentences, teach-back, one correction
    # Development runs can return an edge-proxy 524 while the accepted request
    # is still being processed.  Keep the same request id and allow enough time
    # for the subsequent REQUEST_PENDING responses to settle.
    retry_delays: tuple = (2, 5, 10, 20, 30)

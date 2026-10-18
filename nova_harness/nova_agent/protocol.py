import time
import uuid
from datetime import datetime, timezone

from nova_sdk import Client, NovaError
from .config import Config
from .telemetry import Trace

SAME_ID = {'API_UNAVAILABLE', 'PROVIDER_UNAVAILABLE', 'REQUEST_PENDING', 'LOCAL_GATEWAY_UNAVAILABLE'}
NEW_ID = {'PROVIDER_RESPONSE_INVALID', 'PATIENT_RESPONSE_INVALID', 'EXAMINER_RESPONSE_INVALID'}


def seconds_left(session, now=None):
    value = session.get('deadline')
    if not value:
        return float('inf')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp() - (time.time() if now is None else now)


class LoggedClient(Client):
    def __init__(self, *args, trace=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.trace = trace or Trace()

    def _request(self, method, path, body=None):
        started = time.monotonic()
        self.trace.emit('http_request', method=method, path=path, body=body)
        try:
            result = super()._request(method, path, body)
        except NovaError as exc:
            self.trace.emit('http_error', path=path, request_id=(body or {}).get('request_id'),
                            code=exc.code, status=exc.status, seconds=time.monotonic()-started)
            raise
        self.trace.emit('http_response', path=path, request_id=(body or {}).get('request_id'),
                        response=result, seconds=time.monotonic()-started)
        return result


class Gateway:
    def __init__(self, client, config=None, trace=None, sleeper=time.sleep):
        self.client = client
        self.config = config or Config()
        self.trace = trace or Trace()
        self.sleep = sleeper
        self.deadline = None
        self.chat_ids = set()
        self.usage_ids = set()
        self.input_tokens = 0
        self.output_tokens = 0

    def remaining(self):
        return seconds_left({'deadline': self.deadline})

    def invoke(self, method, *args, final=False, **kwargs):
        request_id = str(uuid.uuid4())
        for attempt in range(len(self.config.retry_delays)+1):
            if self.deadline and self.remaining() <= 5:
                raise NovaError('LOCAL_DEADLINE')
            is_chat = method == 'chat'
            if is_chat and request_id not in self.chat_ids:
                call_cap = self.config.max_calls if final else self.config.max_calls-self.config.reserve_calls
                input_cap = self.config.input_budget if final else self.config.input_budget-self.config.reserve_input
                output_cap = self.config.output_budget if final else self.config.output_budget-self.config.reserve_output
                if len(self.chat_ids) >= call_cap or self.input_tokens >= input_cap or self.output_tokens + kwargs.get('max_tokens', 0) > output_cap:
                    raise NovaError('LOCAL_MODEL_BUDGET')
                self.chat_ids.add(request_id)
            # Do not let a fresh SDK wait run beyond the session deadline.
            original_timeout = getattr(self.client, 'timeout', None)
            if original_timeout is not None and self.deadline:
                self.client.timeout = min(original_timeout, max(1, self.remaining()-5))
            try:
                result = getattr(self.client, method)(*args, request_id=request_id, **kwargs)
            except NovaError as exc:
                self.trace.emit('operation_error', operation=method, request_id=request_id, attempt=attempt,
                                code=exc.code, status=exc.status)
                if exc.code not in SAME_ID | NEW_ID or attempt >= len(self.config.retry_delays):
                    raise
                delay = self.config.retry_delays[attempt]
                if self.remaining() <= delay+5:
                    raise
                self.trace.emit('retry', operation=method, code=exc.code,
                                request_id=request_id, new_request_id=exc.code in NEW_ID, delay=delay)
                self.sleep(delay)
                if exc.code in NEW_ID:
                    request_id = str(uuid.uuid4())
                continue
            finally:
                if original_timeout is not None:
                    self.client.timeout = original_timeout
            if is_chat and request_id not in self.usage_ids:
                usage = result.get('usage', {})
                self.input_tokens += int(usage.get('prompt_tokens', 0))
                self.output_tokens += int(usage.get('completion_tokens', 0))
                self.usage_ids.add(request_id)
            self.trace.emit('operation_success', operation=method, request_id=request_id,
                            response=result, model_calls=len(self.chat_ids),
                            input_tokens=self.input_tokens, output_tokens=self.output_tokens)
            return result

    def chat(self, messages, final=False):
        return self.invoke('chat', messages, final=final, model=self.config.model,
                           max_tokens=self.config.record_tokens if final else self.config.step_tokens,
                           reasoning_effort=self.config.reasoning_effort if final else self.config.planner_reasoning_effort)

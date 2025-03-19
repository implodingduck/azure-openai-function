import azure.functions as func
import openai
from azurefunctions.extensions.http.fastapi import Request, Response, StreamingResponse
import asyncio
import os
import tiktoken

from azure.monitor.opentelemetry import configure_azure_monitor
from azure.monitor.events.extension import track_event

# Import the tracing api from the `opentelemetry` package.
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

configure_azure_monitor()
trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter_provider().get_meter("openaifunction")
token_counter = meter.create_counter("openaitokens")

# Azure Function App
#app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
app = func.FunctionApp()


@app.function_name(name="HttpTrigger1")
@app.route(route="req")
def main(req: Request, context: func.Context) -> Response:
    operation_id = context.trace_context.Traceparent.split("-")[1]
    w3c_trace_context = { "traceparent": context.trace_context.Traceparent }
    ctx = TraceContextTextMapPropagator().extract(carrier=w3c_trace_context)
    with tracer.start_as_current_span("openai-function", context=ctx):
        user = req.query_params.get("user", "default")
        token_counter.add(1, { "function": os.environ.get("OTEL_SERVICE_NAME"), "operation_id": operation_id, "streaming": "false" })
        track_event("openai-tokens", {"function": os.environ.get("OTEL_SERVICE_NAME"), "total_tokens": 1, "operation_id": operation_id , "streaming": "false"})
        return f"Hello, {user}!"

endpoint = os.environ.get("API_BASE")
api_key = os.environ.get("APIM_KEY", "")

# Azure Open AI
deployment = os.environ.get("ENGINE")
temperature = 0.7

client = openai.AsyncAzureOpenAI(
    azure_endpoint=endpoint,
    api_key=api_key,
    api_version="2023-09-01-preview"
)

async def num_tokens_from_string(string: str, encoding_name: str) -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens

# Get data from Azure Open AI
async def stream_processor(response, operation_id):
    async for chunk in response:
        if len(chunk.choices) > 0:
            delta = chunk.choices[0].delta
            if delta.content: # Get remaining generated response if applicable
                #await asyncio.sleep(0.1)
                total_tokens = await num_tokens_from_string(delta.content, 'cl100k_base')
                token_counter.add(total_tokens, { "function": os.environ.get("OTEL_SERVICE_NAME"), "operation_id": operation_id, "streaming": "true" })
                track_event("openai-tokens", {"function": os.environ.get("OTEL_SERVICE_NAME"), "total_tokens": total_tokens, "operation_id": operation_id , "streaming": "true"})
                yield delta.content
    



async def generate_count():
    """Generate a stream of chronological numbers."""
    async for count in range(100):
        yield f"counting, {count}\n\n"

# HTTP streaming Azure Function
@app.function_name(name="streamcities")
@app.route(route="stream-cities", methods=[func.HttpMethod.GET])
async def stream_openai_text(req: Request, context: func.Context) -> StreamingResponse:
    operation_id = context.trace_context.Traceparent.split("-")[1]
    w3c_trace_context = { "traceparent": context.trace_context.Traceparent }
    ctx = TraceContextTextMapPropagator().extract(carrier=w3c_trace_context)
    with tracer.start_as_current_span("openai-function", context=ctx):
        prompt = "List the 100 most populous cities in the United States."
        
        azure_open_ai_response = await client.chat.completions.create(
            model=deployment,
            temperature=temperature,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
            stream=True
        )

        total_tokens = await num_tokens_from_string(prompt, 'cl100k_base')
        token_counter.add(total_tokens, { "function": os.environ.get("OTEL_SERVICE_NAME"), "operation_id": operation_id, "streaming": "true" })
        track_event("openai-tokens", {"function": os.environ.get("OTEL_SERVICE_NAME"), "total_tokens": total_tokens, "operation_id": operation_id , "streaming": "true"})

        return StreamingResponse(stream_processor(azure_open_ai_response, operation_id), media_type="text/event-stream")
    #return StreamingResponse(generate_count(), media_type="text/event-stream")



@app.function_name(name="cities")
@app.route(route="cities", methods=[func.HttpMethod.GET])
async def stream_openai_text(req: Request, context: func.Context) -> Response:
    operation_id = context.trace_context.Traceparent.split("-")[1]
    w3c_trace_context = { "traceparent": context.trace_context.Traceparent }
    ctx = TraceContextTextMapPropagator().extract(carrier=w3c_trace_context)
    with tracer.start_as_current_span("openai-function", context=ctx):
        prompt = "List the 100 most populous cities in the United States."
        azure_open_ai_response = await client.chat.completions.create(
            model=deployment,
            temperature=temperature,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        total_tokens = azure_open_ai_response.usage.total_tokens
        token_counter.add(total_tokens, { "function": os.environ.get("OTEL_SERVICE_NAME"), "operation_id": operation_id, "streaming": "false" })
        track_event("openai-tokens", {"function": os.environ.get("OTEL_SERVICE_NAME"), "total_tokens": total_tokens, "operation_id": operation_id , "streaming": "false"})

        return Response(azure_open_ai_response.to_json(), media_type="application/json")

@app.function_name(name="listenv")
@app.route(route="listenv", methods=[func.HttpMethod.GET])
async def list_env(req: Request, context: func.Context) -> Response:
    env_vars = os.environ
    return Response(str(env_vars), media_type="text/plain")


import logging
import os
import azure.functions as func
from azure.identity import DefaultAzureCredential
import openai
import json
from opentelemetry.sdk.trace import TracerProvider

from azure.monitor.events.extension import track_event
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
from opentelemetry import metrics
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

configure_azure_monitor(
    connection_string=os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"),
)

trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)

meter = metrics.get_meter_provider().get_meter("openaifunction")
token_counter = meter.create_counter("openaitokens")

# Request credential
default_credential = DefaultAzureCredential()
token = default_credential.get_token("https://cognitiveservices.azure.com/.default")

# Setup parameters
openai.api_type = "azure_ad"
openai.api_key = token.token
openai.api_base = os.environ.get("API_BASE")
openai.api_version = "2023-05-15"
engine = os.environ.get("ENGINE")

#@tracer.start_as_current_span("openai-function")
def main(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')
    logging.info(f"Invocation id: {context.invocation_id}")
    logging.info(f"function name: {context.function_name}")
    logging.info(f"context: {context}")
    logging.info(f"trace context: {context.trace_context}")
    logging.info(f"trace parent: {context.trace_context.Traceparent}")
    logging.info(f"trace state: {context.trace_context.Tracestate}")
    operation_id = context.trace_context.Traceparent.split("-")[1]
    w3c_trace_context = { "traceparent": context.trace_context.Traceparent }
    ctx = TraceContextTextMapPropagator().extract(carrier=w3c_trace_context)
    with tracer.start_as_current_span("openai-function", context=ctx):
        question = req.params.get('question')
        if not question:
            try:
                req_body = req.get_json()
            except ValueError:
                pass
            else:
                question = req_body.get('question')

        user_prompt = "What is blue milk?"
        if question:
            user_prompt = question


        
        response = openai.ChatCompletion.create(
            engine=engine,
            n=1,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
            messages=[
                {"role": "system", "content": 'You are an AI assistant that helps people find information about "Star Wars".\n\nInstructions\n- only answer questions related to Star Wars\n- If an answer is not related to Star Wars, respond with "This is not the AI you are looking for..."'},
                {"role": "user", "content": user_prompt},
            ],
        )

        logging.info(f"{list(req.headers.keys())}")
        for key in req.headers.keys():
            logging.info(f"{key}: {req.headers[key]}")
        logging.info(f"{req.headers}")
        logging.info(response)

        token_counter.add(response["usage"]["total_tokens"], { "function": os.environ.get("OTEL_SERVICE_NAME"), "operation_id": operation_id })
        track_event("openai-tokens", {"function": os.environ.get("OTEL_SERVICE_NAME"), "total_tokens": response["usage"]["total_tokens"], "operation_id": operation_id})
        return func.HttpResponse(response["choices"][0]["message"]["content"])
   
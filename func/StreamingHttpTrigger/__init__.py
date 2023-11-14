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
import tiktoken
import time
from starlette.responses import StreamingResponse
import asyncio

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

async def get_streamingresponse_openai(prompt: str):
    response = openai.ChatCompletion.create(
        engine=engine,
        n=1,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        stream=True,
        messages=[
            {"role": "system", "content": 'You are an AI assistant that helps people find information about "Star Wars".\n\nInstructions\n- only answer questions related to Star Wars\n- If an answer is not related to Star Wars, respond with "This is not the AI you are looking for..."'},
            {"role": "user", "content": prompt},
        ],
    )

    total_content = ""
    for chunk in response:
        logging.info(chunk)
        choice_content = chunk["choices"][0]["delta"].get("content", "")
        logging.info(choice_content)
        total_content += choice_content
        yield choice_content

    encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = len(encoding.encode(total_content))
    token_counter.add(num_tokens, { "function": os.environ.get("OTEL_SERVICE_NAME"), "operation_id": operation_id, "streaming": "true" })
    track_event("openai-tokens", {"function": os.environ.get("OTEL_SERVICE_NAME"), "total_tokens": num_tokens, "operation_id": operation_id , "streaming": "true"})
    logging.info(num_tokens)

async def main(req: func.HttpRequest, context: func.Context):
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


        
        return func.HttpResponse(get_streamingresponse_openai(user_prompt))
        

       


        
   
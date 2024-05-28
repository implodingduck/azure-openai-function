import requests
import os
import argparse

parser = argparse.ArgumentParser(description='Client for the Azure OpenAI Function')

parser.add_argument('--id', type=str,
                    help='a string for the tracking id', default=1)

parser.add_argument('--stream', type=int,
                    help='Should I not stream it? (0 or 1)', default=1)

parser.add_argument('--output', type=int,
                    help='Should I provide output? (0 or 1)', default=1)

args = parser.parse_args()

function_key = os.environ.get("FUNCTION_KEY")
function_name = os.environ.get("FUNCTION_NAME")


#url = f"https://{function_name}.azurewebsites.net/api/HttpTrigger/?code={function_key}&question=&stream={args.stream}&tracking={args.id}"
#url = f"https://{function_name}.azurewebsites.net/openaistreaming/?code={function_key}&question=What is the history of the force?"
url = f"https://{function_name}.azurewebsites.net/stream-cities/?code={function_key}"


if args.output > 0:
    print(f"Trying: {url}")
response = requests.get(
    url,
    headers={"accept": "application/json"},
)

if args.output > 0:
    #print(response)
    #print(response.headers)
    #print(response.content)
    for chunk in response.iter_content(chunk_size=1024):
        if chunk:
            print(str(chunk, encoding="utf-8"), end="")

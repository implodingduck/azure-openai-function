import requests

function_key = ""
function_name = ""

url = f"https://{function_name}.azurewebsites.net/api/streaminghttptrigger/?code={function_key}&question=What is the history of the force?"

response = requests.get(
    url,
    stream=1,
    headers={"accept": "application/json"},
)

print(response)

for chunk in response.iter_content(chunk_size=1024):
    if chunk:
        print(str(chunk, encoding="utf-8"), end="")
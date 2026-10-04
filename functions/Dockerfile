# Azure Functions app (Python v2). Build context = repository root so the shared contracts/ can be copied in.
FROM mcr.microsoft.com/azure-functions/python:4-python3.12
ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    CONTRACTS_DIR=/home/site/wwwroot/contracts
COPY functions/requirements.txt /
RUN pip install --no-cache-dir -r /requirements.txt
COPY functions/host.json functions/function_app.py /home/site/wwwroot/
COPY functions/shared /home/site/wwwroot/shared
COPY contracts /home/site/wwwroot/contracts

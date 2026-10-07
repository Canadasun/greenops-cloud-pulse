# Message router – local stand-in for IoT Hub message routing (Role 2 – Marcelbriaud Wafotchoupe)
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY router.py replay.py ./
RUN useradd --create-home router
RUN mkdir -p /data && chown router:router /data
USER router
CMD ["python", "router.py"]

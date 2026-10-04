# Truck simulator (Role 1 – Ying Song). Python 3.12 as stated in the Part 1 technology stack.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY greenops_sim ./greenops_sim
RUN useradd --create-home sim
USER sim
EXPOSE 8090
CMD ["python", "-m", "greenops_sim.runner"]

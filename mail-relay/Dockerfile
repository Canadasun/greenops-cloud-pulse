# Mail relay – local stand-in for the Logic App email step (Role 3 – Shi Wang)
FROM python:3.12-slim
WORKDIR /app
COPY relay.py .
RUN useradd --create-home relay
USER relay
EXPOSE 8070
CMD ["python", "relay.py"]

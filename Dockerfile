FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY main.py .
COPY api/ ./api/
COPY search/ ./search/
COPY symbolic/ ./symbolic/
COPY reasoning/ ./reasoning/
RUN useradd --uid 10001 --create-home rhns
USER 10001
EXPOSE 8090
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]

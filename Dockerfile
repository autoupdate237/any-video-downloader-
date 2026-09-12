FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=5000 HOST=0.0.0.0
EXPOSE 5000

CMD ["gunicorn", "-w", "2", "-k", "gthread", "--threads", "8", "-t", "600", "-b", "0.0.0.0:5000", "app:app"]

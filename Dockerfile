FROM python:3.7

EXPOSE 8080

COPY requirements.txt .
COPY spackbot /app/spackbot

RUN pip3 install -r requirements.txt

ENV PYTHONPATH "${PYTHONPATH}:/app"
CMD ["python3", "-m", "spackbot"]

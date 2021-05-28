FROM python:3.9

COPY requirements.txt .
COPY spackbot /app/spackbot

RUN pip3 install -r requirements.txt

ENV PYTHONPATH "${PYTHONPATH}:/app"
CMD ["python3", "-m", "spackbot"]

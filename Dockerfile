FROM python:3.7

EXPOSE 8080

# dependencies first since they're the slowest
COPY requirements.txt .

RUN pip3 install -r requirements.txt

# copy app in last so that everything above can be cached
COPY spackbot /app/spackbot
COPY entrypoint.sh /entrypoint.sh

ENV PYTHONPATH "${PYTHONPATH}:/app"
CMD ["/bin/bash", "/entrypoint.sh"]

FROM node:16-buster-slim

EXPOSE 8080

WORKDIR /code
COPY smee/entrypoint.sh /code/entrypoint.sh

RUN npm install --global smee-client
ENTRYPOINT ["/bin/bash"]
CMD ["/code/entrypoint.sh"]

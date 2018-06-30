FROM alpine:3.7

RUN apk add --update \
    python \
    python-dev \
    py-pip \
    build-base \
  && pip install virtualenv Flask oauthlib oauth-middleware \
  && rm -rf /var/cache/apk/*

WORKDIR /app

COPY  src /app

CMD [ "python", "delete.py" ]

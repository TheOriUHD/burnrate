FROM python:3.13-alpine
LABEL org.opencontainers.image.title="Burnrate" \
      org.opencontainers.image.description="Self-hosted usage and limit tracker for AI subscriptions and API accounts" \
      org.opencontainers.image.licenses="MIT"
RUN adduser -D -H -u 10001 burnrate && mkdir -p /data && chown burnrate /data && apk add --no-cache tzdata
COPY burnrate /app/burnrate
WORKDIR /app
USER burnrate
ENV BURNRATE_DATA=/data BURNRATE_PORT=8090 PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8090
HEALTHCHECK --interval=60s --timeout=5s CMD wget -qO- http://127.0.0.1:8090/healthz >/dev/null || exit 1
CMD ["python", "-m", "burnrate"]

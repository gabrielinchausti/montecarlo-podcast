FROM alpine:3.22
RUN apk add --no-cache ffmpeg python3 tzdata
COPY grabar.py /app/grabar.py
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python3", "/app/grabar.py"]

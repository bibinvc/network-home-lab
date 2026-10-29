ARG BASE_IMAGE=python:3.12-slim-bookworm
FROM ${BASE_IMAGE}
ARG RELEASE=1.0.0
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 APP_RELEASE=${RELEASE}
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/app.py .
RUN chmod 0444 /app/app.py
USER 10001:10001
EXPOSE 8080
CMD ["python", "app.py"]

FROM mcr.microsoft.com/playwright/python:v1.54.0-noble

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
ARG REGRESSIONFORGE_SOURCE_REV=2
RUN test -n "$REGRESSIONFORGE_SOURCE_REV"
COPY regressionforge ./regressionforge
RUN mkdir -p /data /artifacts

ENV REGRESSIONFORGE_DATA=/data
ENV REGRESSIONFORGE_ARTIFACTS=/artifacts
EXPOSE 8000
CMD ["uvicorn", "regressionforge.main:app", "--host", "0.0.0.0", "--port", "8000"]

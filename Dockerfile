FROM python:latest
MAINTAINER Felix Engelmann "fe-docker@nlogn.org"
COPY lidl.py /app
WORKDIR /app
RUN pip install -r requirements.txt
ENTRYPOINT ["python"]
CMD ["lidl.py"]

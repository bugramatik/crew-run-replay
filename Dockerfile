# Baseimage
FROM python:3.12.10-slim-bookworm

# Update Packages
RUN apt update
RUN apt upgrade -y
RUN pip install --upgrade pip
# install git
RUN apt-get install build-essential -y


RUN mkdir /crew-run-replay

# Install requirements
COPY ./requirements.txt /crew-run-replay/requirements.txt
WORKDIR /crew-run-replay
RUN pip install -r requirements.txt

# Copy crew-run-replay
COPY ./ /crew-run-replay/

# Run app
CMD ["streamlit","run","./app/app.py","--server.headless","true"]
EXPOSE 8501

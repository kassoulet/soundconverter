# Run Test in Docker
#
# This is not straightforward as we launch a graphical application

FROM ubuntu:latest

# Set environment variables to prevent interactive prompts during apt-get
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install packages
RUN apt-get update \
    && apt-get install -y \
    python3-pip \
    python3-dev \
    python3-distutils-extra \
    build-essential \
    libgstreamer1.0-0 \
    libgstreamer1.0-dev \
    libgtk-3-0 \
    libgtk-3-dev \
    gir1.2-gtk-3.0 \
    gir1.2-gst* \
    python3-gi \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-fdkaac \
    gstreamer1.0-libav \
    # xorg \
    # x11vnc \
    # gnome \
    # gnome-terminal \
    # x11-apps \
    xvfb \
    dbus-x11 \
    x11-utils \
    procps \
    libgtk-3-0 \
    libglib2.0-0

# Set the working directory to the application's source code
WORKDIR /app

COPY . /app

# Install Python dependencies
RUN python3 setup.py install --prefix=/usr

# RUN pip install setuptools wheel \
#     && pip install . 

# Copy the script to run tests with Xvfb and make it executable
COPY tests/run_tests_docker.sh /usr/local/bin/run_tests_docker.sh
RUN chmod +x /usr/local/bin/run_tests_docker.sh

CMD ["run_tests_docker.sh"]

# Dockerfile must start with a FROM instruction, base image!
FROM nvidia/cuda:9.0-cudnn7-runtime

# Install Python3 and pip 
RUN apt-get update && apt-get install -y \
        python3 \
        python3-pip \
        && \
    pip3 install --upgrade pip && \
    apt-get clean && \
    apt-get autoremove && \
    rm -rf /var/lib/apt/lists/*

# Install everything needed for training
RUN pip --no-cache-dir install \
    jupyter \
    matplotlib==3.0.0 \
    # the 1.8.0 pip version is linked against Cuda 9.0
    tensorflow-gpu==1.8.0 \
    Keras==2.2.2 \
    scikit-learn==0.19.2 \ 
    pandas==0.23.4 \
    tables==3.4.4 \
    pillow==5.2.0

WORKDIR "/root"

COPY keras_util_v2 training_notebooks/keras_util_v2
COPY cheetah_inception_resnet_train.ipynb training_notebooks/
COPY imagenet_classes training_notebooks/

# For the Jupyter notebook
EXPOSE 8888

CMD ["/bin/bash"]


    


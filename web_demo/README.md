# Web demo/debugging tool for the Cheetah classifier

The `cheetah_tf_serving/` directory contains the model export and the exported model,
as well as a sample command line client to test it with. The model in the `models`
subdirectory must be loaded with Tensorflow Serving. If you have a Tensorflow Serving Docker
image you could run the following command from the `cheetah_tf_serving` directory:

    docker run --rm -p 8500:8500 --entrypoint=tensorflow_model_server \
    --mount type=bind,source=$(pwd)/models/cheetah_inception,target=/models/cheetah_inception \
    -it tensorflow/serving --port=8500 --model_name=cheetah_inception --model_base_path=/models/cheetah_inception
    
The `web_app` directory contains a minimal Flask app that serves a minimal HTML front-end and uses 
the Tensorflow Serving backend to classify camera trap images uploaded by the user. The minimal
front-end looks like this:

![Screenshot of web interface](test.png)
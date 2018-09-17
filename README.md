# IZW_Detector
Automated Cheetah detector for the Reconyx camera traps

# Installation
The repo is used as a source for packing the tool into a PyInstaller executable, but it can also be executed directly by calling `python cheetah_classifier_gui.py` in the `reconyx_classifier` directory. 

To set up the right dependencies and environments, it might be easiest to use the supplied `environment.yml`, which can be used to initialize a Conda environment:

```
conda env create -f environment.yml
conda activate cheetah_detector_env

bash setup.sh
```

The `setup.sh` command (should be run in the activate Conda environment) just generates some GUI code and downloads a default classification model to use.

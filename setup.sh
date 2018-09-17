#!/bin/sh
pyuic5 -o reconyx_classifier/design.py gui/design.ui
pyrcc5 -o reconyx_classifier/images_rc.py gui/images.qrc

mkdir reconyx_classifier/model 
wget 'https://www.dropbox.com/s/z2vae7nn5jij1b7/cheetah_model.hdf5?dl=0' -O reconyx_classifier/model/cheetah_model.hdf5

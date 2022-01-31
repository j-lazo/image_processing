import os
from absl import app, flags, logging
from absl.flags import FLAGS
from general_functions import data_management as dam
from matplotlib import pyplot as plt
import cv2
from classification import call_models as img_class

DATASETS = ['tissue_classification']


def run_experiment(_argv):
    name_model = 'fc_3layers+densenet_train_backbone_lr_1e-05_bs_16_30_01_2022_17_05'
    directory_model = ''.join([os.getcwd(), 'datasets/tissue_classification/results/', name_model,
                               '/model_', name_model])
    model, _ = img_class.load_model(directory_model)
    model.summary()
    backbone_model = model.get_layer(index=0).name
    print(f'Backbone identified: {backbone_model}')

if __name__ == '__main__':

    flags.DEFINE_string('name_model', 'fc_3layers', 'name of the model')
    flags.DEFINE_string('mode', 'train_backbone', 'train, predict, train_backbone')
    flags.DEFINE_string('backbone', 'resnet50', 'backbone network')
    flags.DEFINE_integer('batch_size', 8, 'batch size')
    flags.DEFINE_float('learning_rate', 0.001, 'learning rate')
    flags.DEFINE_integer('epochs', 7, 'number of epochs')
    flags.DEFINE_integer('trainable_layers', -7, 'Trainable layers in case backbone is trained')
    flags.DEFINE_bool('analyze_data', True, 'select if analyze data or not')
    flags.DEFINE_integer('fine_tune_epochs', 3, 'epochs to fine tune the model')

    flags.DEFINE_string('dataset_dir', os.getcwd() + 'data/', 'path to dataset')
    flags.DEFINE_string('val_dataset', '', 'path to validation dataset')
    flags.DEFINE_string('test_dataset', '', 'path to test dataset')
    flags.DEFINE_string('results_dir', os.getcwd() + 'results/', 'path to dataset')
    flags.DEFINE_string('weights', '', 'path to weights file')
    flags.DEFINE_string('directory_model', '', 'indicate the path to the directory')
    flags.DEFINE_float('validation_split', 0.2, 'iif not validation dir but needed')
    flags.DEFINE_string('file_to_predic', '', 'Directory or file where to perform predictions if predict mode selected')

    try:
        app.run(run_experiment)
    except SystemExit:
        pass
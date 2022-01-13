
import numpy as np
import tensorflow as tf
import os
import sys
import cv2
import pandas as pd
from matplotlib import pyplot as plt
import datetime
import shutil

from absl import app, flags, logging
from absl.flags import FLAGS

from tensorflow.keras.models import Sequential
from tensorflow.keras.models import Model
from tensorflow.keras.optimizers import SGD, Adam, RMSprop, Nadam
from tensorflow.keras import applications
from keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau, CSVLogger, TensorBoard

from sklearn.metrics import roc_curve, auc

sys.path.append(os.getcwd() + '/scripts/general_functions/')

import data_management as dam
import data_analysis as daa
import classification_models as cms



flags.DEFINE_string('name_model', '', 'name of the model')
flags.DEFINE_string('mode', '', 'train or predict')
flags.DEFINE_string('backbone', '', 'backbone network')
flags.DEFINE_string('dataset_dir', os.getcwd() + 'data/', 'path to dataset')
flags.DEFINE_string('val_dataset', '', 'path to validation dataset')
flags.DEFINE_string('test_dataset', '', 'path to test dataset')
flags.DEFINE_string('results_dir', os.getcwd() + 'results/', 'path to dataset')
flags.DEFINE_integer('epochs', 1, 'number of epochs')
flags.DEFINE_integer('batch_size', 4, 'batch size')
flags.DEFINE_float('learning_rate', 1e-3, 'learning rate')
flags.DEFINE_string('weights', './checkpoints/yolov3.tf', 'path to weights file')
flags.DEFINE_string('analyze_data', False,  'select if analyze data or not')

"""
flags.DEFINE_string('weights', './checkpoints/yolov3.tf', 'path to weights file')
flags.DEFINE_enum('mode', 'fit', ['fit', 'eager_fit', 'eager_tf'],
                  'fit: model.fit, '
                  'eager_fit: model.fit(run_eagerly=True), '
                  'eager_tf: custom GradientTape')
flags.DEFINE_enum('transfer', 'none',
                  ['none', 'darknet', 'no_output', 'frozen', 'fine_tune'],
                  'none: Training from scratch, '
                  'darknet: Transfer darknet, '
                  'no_output: Transfer all but output, '
                  'frozen: Transfer and freeze all, '
                  'fine_tune: Transfer all and freeze darknet only')
flags.DEFINE_integer('size', '', 'image size')
flags.DEFINE_integer('epochs', 2, 'number of epochs')
flags.DEFINE_integer('batch_size', 8, 'batch size')
flags.DEFINE_float('learning_rate', 1e-3, 'learning rate')
flags.DEFINE_integer('num_classes', 80, 'number of classes in the model')
flags.DEFINE_integer('weights_num_classes', None, 'specify num class for `weights` file if different, '
                     'useful in transfer learning with different number of classes')
flags.DEFINE_boolean('multi_gpu', False, 'Use if wishing to train with more than 1 GPU.')
"""


class DataGenerator(tf.keras.utils.Sequence):
    # Generates data for Keras
    def __init__(self, list_IDs, labels, batch_size=32, dim=(64, 64), n_channels=1,
                 n_classes=10, shuffle=True):
        # Initialization
        self.dim = dim
        self.batch_size = batch_size
        self.labels = labels
        self.list_IDs = list_IDs
        self.n_channels = n_channels
        self.n_classes = n_classes
        self.shuffle = shuffle
        self.on_epoch_end()

    def __len__(self):
        # Denotes the number of batches per epoch
        return int(np.floor(len(self.list_IDs) / self.batch_size))

    def __getitem__(self, index):
        # Generate one batch of data
        # Generate indexes of the batch
        indexes = self.indexes[index*self.batch_size:(index+1)*self.batch_size]
        # Find list of IDs

        list_IDs_temp = [self.list_IDs[k] for k in indexes]

        # Generate data
        x, y = self.__data_generation(list_IDs_temp)

        return x, y

    def on_epoch_end(self):
        # Updates indexes after each epoch
        self.indexes = np.arange(len(self.list_IDs))
        if self.shuffle == True:
            np.random.shuffle(self.indexes)

    def __data_generation(self, list_IDs_temp):
        # Generates data containing batch_size samples' # X : (n_samples, *dim, n_channels)
        # Initialization
        x = np.empty((self.batch_size, self.dim, self.n_channels))
        y = np.empty((self.batch_size), dtype=int)

        # Generate data
        for i, ID in enumerate(list_IDs_temp):
            # Store sample
            if ID.endswith('.csv'):
                x[i,] = np.load(ID)
            elif ID.endswith('.png') or ID.endswith('.jpg') or ID.endswith('.jpeg'):
                img = cv2.imread(ID)/255
                reshaped = cv2.resize(img, self.dim)
                x[i,] = reshaped

            # Store class
            y[i] = self.labels[i]

        return x, tf.keras.utils.to_categorical(y, num_classes=self.n_classes)


def generate_experiment_ID(name_model, learning_rate, batch_size, backbone_model=''):
    """
    Generate a ID name for the experiment considering the name of the model, the learning rate,
    the batch size, and the date of the experiment

    :param name_model: (str)
    :param learning_rate: (float)
    :param batch_size: (int)
    :param backbone_model: (str)
    :return: (str) id name
    """
    training_starting_time = datetime.datetime.now()
    if backbone_model != '':
        name_mod = ''.join([name_model, '+', backbone_model])
    else:
        name_mod = name_model
    id_name = ''.join([name_mod, '_lr_', str(learning_rate),
                              '_bs_', str(batch_size), '_',
                              training_starting_time.strftime("%d_%m_%Y_%H_%M")
                              ])
    return id_name

def load_pretrained_model(name_model, weights='imagenet'):

    """
    Loads a pretrained model given a name
    :param name_model: (str) name of the model
    :param weights: (str) weights names (default imagenet)
    :return: sequential model with the selected weights
    """

    if name_model == 'VGG16':
        base_model = applications.vgg16.VGG16(include_top=False, weights=weights)
        base_model.trainable = False
        input_size = (224, 224, 3)

    elif name_model == 'VGG19':
        base_model = applications.vgg19.VGG19(include_top=False, weights=weights)
        base_model.trainable = False
        input_size = (224, 224, 3)

    elif name_model == 'InceptionV3':
        base_model = applications.inception_v3.InceptionV3(include_top=False, weights=weights)
        base_model.trainable = False
        input_size = (299, 299, 3)

    elif name_model == 'ResNet50':
        base_model = applications.resnet50.ResNet50(include_top=False, weights=weights)
        base_model.trainable = False
        input_size = (224, 224, 3)

    elif name_model == 'ResNet101':
        base_model = applications.resnet.ResNet101(include_top=False, weights=weights)
        base_model.trainable = False
        input_size = (224, 224, 3)

    elif name_model == 'MobileNet':
        base_model = applications.mobilenet.MobileNet(include_top=False, weights=weights)
        base_model.trainable = False
        input_size = (224, 224, 3)

    elif name_model == 'DenseNet121':
        base_model = applications.densenet.DenseNet121(include_top=False, weights=weights)
        base_model.trainable = False
        input_size = (224, 224, 3)

    elif name_model == 'Xception':
        base_model = applications.xception.Xception(include_top=False, weights=weights)
        base_model.trainable = False
        input_size = (299, 299, 3)

    return base_model, input_size


def load_cap_models(name_model, num_classes):
    if name_model == 'simple_fc':
        cap_model = cms.simple_FC(num_classes)

    return cap_model


def load_model(name_model, backbone_model='', num_classes=1):
    # initialize model
    model = Sequential()
    # load the backbone
    base_model, input_shape_backbone = load_pretrained_model(backbone_model)
    base_model.trainable = False
    # load the cap
    cap_model = load_cap_models(name_model, num_classes)
    model.add(base_model)
    model.add(cap_model)

    return model


def generate_dict_x_y(general_dict):

    dict_x = {}
    dict_y = {}
    unique_values = []
    for i, element in enumerate(general_dict):
        dict_x[i] = general_dict[element]['image_dir']
        if general_dict[element]['classification'] not in unique_values:
            unique_values.append(general_dict[element]['classification'])
        dict_y[i] = int(unique_values.index(general_dict[element]['classification']))

    return dict_x, dict_y, unique_values


def load_data(data_dir, annotations_file='', backbone_model='',
              img_size=(255, 255), batch_size=8, prediction_mode=False):
    # If using a pre-trained backbone model, then use the img data generator from the pretrained model
    if backbone_model != '':
        if backbone_model == 'VGG16':
            data_idg = ImageDataGenerator(preprocessing_function=tf.keras.applications.vgg16.preprocess_input)
            img_width, img_height = 224, 224

        elif backbone_model == 'VGG19':
            data_idg = ImageDataGenerator(preprocessing_function=tf.keras.applications.vgg19.preprocess_input)
            img_width, img_height = 224, 224

        elif backbone_model == 'InceptionV3':
            data_idg = ImageDataGenerator(preprocessing_function=tf.keras.applications.inception_v3.preprocess_input)
            img_width, img_height = 299, 299

        elif backbone_model == 'ResNet50':
            data_idg = ImageDataGenerator(preprocessing_function=tf.keras.applications.resnet50.preprocess_input)
            img_width, img_height = 224, 224

        elif backbone_model == 'ResNet101':
            data_idg = ImageDataGenerator(preprocessing_function=tf.keras.applications.resnet.preprocess_input)
            img_width, img_height = 224, 224

        elif backbone_model == 'MobileNet':
            data_idg = ImageDataGenerator(preprocessing_function=tf.keras.applications.mobilenet.preprocess_input)
            img_width, img_height = 224, 224

        elif backbone_model == 'DenseNet121':
            data_idg = ImageDataGenerator(preprocessing_function=tf.keras.applications.densenet.preprocess_input)
            img_width, img_height = 224, 224

        elif backbone_model == 'Xception':
            data_idg = ImageDataGenerator(preprocessing_function=tf.keras.applications.xception.preprocess_input)
            img_width, img_height = 299, 299

    else:
        pass

    if annotations_file == '':
        # determine if the structure of the directory is divided by classes or there is an annotation file
        files_dir = [f for f in os.listdir(data_dir) if os.path.isdir(data_dir+f)]
        num_classes = len(files_dir)
        # if the number of sub-folders is less than two then it supposes that
        # there is an annotation file in .csv format and looks for it
        if num_classes < 2:
            list_csv_files = [f for f in os.listdir(data_dir) if os.path.isdir(f)]
            if not list_csv_files:
                print('No annotation files found or directory with sub-classes found')
            else:
                csv_annotations_file = list_csv_files.pop()
                dataframe = pd.read_csv(data_dir + csv_annotations_file)

        else:
            if prediction_mode is True:
                subdirs = [f for f in os.listdir(data_dir) if os.path.isdir(data_dir + f)]
                total_all_imgs = 0
                for subdir in subdirs:
                    all_imgs = os.listdir(''.join([data_dir, subdir, '/']))
                    total_all_imgs = total_all_imgs + len(all_imgs)
                    data_generator = data_idg.flow_from_directory(data_dir,
                                                                  batch_size=total_all_imgs,
                                                                  class_mode='categorical',
                                                                  target_size=(img_width, img_height))

            else:
                data_generator = data_idg.flow_from_directory(data_dir,
                                                          batch_size=batch_size,
                                                          class_mode='categorical',
                                                          target_size=(img_width, img_height))

            num_classes = len(data_generator.class_indices)
    else:
        # read the annotations from a csv file
        dataframe = pd.read_csv(data_dir + annotations_file)
        data_dictionary = dam.build_dictionary_data_labels(data_dir)
        # Parameters
        data, labels, num_classes = generate_dict_x_y(data_dictionary)
        params = {'dim': img_size,
                  'batch_size': 8,
                  'n_classes': num_classes,
                  'n_channels': 3,
                  'shuffle': True}
        data_generator = DataGenerator(data, labels, params, annotations_file)

    return data_generator, num_classes


def train_model(model, training_generator, validation_generator, epochs,
                batch_size, results_directory, new_results_id, shuffle=1, verbose=1):
    callbacks = [
        ModelCheckpoint(results_directory + new_results_id + "_model.h5",
                        monitor="val_loss", save_best_only=True),
        ReduceLROnPlateau(monitor='val_loss', patience=25),
        CSVLogger(results_directory + 'train_history_' + new_results_id + "_.csv"),
        TensorBoard(),
        EarlyStopping(monitor='val_loss', patience=15, restore_best_weights=True)]

    trained_model = model.fit(training_generator,
              epochs=epochs,
              shuffle=shuffle,
              batch_size=batch_size,
              validation_data=validation_generator,
              verbose=verbose,
              callbacks=callbacks)

    return trained_model


def evaluate_and_predict(model, directory_to_evaluate, results_directory,
                         output_name='', results_id='', backbone_model='', batch_size=1,
                         analyze_data=False, output_dir=''):
    print(f'Evaluation of {directory_to_evaluate}')
    # load the data to evaluate and predict
    data_gen, ene = load_data(directory_to_evaluate, backbone_model=backbone_model,
                                  batch_size=batch_size, prediction_mode=True)

    evaluation = model.evaluate(data_gen, verbose=True, steps=1)
    print('Performance:')
    print(evaluation)

    predictions = model.predict(data_gen, verbose=True, steps=1)
    print(np.shape(predictions))

    # 2DO: modify this to handle N classes
    x_0 = [x[0] for x in predictions]
    x_1 = [x[1] for x in predictions]
    #names = [os.path.basename(x) for x in data_gen.filenames]

    predicts = np.argmax(predictions, axis=1)
    label_index = {v: k for k, v in data_gen.class_indices.items()}
    predicts = [label_index[p] for p in predicts]
    print(predicts)
    df = pd.DataFrame(columns=['fname', 'class_1', 'class_2', 'over all'])
    df['fname'] = [os.path.basename(x) for x in data_gen.filenames]
    df['class_1'] = x_0
    df['class_2'] = x_1
    df['over all'] = predicts
    # save the predictions  of each case
    name_csv_file = ''.join([results_directory, '/predictions_', output_name, '_', results_id, '_.csv'])
    df.to_csv(name_csv_file, index=False)

    if analyze_data is True:
        auc_val = daa.calculate_auc_and_roc(predictions, real_values, output_name, plot=False)

    return name_csv_file


def call_models(name_model, mode, data_dir=os.getcwd() + '/data/', validation_data_dir='',
                test_data='', results_dir=os.getcwd() + '/results/', epochs=2, batch_size=4, learning_rate=0.001,
                backbone_model='', eval_val_set=False, eval_train_set=False, analyze_data=False):

    # Determine what is the structure of the data directory, if the directory contains train/val datasets
    if validation_data_dir == '':
        sub_dirs = os.listdir(data_dir)
        if 'train' in sub_dirs:
            train_data_dir = data_dir + 'train/'

        if 'val' in sub_dirs:
            validation_data_dir = data_dir + 'val/'
        else:
            print(f'not recognized substructure found in {data_dir}, please indicate the validation dataset')

    # Decide how to act according to the mode (train/predict)
    if mode == 'train':

        # Define Generators
        training_generator, num_classes = load_data(train_data_dir, backbone_model=backbone_model,
                                                    batch_size=batch_size)
        validation_generator, num_classes = load_data(validation_data_dir, backbone_model=backbone_model,
                                                      batch_size=batch_size)

        # load the model
        model = load_model(name_model, backbone_model, num_classes)
        adam = Adam(learning_rate=learning_rate)
        sgd = SGD(learning_rate=learning_rate, momentum=0.9)
        metrics = ["accuracy",  tf.keras.metrics.Precision(), tf.keras.metrics.Recall()]
        model.compile(optimizer=adam, loss='categorical_crossentropy', metrics=metrics)
        model.summary()

        # define a dir to save the results and Checkpoints
        # if results directory doesn't exists create it
        if not os.path.isdir(results_dir):
            os.mkdir(results_dir)

        # ID name for the folder and results
        new_results_id = generate_experiment_ID(name_model,learning_rate, batch_size,
                                                backbone_model=backbone_model)

        results_directory = ''.join([results_dir, new_results_id, '/'])
        # if results experiment doesn't exists create it
        if not os.path.isdir(results_directory):
            os.mkdir(results_directory)

        # track time
        start_time = datetime.datetime.now()
        # Train the model
        trained_model = train_model(model, training_generator, validation_generator, epochs,
                    batch_size, results_directory, new_results_id)

        model.save(results_directory + new_results_id + '_model')

        print('Total Training TIME:', (datetime.datetime.now() - start_time))
        print('METRICS Considered:')
        print(trained_model.history.keys())
        # in case evaluate val dataset is True
        if eval_val_set is True:
            evaluate_and_predict(model, validation_data_dir, results_directory,
                                 results_id=new_results_id, output_name='val',
                                 backbone_model=backbone_model, predict=False)

        if eval_train_set is True:
            evaluate_and_predict(model, train_data_dir, results_directory,
                                 results_id=new_results_id, output_name='train',
                                 backbone_model=backbone_model, predict=False)
        if test_data != '':
            # determine if there are sub_folders or if it's the absolute path of the dataset
            sub_dirs = [f for f in os.listdir(test_data) if os.path.isdir(test_data + f)]
            if sub_dirs:
                for sub_dir in sub_dirs:
                    sub_sub_dirs = [f for f in os.listdir(test_data + sub_dir) if os.path.isdir(test_data + sub_dir + f)]
                    if sub_sub_dirs:
                        # this means that inside each sub-dir there is more directories so we can iterate over the previous one
                        name_file = evaluate_and_predict(model, ''.join([test_data, sub_dir, '/']), results_directory,
                                             results_id=new_results_id, output_name=sub_dir,
                                             backbone_model=backbone_model, predict=True,
                                             analyze_data=analyze_data)

                        print(f'Evaluation results saved at {name_file}')
                    else:
                        name_file = evaluate_and_predict(model, test_data, results_directory,
                                                         results_id=new_results_id, output_name='test',
                                                         backbone_model=backbone_model, predict=True,
                                                         analyze_data=analyze_data)
                        print(f'Evaluation results saved at {name_file}')

            else:
                name_file = evaluate_and_predict(model, test_data, results_directory,
                                     results_id=new_results_id, output_name='test',
                                     backbone_model=backbone_model, predict=True, analyze_data=analyze_data)
                print(f'Evaluation results saved at {name_file}')


    elif mode == 'predict':
        pass


def main(_argv):

    name_model = FLAGS.name_model
    mode = FLAGS.mode
    backbone_model = FLAGS.backbone
    data_dir = FLAGS.dataset_dir
    val_data = FLAGS.val_dataset
    batch_zie = FLAGS.batch_size
    epochs = FLAGS.epochs
    test_data = FLAGS.test_dataset
    analyze_data = FLAGS.analyze_data

    """
    e.g: 
    call_models.py --name_model=simple_fc --backbone=VGG19 --mode=train --batch_size=4
    --dataset_dir=directory/to/train/data/ --batch_size=16  --epochs=5
    """

    print('INFORMATION:', name_model, backbone_model, mode)
    call_models(name_model, mode, data_dir=data_dir, backbone_model=backbone_model,
                batch_size=batch_zie, epochs=epochs, test_data=test_data, analyze_data=analyze_data)


if __name__ == '__main__':
    try:
        app.run(main)
    except SystemExit:
        pass

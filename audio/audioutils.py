# -*- coding: utf-8 -*-
# @Author: Noah Huetter
# @Date:   2020-04-16 16:59:47
# @Last Modified by:   Noah Huetter
# @Last Modified time: 2020-05-11 17:56:53

snipsDataPath = "/Users/noah/git/mlmcu-project/audio/data/snips/"
# snipsDataPath = '/media/spare/data/hey_snips_research_6k_en_train_eval_clean_ter'

scDataPath = 'train/.cache/speech_commands_v0.02'
ownDataPath = '../acquire/out'
scDownloadURL = 'http://download.tensorflow.org/data/speech_commands_v0.02.tar.gz'


def load_own_speech_commands(keywords=None, sample_len=2*16000, playsome=False, test_val_size=0.2):
  """
    Load data from the own recorded set

    X_train, y_train, X_test, y_test, X_val, y_val, keywords = load_own_speech_commands(keywords=None, sample_len=2*16000, playsome=False, test_val_size=0.2)
  """
  from os import path
  from scipy.io import wavfile
  from tqdm import tqdm
  import numpy as np

  # if directory does not exist
  if not path.exists(ownDataPath):
    print('Folder not found:', ownDataPath)
    return -1

  from pathlib import Path
  all_data = [str(x) for x in list(Path(ownDataPath).rglob("*.wav"))]

  if keywords is not None:
    print('use only samples that are in keywords')
    all_data = [x for x in all_data if x.split('/')[-2] in keywords]
  else:
    keywords = list(set([x.split('/')[-2] for x in all_data]))
  print('Using keywords: ', keywords)

  fs, _ = wavfile.read(all_data[0])

  print('Loading files count:', len(all_data))
  x_list = []
  y_list = []
  cut_cnt = 0
  for i in tqdm(range(len(all_data))): 
    fs, data = wavfile.read(all_data[i])
    if data.dtype == 'float32':
      data = ( (2**15-1)*data).astype('int16')
    x = data.copy()
    # Cut/pad sample
    if x.shape[0] < sample_len:
      if len(x) == 0:
        x = np.pad(x, (0, sample_len-x.shape[0]), mode='constant', constant_values=(0, 0))
      else:  
        x = np.pad(x, (0, sample_len-x.shape[0]), mode='edge')
    else:
      cut_cnt += 1
      x = x[:sample_len]
    # add to sample list
    x_list.append(x)
    y_list.append(keywords.index(all_data[i].split('/')[-2]))
  x = np.asarray(x_list)
  y = np.asarray(y_list)

  print('Had to cut',cut_cnt,'samples')

  print('Splitting into train/test/validation sets')
  from sklearn.model_selection import train_test_split
  X_train, X_test, y_train, y_test = train_test_split(x, y, test_size=test_val_size, random_state=42)
  X_train, X_val, y_train, y_val  = train_test_split(X_train, y_train, test_size=0.25, random_state=42)

  print("total files=%d trainsize=%d testsize=%d validationsize=%d fs=%.0f" % 
    (len(all_data), len(X_train), len(X_test), len(X_val), fs))

  # play some to check
  if playsome:
    import simpleaudio as sa
    import random

    for i in range(10):
      rset = random.choice(['X_train', 'X_test', 'X_val'])
      if rset == 'X_train':
        idx = random.randint(0, len(X_train)-1)
        print('train keyword',keywords[y_train[idx]])
        data = X_train[idx]
      if rset == 'X_test':
        idx = random.randint(0, len(X_test)-1)
        print('test keyword',keywords[y_test[idx]])
        data = X_test[idx]
      if rset == 'X_val':
        idx = random.randint(0, len(X_val)-1)
        print('validation keyword',keywords[y_val[idx]])
        data = X_val[idx]
      play_obj = sa.play_buffer(data, 1, 2, fs) # data, n channels, bytes per sample, fs
      play_obj.wait_done()
  
  print('sample count for train/test/validation')
  for i in range(len(keywords)):
    print('  %-20s %5d %5d %5d' % (keywords[i],np.count_nonzero(y_train==i),np.count_nonzero(y_test==i),np.count_nonzero(y_val==i)))

  print("Returning data: trainsize=%d  testsize=%d  validationsize=%d with keywords" % 
    (X_train.shape[0], X_test.shape[0], X_val.shape[0]))
  print(keywords)

  return X_train, y_train, X_test, y_test, X_val, y_val, keywords


def load_speech_commands(keywords = ['cat','marvin','left','zero'], 
  sample_len=2*16000, coldwords=['bed','bird','stop','visual'], noise=['_background_noise_'],
  playsome=False):
  """
    Loads samples from 
    http://download.tensorflow.org/data/speech_commands_v0.02.tar.gz

    keywords a list of which keywords to load

    coldwords   specify directories that are used and classified as coldwords
    noise       specify directory used as noise sources
  """
  import os
  import tarfile
  import urllib
  from os import path
  from scipy.io import wavfile
  from tqdm import tqdm
  import numpy as np

  # if directory does not exist
  if not path.exists(scDataPath):
    print('Please download dataset from', scDownloadURL, 'and extract it to', scDataPath)
    return -1

  
  # all files
  from pathlib import Path
  all_data = [str(x) for x in list(Path(scDataPath).rglob("*.wav"))]
  
  # print(all_data)

  with open(scDataPath+'/'+"testing_list.txt") as fd:
    test_data = [scDataPath+'/'+x.strip() for x in fd.readlines()]
  with open(scDataPath+'/'+"validation_list.txt") as fd:
    validation_data = [scDataPath+'/'+x.strip() for x in fd.readlines()]

  print('use only samples that are in keywords')
  all_data = [x for x in all_data if x.split('/')[-2] in keywords]
  test_data = [x for x in test_data if x.split('/')[-2] in keywords]
  validation_data = [x for x in validation_data if x.split('/')[-2] in keywords]

  print('scrap data files that are not in test/validation data')
  train_data = [x for x in all_data if x not in test_data]
  train_data = [x for x in train_data if x not in validation_data]

  fs, _ = wavfile.read(train_data[0])

  # print(train_data)
  # print(test_data)
  # print(validation_data)

  print("Loading data: trainsize=%d  testsize=%d  validationsize=%d fs=%.0f" % 
    (len(train_data), len(test_data), len(validation_data), fs))

  cut_cnt = 0
  def extract(fnames, sample_len):
    x_list = []
    y_list = []
    for i in tqdm(range(len(fnames))): 
      fs, data = wavfile.read(fnames[i])
      x = data.copy()

      # Cut/pad sample
      if x.shape[0] < sample_len:
        x = np.pad(x, (0, sample_len-x.shape[0]), mode='edge')
      else:
        cut_cnt += 1
        x = x[:sample_len]

      # add to sample list
      x_list.append(x)
      y_list.append(keywords.index(fnames[i].split('/')[-2]))
      
    return np.asarray(x_list), np.asarray(y_list)


  # Will store data here
  x_train, y_train = extract(train_data, sample_len)
  x_test, y_test = extract(test_data, sample_len)
  x_validation, y_validation = extract(validation_data, sample_len)

  # Load noise from wav files
  if noise is not None:
    keywords += ['_noise']
    # print('extracting noise')
    x_list = []
    y_list = []
    for noise_folder in noise:
      # list of files used as noise
      noise_data = [str(x) for x in list(Path(scDataPath+'/'+noise_folder).rglob("*.wav"))]

      for fname in noise_data:
        print('working on file',fname)
        # load data
        fs, data = wavfile.read(fname)
        x = data.copy()
        # print('  file shape',data.shape)
        # split noise samples in junks of sample_len
        n_smp = x.shape[0] // sample_len
        # print('  create nchunks ', n_smp)
        for smp in range(n_smp):
          x_list.append(x[smp*sample_len:(1+smp)*sample_len])
          y_list.append(keywords.index('_noise'))

    x_list = np.asarray(x_list)
    y_list = np.asarray(y_list)

    # split into train/test
    from sklearn.model_selection import train_test_split
    xtrain_noise, xtest_noise, ytrain_noise, ytest_noise = train_test_split(x_list, y_list, test_size=0.33, random_state=42)

    # Append noise to train/test/validation sets
    x_train = np.append(x_train, xtrain_noise, axis=0)
    y_train = np.append(y_train, ytrain_noise, axis=0)
    x_test = np.append(x_test, np.array_split(xtest_noise, 2)[0], axis=0)
    y_test = np.append(y_test, np.array_split(ytest_noise, 2)[0], axis=0)
    x_validation = np.append(x_validation, np.array_split(xtest_noise, 2)[1], axis=0)
    y_validation = np.append(y_validation, np.array_split(ytest_noise, 2)[1], axis=0)

    print('Added to train',xtrain_noise.shape[0],
      'test', np.array_split(xtest_noise, 2)[0].shape[0], 
      'and validation', np.array_split(xtest_noise, 2)[1].shape[0], 'noise samples')

  # Load coldwords from wav files
  print('Start loading coldwords')
  if coldwords is not None:
    keywords += ['_cold']
    x_list = []
    y_list = []
    for cold_folder in coldwords:
      # list of files used as noise
      cold_data = [str(x) for x in list(Path(scDataPath+'/'+cold_folder).rglob("*.wav"))]

      for fname in cold_data:
        # load data
        fs, data = wavfile.read(fname)
        x = data.copy()

        # Cut/pad sample
        if x.shape[0] < sample_len:
          x = np.pad(x, (0, sample_len-x.shape[0]), mode='edge')
        else:
          cut_cnt += 1
          x = x[:sample_len]
        # add to sample list
        x_list.append(x)
        y_list.append(keywords.index('_cold'))

    x_list = np.asarray(x_list)
    y_list = np.asarray(y_list)

    # split into train/test
    from sklearn.model_selection import train_test_split
    xtrain_cold, xtest_cold, ytrain_cold, ytest_cold = train_test_split(x_list, y_list, test_size=0.33, random_state=42)

    # Append noise to train/test/validation sets
    x_train = np.append(x_train, xtrain_cold, axis=0)
    y_train = np.append(y_train, ytrain_cold, axis=0)
    x_test = np.append(x_test, np.array_split(xtest_cold, 2)[0], axis=0)
    y_test = np.append(y_test, np.array_split(ytest_cold, 2)[0], axis=0)
    x_validation = np.append(x_validation, np.array_split(xtest_cold, 2)[1], axis=0)
    y_validation = np.append(y_validation, np.array_split(ytest_cold, 2)[1], axis=0)

    print('Added to train',xtrain_cold.shape[0],
      'test', np.array_split(xtest_cold, 2)[0].shape[0], 
      'and validation', np.array_split(xtest_cold, 2)[1].shape[0], 'cold samples')


  # play some to check
  if playsome:
    import simpleaudio as sa
    import random
    i = len(x_train)-1
    print('train keyword',keywords[y_train[i]])
    play_obj = sa.play_buffer(x_train[i], 1, 2, fs) # data, n channels, bytes per sample, fs
    play_obj.wait_done()
    i = len(x_test)-1
    print('test keyword',keywords[y_test[i]])
    play_obj = sa.play_buffer(x_test[i], 1, 2, fs) # data, n channels, bytes per sample, fs
    play_obj.wait_done()
    i = len(x_validation)-1
    print('validation keyword',keywords[y_validation[i]])
    play_obj = sa.play_buffer(x_validation[i], 1, 2, fs) # data, n channels, bytes per sample, fs
    play_obj.wait_done()
    for i in range(5):
      i = random.randint(0, len(x_train)-1)
      print('train keyword',keywords[y_train[i]])
      play_obj = sa.play_buffer(x_train[i], 1, 2, fs) # data, n channels, bytes per sample, fs
      play_obj.wait_done()
      i = random.randint(0, len(x_test)-1)
      print('test keyword',keywords[y_test[i]])
      play_obj = sa.play_buffer(x_test[i], 1, 2, fs) # data, n channels, bytes per sample, fs
      play_obj.wait_done()
      i = random.randint(0, len(x_validation)-1)
      print('validation keyword',keywords[y_validation[i]])
      play_obj = sa.play_buffer(x_validation[i], 1, 2, fs) # data, n channels, bytes per sample, fs
      play_obj.wait_done()
  
  print('Had to cut',cut_cnt,'samples')

  print('sample count for train/test/validation')
  for i in range(len(keywords)):
    print('  ',keywords[i],'counts',np.count_nonzero(y_train==i),np.count_nonzero(y_test==i),np.count_nonzero(y_validation==i))

  print("Returning data: trainsize=%d  testsize=%d  validationsize=%d with keywords" % 
    (x_train.shape[0], x_test.shape[0], x_validation.shape[0]))
  print(keywords)

  return x_train, y_train, x_test, y_test, x_validation, y_validation, keywords

def load_snips_data(sample_len=4*16000, trainsize = 1000, testsize = 100):
  """
    Load training and test data from hey snips dataset
    
      sample_len    how long each sample should be. shorter ones get padded, longer are silced
    returns x_train, y_train, x_test, y_test
  """
  import json
  from tqdm import tqdm
  from scipy.io import wavfile
  import numpy as np

  x_train_list = []
  y_train_list = []
  x_test_list = []
  y_test_list = []

  with open(snipsDataPath+'/'+"train.json") as jsonfile:
    traindata = json.load(jsonfile)

  with open(snipsDataPath+'/'+"test.json") as jsonfile:
    testdata = json.load(jsonfile)

  # Length to stuff the signals to, given in seconds
  totalSliceLength = 10 

  # number of training/test sampels to take
  if trainsize < 0:
    trainsize = len(traindata)
  if testsize < 0:
    testsize = len(testdata)

  print("Loading data with %d samples each, %d trainsize %d testsize" % (sample_len, trainsize, testsize))
  
  # get sampling rate from a file, assuming all have same fs
  fs, _ = wavfile.read(snipsDataPath+'/'+traindata[0]['audio_file_path'])

  # segmentLength = 1024 # Number of samples to use per segment

  # sliceLength = int(totalSliceLength * fs / segmentLength)*segmentLength
  # print ('sliceLength=%d' % sliceLength)

  for i in tqdm(range(trainsize)): 
    # Read wavfile
    fs, data = wavfile.read(snipsDataPath+'/'+traindata[i]['audio_file_path'])

    # Get a mutable copy of the wavfile
    _x_train = data.copy()

    # Cut/pad sample
    if _x_train.shape[0] < sample_len:
      _x_train = np.pad(_x_train, (0, sample_len-_x_train.shape[0]))
    else:
      _x_train = _x_train[:sample_len]
    
    # add to sample list
    x_train_list.append(_x_train.astype(np.float32))
    y_train_list.append(traindata[i]['is_hotword'])

  for i in tqdm(range(testsize)): 
    # Read wavfile
    fs, data = wavfile.read(snipsDataPath+'/'+testdata[i]['audio_file_path'])

    # Get a mutable copy of the wavfile
    _x_test = data.copy()

    # Cut/pad sample
    if _x_test.shape[0] < sample_len:
      _x_test = np.pad(_x_test, (0, sample_len-_x_test.shape[0]))
    else:
      _x_test = _x_test[:sample_len]
    
    # add to sample list
    x_test_list.append(_x_test.astype(np.float32))
    y_test_list.append(testdata[i]['is_hotword'])

  x_train = np.asarray(x_train_list)
  y_train = np.asarray(y_train_list)
  x_test = np.asarray(x_test_list)
  y_test = np.asarray(y_test_list)

  return x_train, y_train, x_test, y_test


######################################################################
# main
######################################################################
if __name__ == '__main__':
  # load_speech_commands()
  load_own_speech_commands(playsome=True)
# -*- coding: utf-8 -*-
# @Author: Noah Huetter
# @Date:   2020-04-30 14:43:56
# @Last Modified by:   Noah Huetter
# @Last Modified time: 2020-05-03 19:29:01

import sys

if len(sys.argv) < 2:
  print('Usage:')
  print('  kws_on_mcu.py <mode>')
  print('    Modes:')
  print('    single                   Single inference on random data')
  print('    fileinf <file>           Get file, run MFCC on host and inference on MCU')
  print('    file <file>              Get file, run MFCC and inference on host and on MCU')
  print('    mic                      Record sample from onboard mic and do stuffs')
  exit()
mode = sys.argv[1]
args = sys.argv[2:]

import numpy as np
import matplotlib.pyplot as plt
from scipy.io import wavfile
from tqdm import tqdm
import simpleaudio as sa
import scipy.io.wavfile as wavfile

# import keras
import tensorflow as tf

import mfcc_utils as mfu
import mcu_util as mcu

cache_dir = '.cache/kws_mcu'
model_file = '../firmware/src/ai/cube/kws/kws_model_2020-05-01_09:22:51.h5'
from_file = 0

# Load trained model
model = tf.keras.models.load_model(model_file)
model.summary()

input_shape = model.input.shape.as_list()[1:]
input_size = np.prod(input_shape)

# Settings
fs = 16000
sample_len_seconds = 4
sample_len = sample_len_seconds*fs
mel_mtx_scale = 128
lower_edge_hertz, upper_edge_hertz, num_mel_bins = 80.0, 7600.0, 32
frame_length = 1024
num_mfcc = 13
nSamples = int(sample_len_seconds*fs)
frame_len = frame_length
frame_step = frame_len
frame_count = 0 # 0 for auto
fft_len = frame_len
n_frames = 1 + (sample_len - frame_length) // frame_step

######################################################################
# plottery
######################################################################

def plotTwoMfcc(mfcc_host, mfcc_mcu):
  frames = np.arange(mfcc_host.shape[0])
  melbin = np.arange(mfcc_host.shape[1])

  fig = plt.figure(constrained_layout=True)
  gs = fig.add_gridspec(1, 2)

  vmin = mfcc_host.min()
  vmax = mfcc_host.max()
  ax = fig.add_subplot(gs[0, 0])
  c = ax.pcolor(frames, melbin, mfcc_host.T, cmap='PuBu', vmin=vmin, vmax=vmax)
  ax.grid(True)
  ax.set_title('host MFCC')
  ax.set_xlabel('frame')
  ax.set_ylabel('Mel bin')
  fig.colorbar(c, ax=ax)

  vmin = mfcc_mcu.min()
  vmax = mfcc_mcu.max()
  ax = fig.add_subplot(gs[0, 1])
  c = ax.pcolor(frames, melbin, mfcc_mcu.T, cmap='PuBu', vmin=vmin, vmax=vmax)
  ax.grid(True)
  ax.set_title('MCU MFCC')
  ax.set_xlabel('frame')
  ax.set_ylabel('Mel bin')
  fig.colorbar(c, ax=ax)

  return fig

def plotAudioMfcc(audio, mfcc_host, mfcc_mcu):
  t = np.linspace(0, audio.shape[0]/fs, audio.shape[0])
  frames = np.arange(mfcc_mcu.shape[0])
  melbin = np.arange(mfcc_mcu.shape[1])

  fig = plt.figure(constrained_layout=True)
  gs = fig.add_gridspec(2, 2)

  ax = fig.add_subplot(gs[0, :])
  ax.plot(t, audio, label='audio')
  ax.grid(True)
  ax.set_title('microphone data')
  ax.set_xlabel('time [s]')
  ax.set_ylabel('amplitude')
  ax.legend()

  vmin = mfcc_mcu.min()
  vmax = mfcc_mcu.max()
  ax = fig.add_subplot(gs[1, 1])
  c = ax.pcolor(frames, melbin, mfcc_mcu.T, cmap='PuBu', vmin=vmin, vmax=vmax)
  ax.grid(True)
  ax.set_title('MCU MFCC')
  ax.set_xlabel('frame')
  ax.set_ylabel('Mel bin')
  fig.colorbar(c, ax=ax)

  vmin = mfcc_host.min()
  vmax = mfcc_host.max()
  ax = fig.add_subplot(gs[1, 0])
  c = ax.pcolor(frames, melbin, mfcc_host.T, cmap='PuBu', vmin=vmin, vmax=vmax)
  ax.grid(True)
  ax.set_title('host MFCC')
  ax.set_xlabel('frame')
  ax.set_ylabel('Mel bin')
  fig.colorbar(c, ax=ax)

  return fig


######################################################################
# functions
######################################################################
def infereOnMCU(net_input, progress=False):
  """
    Upload, process and download inference
  """
  if mcu.sendCommand('kws_single_inference') < 0:
    exit()
  mcu.sendData(net_input.reshape(-1), 0, progress=progress)
  mcu_pred, tag = mcu.receiveData()
  print('Received %s type with tag 0x%x len %d' % (mcu_pred.dtype, tag, mcu_pred.shape[0]))
  return mcu_pred

def mfccAndInfereOnMCU(data, progress=False):
  """
    Upload, process and download inference of raw audio data
  """
  if mcu.sendCommand('mfcc_kws_frame') < 0:
    exit()

  print('Sending %d frames' % (n_frames))
  for frame in tqdm(range(n_frames)):
    mcu.sendData(data[frame*frame_step:frame*frame_step+frame_length], 0, progress=False)
    if mcu.waitForMcuReady() < 0:
      print('Wait for MCU timed out')

  # MCU now runs inference, wait for complete
  if mcu.waitForMcuReady() < 0:
    print('Wait for MCU timed out')

  # MCU returns net input and output
  mcu_mfccs, tag = mcu.receiveData()
  print('Received %s type with tag 0x%x len %d' % (mcu_mfccs.dtype, tag, mcu_mfccs.shape[0]))
  mcu_pred, tag = mcu.receiveData()
  print('Received %s type with tag 0x%x len %d' % (mcu_pred.dtype, tag, mcu_pred.shape[0]))
  
  return mcu_mfccs, mcu_pred

def micAndAllOnMCU():
  """
    Records a sample from mic and processes it
  """

  if mcu.sendCommand('kws_mic') < 0:
    exit()

  # MCU now runs, wait for complete
  if mcu.waitForMcuReady(timeout=5000) < 0:
    print('Wait for MCU timed out')

  # MCU returns mic data, mfcc and net output
  mic_data, tag = mcu.receiveData()
  print('Received %s type with tag 0x%x len %d' % (mic_data.dtype, tag, mic_data.shape[0]))
  mcu_mfccs, tag = mcu.receiveData()
  print('Received %s type with tag 0x%x len %d' % (mcu_mfccs.dtype, tag, mcu_mfccs.shape[0]))
  mcu_pred, tag = mcu.receiveData()
  print('Received %s type with tag 0x%x len %d' % (mcu_pred.dtype, tag, mcu_pred.shape[0]))
  
  return mic_data, mcu_mfccs.reshape(62, 13), mcu_pred


def rmse(a, b):
  return np.sqrt(np.mean((a-b)**2))

def compare(host_preds, mcu_preds):
  deviaitons = 100.0 * (1.0 - (mcu_preds+1e-9) / (host_preds+1e-9) )

  print('_________________________________________________________________')
  print('Number of inferences run: %d' % (len(host_preds)))
  print("Deviation: max %.3f%% min %.3f%% avg %.3f%% \nrmse %.3f" % (
    deviaitons.max(), deviaitons.min(), np.mean(deviaitons), rmse(mcu_preds, host_preds)))
  print('_________________________________________________________________')


def singleInference(repeat = 1):
  """
    Run a single inference on MCU
  """

  # generate some random data
  np.random.seed(20)

  host_preds = []
  mcu_preds = []
  for i in range(repeat):
    net_input = np.array(np.random.rand(input_size).reshape([1]+input_shape), dtype='float32')

    # predict on CPU
    host_preds.append(model.predict(net_input)[0][0])

    # predict on MCU
    mcu_preds.append(infereOnMCU(net_input))
    rmserror = rmse(host_preds[-1], mcu_preds[-1])
    print('host prediction: %f mcu prediction: %f rmse: %.3f' % (host_preds[-1], mcu_preds[-1], rmserror))
    
  mcu_preds = np.array(mcu_preds)
  host_preds = np.array(host_preds)
  compare(host_preds, mcu_preds)

def fileInference():
  """
    Read file and comput MFCC, launch inference on host and MCU
  """
  host_preds = []
  mcu_preds = []

  in_fs, data = wavfile.read(args[0])

  if (in_fs != fs):
    print('Sample rate of file %d doesn\'t match %d' % (in_fs, fs))
    exit()

  # Cut/pad sample
  if data.shape[0] < sample_len:
    data = np.pad(data, (0, sample_len-data.shape[0]))
  else:
    data = data[:sample_len]

  # Calculate MFCC
  o_mfcc = mfu.mfcc_mcu(data, fs, nSamples, frame_len, frame_step, frame_count, fft_len, 
    num_mel_bins, lower_edge_hertz, upper_edge_hertz, mel_mtx_scale)
  data_mfcc = np.array([x['mfcc'][:num_mfcc] for x in o_mfcc])
  # make fit shape and dtype
  net_input = np.array(data_mfcc.reshape([1]+input_shape), dtype='float32')
  
  # predict on CPU and MCU
  host_preds.append(model.predict(net_input)[0][0])
  mcu_preds.append(infereOnMCU(net_input))

  print('host prediction: %f mcu prediction: %f' % (host_preds[-1], mcu_preds[-1]))

  mcu_preds = np.array(mcu_preds)
  host_preds = np.array(host_preds)
  compare(host_preds, mcu_preds)
  # print('host prediction: %f ' % (host_preds[-1]))

def frameInference():
  """
    Reads file, computes mfcc and kws on mcu and host
  """
  host_preds = []
  mcu_preds = []
  mcu_mfccss = []

  in_fs, data = wavfile.read(args[0])
  
  if not from_file:

    if (in_fs != fs):
      print('Sample rate of file %d doesn\'t match %d' % (in_fs, fs))
      exit()

    # Cut/pad sample
    if data.shape[0] < sample_len:
      data = np.pad(data, (0, sample_len-data.shape[0]))
    else:
      data = data[:sample_len]

    # Calculate MFCC and compute on host
    o_mfcc = mfu.mfcc_mcu(data, fs, nSamples, frame_len, frame_step, frame_count, fft_len, 
      num_mel_bins, lower_edge_hertz, upper_edge_hertz, mel_mtx_scale)
    data_mfcc = np.array([x['mfcc'][:num_mfcc] for x in o_mfcc])
    net_input = np.array(data_mfcc.reshape([1]+input_shape), dtype='float32')
    host_preds.append(model.predict(net_input)[0][0])

    # Calculate MFCC and compute on MCU
    mcu_mfccs, mcu_pred = mfccAndInfereOnMCU(data, progress=True)
    mcu_preds.append(mcu_pred)
    mcu_mfccss.append(mcu_mfccs)

    mcu_mfccss = np.array(mcu_mfccss)
    mcu_preds = np.array(mcu_preds)
    host_preds = np.array(host_preds)

    # store this valuable data!
    import pathlib
    pathlib.Path(cache_dir).mkdir(parents=True, exist_ok=True)
    np.save(cache_dir+'/frame_mcu_preds.npy', mcu_preds)
    np.save(cache_dir+'/frame_mcu_mfccss.npy', mcu_mfccss)
    np.save(cache_dir+'/frame_net_input.npy', net_input)
    np.save(cache_dir+'/frame_host_preds.npy', host_preds)

  else:
    mcu_preds = np.load(cache_dir+'/frame_mcu_preds.npy')
    mcu_mfccss = np.load(cache_dir+'/frame_mcu_mfccss.npy')
    net_input = np.load(cache_dir+'/frame_net_input.npy')
    host_preds = np.load(cache_dir+'/frame_host_preds.npy')

  # report
  print('host prediction: %f mcu prediction: %f' % (host_preds[-1], mcu_preds[-1]))

  # reshape data to make plottable
  mcu_mfcc = mcu_mfccss.reshape(n_frames,num_mfcc)
  host_mfcc = net_input.reshape(n_frames,num_mfcc)
  if not from_file:
    fig = plotAudioMfcc(data, host_mfcc, mcu_mfcc)
  else:
    fig = plotTwoMfcc(host_mfcc, mcu_mfcc)

  # summarize
  mcu_preds = np.array(mcu_preds)
  host_preds = np.array(host_preds)
  stats = mcu.getStats()
  mcuInferenceTime = stats['lastinferencetime']
  mcuMfccTime = stats['AudioLastProcessingTime']
  compare(host_preds, mcu_preds)
  print('MCU Audio processing took %.2fms (%.2fms per frame)' % (n_frames*mcuMfccTime, mcuMfccTime))
  print('MCU inference took %.2fms' % (mcuInferenceTime))
  plt.show()

def micInference():
  """

  """

  # fetch data
  mic_data, mcu_mfccs, mcu_pred = micAndAllOnMCU()

  # Start playback
  fs = 16000
  play_obj = sa.play_buffer(mic_data, 1, 2, fs) # data, n channels, bytes per sample, fs
  play_obj.wait_done()
  wavfile.write(cache_dir+'/mic.wav', fs, mic_data)

  # pad/cut data
  if mic_data.shape[0] < sample_len:
    mic_data = np.pad(mic_data, (0, sample_len-mic_data.shape[0]), mode='edge')
  else:
    mic_data = mic_data[:sample_len]

  # Calculate MFCC
  nSamples = mic_data.shape[0]
  o_mfcc = mfu.mfcc_mcu(mic_data, fs, nSamples, frame_len, frame_step, frame_count, fft_len, 
    num_mel_bins, lower_edge_hertz, upper_edge_hertz, mel_mtx_scale)
  data_mfcc = np.array([x['mfcc'][:num_mfcc] for x in o_mfcc])
  # make fit shape and dtype
  net_input = np.array(data_mfcc.reshape([1]+input_shape), dtype='float32')
  
  # make host prediction
  host_pred = model.predict(net_input)[0][0]
  print('Host prediction:', host_pred)

  # plot
  mcu_mfcc = mcu_mfccs.reshape(n_frames,num_mfcc)
  host_mfcc = net_input.reshape(n_frames,num_mfcc)

  fig = plotAudioMfcc(mic_data, host_mfcc, mcu_mfcc)
  plt.show()

######################################################################
# main
######################################################################
if __name__ == '__main__':
  if mode == 'single':
    if len(args):
      singleInference(int(args[0]))
    else:
      singleInference(1)
  if mode == 'fileinf':
    fileInference()
  if mode == 'file':
    frameInference()
  if mode == 'mic':
    micInference()





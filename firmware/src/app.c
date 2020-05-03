/*
* @Author: Noah Huetter
* @Date:   2020-04-15 11:16:05
* @Last Modified by:   Noah Huetter
* @Last Modified time: 2020-05-03 19:16:09
*/
#include "app.h"
#include <stdlib.h>

#include "printf.h"
#include "microphone.h"
#include "ai.h"
#include "audioprocessing.h"
#include "hostinterface.h"
#include "cyclecounter.h"

/*------------------------------------------------------------------------------
 * Types
 * ---------------------------------------------------------------------------*/
/*------------------------------------------------------------------------------
 * Settings
 * ---------------------------------------------------------------------------*/

/**
 * @brief Enable this to show profiling on arduino Tx pin
 */
#define CYCLE_PROFILING

#ifdef CYCLE_PROFILING
  #define prfStart(x) cycProfStart(x)
  #define prfEvent(x) cycProfEvent(x)
  #define prfStop() cycProfStop()
#else
  #define prfStart(x)
  #define prfEvent(x)
  #define prfStop()
#endif

/*------------------------------------------------------------------------------
 * Private data
 * ---------------------------------------------------------------------------*/
/*------------------------------------------------------------------------------
 * Prototypes
 * ---------------------------------------------------------------------------*/
/*------------------------------------------------------------------------------
 * Publics
 * ---------------------------------------------------------------------------*/
/**
 * @brief Receive samples from host, calculate mfcc and run inference
 * @details 
 * 
 * @param args 
 * @return 
 */
int8_t appHifMfccAndInference(uint8_t *args)
{
  (void)args;
  int ret;
  
  int16_t *in_data=NULL, *out_mfccs;
  float *out_data=NULL, *mfccs=NULL, tmpf;
  
  uint8_t tag;
  uint16_t in_x, in_y;
  uint32_t len;

  prfStart("appHifMfccAndInference");

  // get net info
  aiGetInputShape(&in_x, &in_y);

  prfEvent("aiGetInputShape");

  // printf("Got input shape (%d, %d)\n", in_x, in_y);

  // 1. Receive in_y frames and process their MFCC
  in_data = malloc(AUD_MFCC_FRAME_SIZE_BYES);
  mfccs = malloc(AI_NET_INSIZE_BYTES);
  out_data = malloc(AI_NET_OUTSIZE_BYTES);

  prfEvent("malloc");

  for(int frameCtr = 0; frameCtr < in_y; frameCtr++)
  {
    // 2. Calculate MFCC
    len = hiReceive(in_data, AUD_MFCC_FRAME_SIZE_BYES, DATA_FORMAT_S16, &tag);    
    printf("received %d \n", len);

    audioCalcMFCCs(in_data, &out_mfccs);

    // copy to net in buffer and cast to float
    for(int mfccCtr = 0; mfccCtr < in_x; mfccCtr++)
    {
      tmpf = (float)out_mfccs[mfccCtr];
      mfccs[frameCtr*in_x + mfccCtr] = tmpf;
    }

    // signal host that we are ready
    hiSendMCUReady();
  }

  prfEvent("receive and MFCC");

  // 3. Run inference
  ret = aiRunInference((void*)mfccs, (void*)out_data);
  prfEvent("inference");
  hiSendMCUReady();

  // 4. report back mfccs and net out
  hiSendF32(mfccs, AI_NET_INSIZE, 0x20);
  hiSendF32(out_data, AI_NET_OUTSIZE, 0x21);
  
  prfEvent("send");

  // cleanup
  free(in_data);
  free(mfccs);
  free(out_data);

  prfEvent("free");
  prfStop();
  return ret;
}

/**
 * @brief Collects samples from mic, runs mfcc and inference while reporting 
 * data to host
 * @details 
 * 
 * @param args 
 * @return 
 */
int8_t appHifMicMfccInfere(uint8_t *args)
{
  (void) args;

  int16_t *inFrame, *out_mfccs, *inFrameBuf=NULL, *inFrameBufPtr;
  uint16_t in_x, in_y;
  float *out_data=NULL, *mfccs=NULL, tmpf;
  int ret;

  // get net info
  aiGetInputShape(&in_x, &in_y);

  // alocate memory
  mfccs = malloc(AI_NET_INSIZE_BYTES);
  out_data = malloc(AI_NET_OUTSIZE_BYTES);
  inFrameBuf = malloc(2*1024*16);

  if(!mfccs || !out_data || !inFrameBuf)
  {
    fprintf(&huart4, "malloc error!\n");
    Error_Handler();
  }

  // start continuous mic sampling
  micContinuousStart();

  // get 62 * 1024 samples, because that is the net input
  // TODO: change to 62 iterations
  inFrameBufPtr = &inFrameBuf[0];
  for (int frameCtr = 0; frameCtr < 16; frameCtr++)
  {
    // get samples, this call is blocking
    inFrame = micContinuousGet();

    // calc mfccs
    audioCalcMFCCs(inFrame, &out_mfccs); //*inp, **oup

    // copy to storage
    for(int i = 0; i < 1024; i++)
    {
      *inFrameBufPtr++ = inFrame[i];
    }

    // copy to net in buffer and cast to float
    for(int mfccCtr = 0; mfccCtr < in_x; mfccCtr++)
    {
      tmpf = (float)out_mfccs[mfccCtr];
      mfccs[frameCtr*in_x + mfccCtr] = tmpf;
    }
  } 

  // stop sampling
  micContinuousStop();

  // 3. Run inference
  ret = aiRunInference((void*)mfccs, (void*)out_data);

  // signal host that we are ready
  hiSendMCUReady();

  // 4. report back mfccs and net out
  hiSendS16(inFrameBuf, 1024*16, 0x30);
  hiSendF32(mfccs, AI_NET_INSIZE, 0x31);
  hiSendF32(out_data, AI_NET_OUTSIZE, 0x32);

  fprintf(&huart4, "Prediction: %f\n", out_data[0]);

  free(inFrameBuf);
  free(mfccs);
  free(out_data);

  return ret;
}
/*------------------------------------------------------------------------------
 * Privates
 * ---------------------------------------------------------------------------*/
/*------------------------------------------------------------------------------
 * Callbacks
 * ---------------------------------------------------------------------------*/
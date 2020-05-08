/*
* @Author: Noah Huetter
* @Date:   2020-04-15 11:16:05
* @Last Modified by:   Noah Huetter
* @Last Modified time: 2020-05-08 15:09:06
*/
#include "app.h"
#include <stdlib.h>
#include "arm_math.h"

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
 * @brief Consider network output above this thershold as hit
 */
#define TRUE_THRESHOLD 0.8

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


static float netInput[AI_NET_INSIZE_BYTES/4];
static float netOutput[AI_NET_OUTSIZE_BYTES/4];
static FASTRAM_BSS int16_t tmpBuf[1024*16]; // fills entire region

static int16_t * inFrameBuf = tmpBuf;
// static float * netInBuf = (float*)tmpBuf;


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
  uint32_t tmp32 = 0;
  
  int16_t *out_mfccs;
  float tmpf;
  
  uint8_t tag;
  uint16_t in_x, in_y;

  prfStart("appHifMfccAndInference");

  // get net info
  aiGetInputShape(&in_x, &in_y);

  prfEvent("aiGetInputShape");

  for(int frameCtr = 0; frameCtr < in_y; frameCtr++)
  {
    // 2. Calculate MFCC
    (void)hiReceive(inFrameBuf, AUD_MFCC_FRAME_SIZE_BYES, DATA_FORMAT_S16, &tag);    
    // printf("received %d \n", len);

    audioCalcMFCCs(inFrameBuf, &out_mfccs);

    // copy to net in buffer and cast to float
    for(int mfccCtr = 0; mfccCtr < in_x; mfccCtr++)
    {
      tmpf = (float)out_mfccs[mfccCtr];
      netInput[frameCtr*in_x + mfccCtr] = tmpf;
    }

    // signal host that we are ready
    hiSendMCUReady();
  }

  prfEvent("receive and MFCC");

  // 3. Run inference
  fprintf(&huart4, "inference..");
  ret = aiRunInference((void*)netInput, (void*)netOutput);
  fprintf(&huart4, "Prediction: ");
  for(tmp32 = 0; tmp32 < AI_NET_OUTSIZE; tmp32++) {fprintf(&huart4, "%.2f ", netOutput[tmp32]);}
    fprintf(&huart4, "\n");
  prfEvent("inference");
  hiSendMCUReady();

  // 4. report back mfccs and net out
  hiSendF32(netInput, AI_NET_INSIZE, 0x20);
  hiSendF32(netOutput, AI_NET_OUTSIZE, 0x21);
  
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

  int16_t *inFrame, *out_mfccs, *inFrameBufPtr;
  uint16_t in_x, in_y;
  float tmpf;
  int ret;
  uint32_t tmp32 = 0;

  // get net info
  aiGetInputShape(&in_x, &in_y);

  // start continuous mic sampling
  micContinuousStart();

  // get in_y * 1024 samples, because that is the net input
  inFrameBufPtr = &inFrameBuf[0];
  for (int frameCtr = 0; frameCtr < in_y; frameCtr++)
  {
    // get samples, this call is blocking
    inFrame = micContinuousGet();

    // calc mfccs
    audioCalcMFCCs(inFrame, &out_mfccs); //*inp, **oup

    // copy to storage
    if(frameCtr < 16)
    {
      for(int i = 0; i < 1024; i++)
      {
        *inFrameBufPtr++ = inFrame[i];
      }
    }

    // copy to net in buffer and cast to float
    for(int mfccCtr = 0; mfccCtr < in_x; mfccCtr++)
    {
      tmpf = (float)out_mfccs[mfccCtr];
      netInput[frameCtr*in_x + mfccCtr] = tmpf;
    }
  } 

  // stop sampling
  micContinuousStop();

  // 3. Run inference
  fprintf(&huart4, "inference..");
  ret = aiRunInference((void*)netInput, (void*)netOutput);
  fprintf(&huart4, "Prediction: ");
  for(tmp32 = 0; tmp32 < AI_NET_OUTSIZE; tmp32++) {fprintf(&huart4, "%.2f ", netOutput[tmp32]);}
    fprintf(&huart4, "\n");

  // signal host that we are ready
  hiSendMCUReady();

  // 4. report back mfccs and net out
  hiSendS16(inFrameBuf, 1024*16, 0x30);
  hiSendF32(netInput, AI_NET_INSIZE, 0x31);
  hiSendF32(netOutput, AI_NET_OUTSIZE, 0x32);

  return ret;
}

/**
 * @brief Runs mic sample - mfcc - inference until button press or uart receive
 * @details 
 * 
 * @param args 
 * @return 
 */
int8_t appMicMfccInfereContinuous (uint8_t *args)
{
  int16_t *inFrame, *out_mfccs, maxAmplitude, minAmplitude;
  uint16_t in_x, in_y;
  uint32_t tmp32, dstIdx, srcIdx;
  // uint32_t netInBufOff = 0;
  bool doAbort = false;
  int ret;
  float tmpf;

  aiGetInputShape(&in_x, &in_y); // x = 13, y = 62 (nframes)
  fprintf(&huart1, "Input shape x,y: (%d,%d)\n", in_x, in_y);

  // start continuous mic sampling
  micContinuousStart();

  // fill buffer once
  for (int frameCtr = 0; (frameCtr < in_y) && !doAbort; frameCtr++)
  {
    // get samples, this call is blocking
    inFrame = micContinuousGet();

    // calc mfccs
    audioCalcMFCCs(inFrame, &out_mfccs); //*inp, **oup

    // copy to net in buffer and cast to float
    for(int mfccCtr = 0; mfccCtr < in_x; mfccCtr++)
    {
      tmpf = (float)out_mfccs[mfccCtr];
      netInput[frameCtr*in_x + mfccCtr] = tmpf;
    }

    if(IS_BTN_PRESSED() || (huart1.Instance->ISR & UART_FLAG_RXNE) ) doAbort = true;
  }

  // now enter a loop where sampling and inference is done simultaneously
  while(!doAbort)
  {
    // get amplitude max
    arm_max_q15(inFrame, 1024, &maxAmplitude, &tmp32);
    arm_min_q15(inFrame, 1024, &minAmplitude, &tmp32);

    // 3. Run inference
    ret = aiRunInference((void*)netInput, (void*)netOutput);

    // store net input
    // for(int i = 0; i < in_x*in_y; i++)
    //   netInBuf[i+netInBufOff] = netInput[i];
    // netInBufOff += in_x*in_y;

    // report
    fprintf(&huart1, "pred: [ ");
    for(tmp32 = 0; tmp32 < AI_NET_OUTSIZE; tmp32++)
    {
      fprintf(&huart1, "%.2f ", netOutput[tmp32]);
    }
    fprintf(&huart1, "] ret: %d ampl: %d", ret, maxAmplitude-minAmplitude);

    arm_max_f32(netOutput, AI_NET_OUTSIZE, &tmpf, &tmp32);
    printf(" likely: %s", aiGetKeywordFromIndex(tmp32));
    if( (tmpf > TRUE_THRESHOLD) )
    {
      printf(" spotted %s", aiGetKeywordFromIndex(tmp32));
    }
    fprintf(&huart1, "\n");

    if(netOutput[0] > TRUE_THRESHOLD) LED2_ORA();
    else LED2_BLU();

    // get samples, this call is blocking
    inFrame = micContinuousGet();

    // calc mfccs
    audioCalcMFCCs(inFrame, &out_mfccs); //*inp, **oup

    // shift net buffer contents one frame back
    dstIdx = (in_y-1)*in_x;
    srcIdx = (in_y-2)*in_x;
    for(int netInCtr = 0; netInCtr < ( (in_y-1)*in_x ); netInCtr++)
    {
      netInput[dstIdx--] = netInput[srcIdx--];
    }

    // copy new sample in at front
    for(int mfccCtr = 0; mfccCtr < in_x; mfccCtr++)
    {
      tmpf = (float)out_mfccs[mfccCtr];
      netInput[mfccCtr] = tmpf;
    }

    // check abort condition
    if(IS_BTN_PRESSED() || (huart1.Instance->ISR & UART_FLAG_RXNE) ) doAbort = true;

    // if(netInBufOff > 12*in_x*in_y) doAbort = true;
  }

  // stop sampling
  micContinuousStop();

  // flush input
  (void)huart1.Instance->RDR;

  // send net input history
  // hiSendF32(netInBuf, 12*AI_NET_INSIZE, 0x20);

  return ret;
}

/**
 * @brief Runs mic sample - mfcc - inference until button press or uart receive
 * @details not shifting but starting entire net input with new samples
 * 
 * @param args 
 * @return 
 */
int8_t appMicMfccInfereBlocks (uint8_t *args)
{
  int16_t *inFrame, *out_mfccs, maxAmplitude, minAmplitude;
  uint16_t in_x, in_y;
  uint32_t tmp32;
  // int32_t netInBufOff = 0;
  bool doAbort = false;
  int ret;
  float tmpf;

  aiGetInputShape(&in_x, &in_y); // x = 13, y = 62 (nframes)
  fprintf(&huart1, "Input shape x,y: (%d,%d)\n", in_x, in_y);

  // start continuous mic sampling
  micContinuousStart();

  // now enter a loop where sampling and inference is done simultaneously
  while(!doAbort)
  {

    // fill buffer once
    for (int frameCtr = 0; (frameCtr < in_y) && !doAbort; frameCtr++)
    {
      // get samples, this call is blocking
      inFrame = micContinuousGet();

      // calc mfccs
      audioCalcMFCCs(inFrame, &out_mfccs); //*inp, **oup

      // copy to net in buffer and cast to float
      for(int mfccCtr = 0; mfccCtr < in_x; mfccCtr++)
      {
        tmpf = (float)out_mfccs[mfccCtr];
        netInput[frameCtr*in_x + mfccCtr] = tmpf;
      }

      if(IS_BTN_PRESSED() || (huart1.Instance->ISR & UART_FLAG_RXNE) ) doAbort = true;
    }

    // get amplitude max
    arm_max_q15(inFrame, 1024, &maxAmplitude, &tmp32);
    arm_min_q15(inFrame, 1024, &minAmplitude, &tmp32);

    // 3. Run inference
    ret = aiRunInference((void*)netInput, (void*)netOutput);

    // store net input
    // for(int i = 0; i < in_x*in_y; i++)
    //   netInBuf[i+netInBufOff] = netInput[i];
    // netInBufOff += in_x*in_y;

    // report
    fprintf(&huart1, "pred: [ ");
    for(tmp32 = 0; tmp32 < AI_NET_OUTSIZE; tmp32++)
    {
      fprintf(&huart1, "%.2f ", netOutput[tmp32]);
    }
    fprintf(&huart1, "] ret: %d ampl: %d", ret, maxAmplitude-minAmplitude);

    arm_max_f32(netOutput, AI_NET_OUTSIZE, &tmpf, &tmp32);
    printf(" likely: %s", aiGetKeywordFromIndex(tmp32));
    if( (tmpf > TRUE_THRESHOLD) )
    {
      printf(" SPOTTED %s", aiGetKeywordFromIndex(tmp32));
    }
    fprintf(&huart1, "\n");

    if(netOutput[0] > TRUE_THRESHOLD) LED2_ORA();
    else LED2_BLU();

    // check abort condition
    if(IS_BTN_PRESSED() || (huart1.Instance->ISR & UART_FLAG_RXNE) ) doAbort = true;

    // if(netInBufOff > 12*in_x*in_y) doAbort = true;
  }

  // stop sampling
  micContinuousStop();

  // flush input
  (void)huart1.Instance->RDR;

  // send net input history
  // hiSendF32(netInBuf, 12*AI_NET_INSIZE, 0x20);

  return ret;
}


/*------------------------------------------------------------------------------
 * Privates
 * ---------------------------------------------------------------------------*/
/*------------------------------------------------------------------------------
 * Callbacks
 * ---------------------------------------------------------------------------*/
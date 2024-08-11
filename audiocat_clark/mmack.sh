#!/bin/bash

# message types
###############
: '
    [init]
    [init_ack_chat]
    [init_ack_shell]
    [init_ack_file]
    [keepalive]
    [test]
    [preamble] (text defined in preamble parameter)    
    [trailer]  (text defined in trailer parameter)    
                    <seq_tx><seq_rx>[ack]
                    <seq_tx><seq_rx>[data]<input_data>
                    <seq_tx><seq_rx>[file]<file_data>         
                    <seq_tx><seq_rx>[file_end]<file_data>                                 
                    \_______________ ___________________/
                                    V
                                encrypted
'

# configuration
###############
TMP_PATH=$(cat cfg/tmp_path)
TRAILER=$(cat ${HOME}${TMP_PATH}/cfg/trailer)
CIPHER_ALGO=$(cat ${HOME}${TMP_PATH}/cfg/cipher_algo)
ARMOR=$(cat ${HOME}${TMP_PATH}/cfg/armor)
BAUD=$(cat ${HOME}${TMP_PATH}/cfg/baud)
SYNCBYTE=$(cat ${HOME}${TMP_PATH}/cfg/syncbyte)
NEED_ACK=$(cat ${HOME}${TMP_PATH}/cfg/need_ack)
VERBOSE=$(cat ${HOME}${TMP_PATH}/cfg/verbose)
MSGFILE="${HOME}${TMP_PATH}/tmp/msgtx.gpg"
TMPFILE="${HOME}${TMP_PATH}/tmp/out.txt"
INVALID_SEQ_NR=200

# state
#######
SEQ_TX_FILE="${HOME}${TMP_PATH}/state/seq_tx"
SEQ_RX_FILE="${HOME}${TMP_PATH}/state/seq_rx"
SEQ_TX_ACKED_FILE="${HOME}${TMP_PATH}/state/seq_tx_acked"
SEQ_TX=$(cat ${SEQ_TX_FILE})
SEQ_TX_ACKED=$(cat ${SEQ_TX_ACKED_FILE})
SEQ_RX_NEW=$(cat ${SEQ_RX_FILE})            
if [[ ${SEQ_RX_NEW} != ${INVALID_SEQ_NR} ]] ; then
    # we don't clean state, that will be done in mmshellout.sh     
    SEQ_RX=${SEQ_RX_NEW}
else
    if [ "${VERBOSE}" == true ] ; then
        echo "WARNING: mmack.sh called but SEQ_RX = INVALID_SEQ_NR. Defaulting to 0!"
    fi
    SEQ_RX=0 # default is different to 1 which is the first value to be received
fi
seq_tx=$((SEQ_TX+33))
seq_rx=$((SEQ_RX+33))
seq_tx_ascii=$(printf "\x$(printf %x $seq_tx)") 
seq_rx_ascii=$(printf "\x$(printf %x $seq_rx)") 

# the first argument is the password
PASSWORD="$1"
                                  
# send ACK
##########
if [ "${NEED_ACK}" == "true" ] ; then
    if [[ ${SEQ_RX} != ${INVALID_SEQ_NR} ]] && [[ ${SEQ_RX_NEW} != ${INVALID_SEQ_NR} ]] ; then
        # SEQ_RX to be acknowledged in ACK message
        # we don't clean state, that will be done in mmshellout.sh
        SEQ_RX=${SEQ_RX_NEW}
        seq_rx=$((SEQ_RX+33))
        seq_rx_ascii=$(printf "\x$(printf %x $seq_rx)")        
        # send ACK without data          
        echo "${seq_tx_ascii}${seq_rx_ascii}[ack]" | source gpg.src
        if [ "${VERBOSE}" == true ] ; then
            echo "> ack[${SEQ_TX},${SEQ_RX}]"
        fi
        # send message with encrypted data
        cat ${MSGFILE} | source tx.src
        # add trailer?
        if [ "${TRAILER}" != "" ] ; then
            echo "${TRAILER}" | source tx.src
        fi            
    else
        if [ "${VERBOSE}" == true ] ; then
            echo "FAILED to send: ack[${SEQ_TX},${SEQ_RX},${SEQ_RX_NEW}]"
        fi            
    fi
fi                        

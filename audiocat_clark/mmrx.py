import sys
import subprocess
import logging
from getpass import getpass
from io import StringIO
import time
from time import sleep
import select
import threading
from pathlib import Path
import os
from time import sleep
import queue
import datetime
import random
import getopt



# message types
###############
'''
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
                    <seq_tx><seq_rx>[file_name]<file_name>[file]<file_data>
                    <seq_tx><seq_rx>[file_name]<file_name>[file_end]<file_data>
                    \_______________ _________________________________________/
                                    V
                                encrypted
'''



# module variables
##################
TX_SENDING = False
SESSION_ESTABLISHED = False
SHELL_OUTPUT_READ_TIMEOUT_SEC = 1
NEED_ACK = False
WAITING_FOR_COMMAND_OUTPUT = False



# main
######
def main():
    global TX_SENDING
    global SESSION_ESTABLISHED
    global WAITING_FOR_COMMAND_OUTPUT
    global NEED_ACK
    
    # local variables
    #################
    PASSWORD = ""
    run_thread = True
    stdin_err_cnt = 0
    file_name = ""
    RND_MAX_DELAY_MS = 1000
    AVG_RND_DELAY_SEC = (RND_MAX_DELAY_MS/2000.0)
    
    # definitions
    #############
    INCOMPLETE_FILE_OUT_64 = 0
    WRITE_FILE_OUT_64 = 1
    WRITE_AND_DECODE_FILE_OUT_64 = 2
    APPEND_FILE_OUT_64 = 3
    DECODE_FILE_OUT_64 = 4
    APPEND_AND_DECODE_FILE_OUT_64 = 5
    state_file_out = INCOMPLETE_FILE_OUT_64
    
    # read tmp path
    ###############
    f = open("cfg/tmp_path", "r")
    TMP_PATH = f.read().splitlines()[0]
    f.close()        
    HOME = str(Path.home())
    
    # default configuration
    #######################
    REVERSE_SHELL = False
    FILE_TRANSFER = False
    RETRANSMISSION_TIMEOUT_SEC = 3.5
    SEND_DELAY_SEC = 0.1
    ARMOR = "--armor"  # ""
    SHOW_RX_PROMPT = False
    SHOW_TX_PROMPT = False
    VERBOSE = False
    TEMP_GPG_FILE = HOME+TMP_PATH+"/tmp/msgrx.gpg"
    SEQ_TX_FILE = HOME+TMP_PATH+"/state/seq_tx"
    SEQ_RX_FILE = HOME+TMP_PATH+"/state/seq_rx"
    SEQ_TX_ACKED_FILE = HOME+TMP_PATH+"/state/seq_tx_acked"
    SESSION_ESTABLISHED_FILE = HOME+TMP_PATH+"/state/session_established"
    LOGGING_LEVEL = logging.WARNING
    INVALID_SEQ_NR = "200"  # (outside 0-93 range!)
    TIMEOUT_POLL_SEC = float(0.01)
    SPLIT_TX_LINES = int(25)
    LOG_TO_FILE = False
    PIPE_SHELL_IN = HOME+TMP_PATH+"/tmp/pipe_shell_in"
    PIPE_SHELL_OUT = HOME+TMP_PATH+"/tmp/pipe_shell_out"
    PIPE_FILE_IN = HOME+TMP_PATH+"/tmp/pipe_file_in"
    TMPFILE_BASE64_IN=HOME+TMP_PATH+"/tmp/in.64"

    # default state
    ###############
    TRANSMITTER_STARTED_FILE = HOME+TMP_PATH+"/state/transmitter_started"
    TRANSMITTER_STARTED = False
    TX_SENDING_FILE_FILE = HOME+TMP_PATH+"/state/tx_sending_file"
    TX_SENDING_FILE = False
    RX_RECEIVING_FILE = False    
    SESSION_ESTABLISHED = False
    
    
    # parse arguments
    #################                    
    if len(sys.argv) > 1:
        if sys.argv[1] != "":
            PASSWORD = sys.argv[1]

    # current configuration
    #######################  
    # reverse shell
    # can be activated with an argument or with a configuration file
    if len(sys.argv) > 2:
        if sys.argv[2] == "-s" or sys.argv[2] == "--rs" or sys.argv[2] == "--reverse-shell":
            REVERSE_SHELL = True
        elif sys.argv[2] == "-f" or sys.argv[2] == "--file" or sys.argv[2] == "--file-transfer":
            FILE_TRANSFER = True
    else:
        f = open(HOME+TMP_PATH+"/cfg/reverse_shell", "r")
        tmp_rs = f.read().splitlines()[0]
        f.close()
        if tmp_rs == "true":
            REVERSE_SHELL = True
    print("reverse_shell = " + str(REVERSE_SHELL))  
    # retransmission_timeout_sec
    f = open(HOME+TMP_PATH+"/cfg/keepalive_time_sec", "r")
    KEEPALIVE_TIME_SEC = f.read().splitlines()[0]
    KEEPALIVE_TIME_SEC_F = float(KEEPALIVE_TIME_SEC)
    if KEEPALIVE_TIME_SEC_F <= AVG_RND_DELAY_SEC:
        AVG_RND_DELAY_SEC = 0.0
        print("AVG_RND_DELAY_SEC changed to 0")
    f.close()
    print("retransmission_timeout_sec = " + str(RETRANSMISSION_TIMEOUT_SEC))
    # send_delay_sec
    f = open(HOME+TMP_PATH+"/cfg/send_delay_sec", "r")
    SEND_DELAY_SEC = f.read().splitlines()[0]
    SEND_DELAY_SEC_F = float(SEND_DELAY_SEC)
    f.close()
    print("send_delay_sec = " + str(SEND_DELAY_SEC))
    # armor
    f = open(HOME+TMP_PATH+"/cfg/armor", "r")
    ARMOR = f.read().splitlines()[0]
    f.close()
    print("armor = " + ARMOR)
    # need_ack
    f = open(HOME+TMP_PATH+"/cfg/need_ack", "r")
    if f.read().splitlines()[0] == "true":
        NEED_ACK = True
    f.close()
    print("need_ack = " + str(NEED_ACK))
    # show_rx_prompt
    f = open(HOME+TMP_PATH+"/cfg/show_rx_prompt", "r")
    if f.read().splitlines()[0] == "true":
        SHOW_RX_PROMPT = True
    f.close()
    print("show_rx_prompt = " + str(SHOW_RX_PROMPT))
    # show_tx_prompt
    f = open(HOME+TMP_PATH+"/cfg/show_tx_prompt", "r")
    if f.read().splitlines()[0] == "true":
        SHOW_TX_PROMPT = True
    f.close()
    print("show_tx_prompt = " + str(SHOW_TX_PROMPT))
    # syncbyte
    f = open(HOME+TMP_PATH+"/cfg/syncbyte", "r")
    SYNC_BYTE = str(f.read().splitlines()[0])
    f.close()
    # print("syncbyte = " + SYNC_BYTE)  # already printed in bash
    # baud
    f = open(HOME+TMP_PATH+"/cfg/baud", "r")
    BAUD = str(f.read().splitlines()[0])
    f.close()
    # print("baud = " + BAUD)  # already printed in bash 
    # timeout_poll_sec
    f = open(HOME+TMP_PATH+"/cfg/timeout_poll_sec", "r")
    TIMEOUT_POLL_SEC = float(f.read().splitlines()[0])
    f.close()
    print("timeout_poll_sec = " + str(TIMEOUT_POLL_SEC))
    # split_tx_lines
    f = open(HOME+TMP_PATH+"/cfg/split_tx_lines", "r")
    SPLIT_TX_LINES = int(f.read().splitlines()[0])
    f.close()    
    # log_to_file
    f = open(HOME+TMP_PATH+"/cfg/log_to_file", "r")
    if f.read().splitlines()[0] == "true":
        LOG_TO_FILE = True
        date_time = datetime.datetime.now().strftime("%d/%m/%Y, %H:%M:%S")
        f = open("out/log.txt", "w")
        f.write("audiocat started: " + date_time + "\n")
        f.close()
    f.close()
    print("log_to_file = " + str(LOG_TO_FILE))            
    # logging_level
    f = open(HOME+TMP_PATH+"/cfg/logging_level", "r")
    LOGGING_LEVEL = f.read().splitlines()[0]
    f.close() 
    # evaluate LOGGING_LEVEL as string
    if LOGGING_LEVEL == "logging.NOTSET":
        LOGGING_LEVEL = logging.NOTSET
    elif LOGGING_LEVEL == "logging.DEBUG":
        LOGGING_LEVEL = logging.DEBUG
    elif LOGGING_LEVEL == "logging.INFO":
        LOGGING_LEVEL = logging.INFO
    elif LOGGING_LEVEL == "logging.WARNING":
        LOGGING_LEVEL = logging.WARNING
    elif LOGGING_LEVEL == "logging.ERROR":
        LOGGING_LEVEL = logging.ERROR
    elif LOGGING_LEVEL == "logging.CRITICAL":
        LOGGING_LEVEL = logging.CRITICAL
    else:
        LOGGING_LEVEL = logging.WARNING   
    # verbose
    f = open(HOME+TMP_PATH+"/cfg/verbose", "r")
    if f.read().splitlines()[0] == "true":
        VERBOSE = True
    f.close()
    if VERBOSE and LOGGING_LEVEL > logging.INFO:
        print("verbose = true (logging_level forced to logging.INFO)")
    else:
        print("verbose = false")
    
    # logging
    #########   
    if VERBOSE:
        # force logging level to info at least
        # which is the level to output VERBOSE infos
        if LOGGING_LEVEL > logging.INFO:            
            LOGGING_LEVEL = logging.INFO
        if LOG_TO_FILE:
            logging.basicConfig(filename="out/log.txt", filemode='a', format='%(message)s', level=LOGGING_LEVEL, force=True)
        else:
            logging.basicConfig(format='%(message)s', level=LOGGING_LEVEL, force=True)
    else:
        if LOG_TO_FILE:            
            logging.basicConfig(filename="out/log.txt", filemode='a', 
            format='%(asctime)s.%(msecs)03d %(levelname)s {%(module)s} [%(funcName)s] %(message)s',
            datefmt='%H:%M:%S', level=LOGGING_LEVEL, force=True)   
        else:
            logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s {%(module)s} [%(funcName)s] %(message)s',
            datefmt='%H:%M:%S', level=LOGGING_LEVEL, force=True)                 
    # make sure we also see stderr when logging level is debug
    if LOGGING_LEVEL == logging.DEBUG:
        SENT_OUT_TO_DEV_NULL = ""
    else:
        SENT_OUT_TO_DEV_NULL = " 2>/dev/null"
        
    # print logging_level
    #####################
    # evaluate LOGGING_LEVEL as integer value
    if LOGGING_LEVEL == logging.NOTSET:
        print("logging_level = logging.NOTSET")
    elif LOGGING_LEVEL == logging.DEBUG:
        print("logging_level = logging.DEBUG")
    elif LOGGING_LEVEL == logging.INFO:
        print("logging_level = logging.INFO")
    elif LOGGING_LEVEL == logging.WARNING:
        print("logging_level = logging.WARNING")
    elif LOGGING_LEVEL == logging.ERROR:
        print("logging_level = logging.ERROR")
    elif LOGGING_LEVEL == logging.CRITICAL:
        print("logging_level = logging.CRITICAL")
    else:
        print("logging_level = logging.WARNING")           

    # current state
    ###############
    # session_established
    f = open(SESSION_ESTABLISHED_FILE, "r")
    if f.read().splitlines()[0] == "true":
        SESSION_ESTABLISHED = True
    f.close()
    if REVERSE_SHELL:
        # force session not yet established
        SESSION_ESTABLISHED = False
        f = open(SESSION_ESTABLISHED_FILE, "w")
        f.write("false")
        f.close()
    else:
        # transmitter_started
        f = open(TRANSMITTER_STARTED_FILE, "r")
        if f.read().splitlines()[0] == "true":
            TRANSMITTER_STARTED = True
        f.close()
        # tx_sending_file
        f = open(TX_SENDING_FILE_FILE, "r")
        if f.read().splitlines()[0] == "true":
            TX_SENDING_FILE = True
        f.close()         

    # helper functions
    ##################
    def clear_seq_nrs():
        f = open(SEQ_TX_FILE, "w")
        f.write("0")
        f.close()
        logging.debug("set seq_tx to 0")
        f = open(SEQ_RX_FILE, "w")
        f.write(INVALID_SEQ_NR)
        f.close()
        logging.debug("set seq_rx to INVALID_SEQ_NR (outside 0-93 range!)")  
        f = open(SEQ_TX_ACKED_FILE, "w")
        f.write(INVALID_SEQ_NR)
        f.close()
        logging.debug("set seq_tx_acked to INVALID_SEQ_NR (outside 0-93 range!)")     
        
    def init_session():
        global SESSION_ESTABLISHED  
        clear_seq_nrs()    
        SESSION_ESTABLISHED = True          
        f = open(SESSION_ESTABLISHED_FILE, "w")
        f.write("true")
        f.close()
        logging.debug("set session_established to true") 

    def end_session():
        global SESSION_ESTABLISHED
        clear_seq_nrs()
        SESSION_ESTABLISHED = False             
        f = open(SESSION_ESTABLISHED_FILE, "w")
        f.write("false")
        f.close()
        logging.debug("set session_established to false")
            
    def minimodem_tx(message):
        messageQueue.put(message)

    # thread to transmit minimodem message
    # (without encryption and seq. nr.)
    ######################################
    def TransmitMinimodemThread():        
        global TX_SENDING
        # main thread loop
        ##################
        while run_thread:
            # block until a message is input to the queue
            message = messageQueue.get(block=True)
            # avoid collissions with tranmissions triggered somewhere else
            while TX_SENDING:
                sleep(TIMEOUT_POLL_SEC)                        
            # send message
            TX_SENDING = True
            command = "echo '" + message + "' | minimodem --tx --ascii --quiet --startbits 1 --stopbits 1.0 --sync-byte " + SYNC_BYTE + " " + BAUD                 
            if VERBOSE:
                # stdout to see VERBOSE text from minimodem
                p1 = subprocess.Popen(command, shell=True, stdout=None, text=True)
            else:
                p1 = subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, text=True)        
            out, err = p1.communicate()                                        
            if p1.returncode == 0:
                p1.terminate()
                p1.kill()
                logging.info("> " + message)
            TX_SENDING = False                        
                
    if REVERSE_SHELL or FILE_TRANSFER:
        # shell: need to send ACKs here because a user input does not always produce a shell output
        # thus no mmshellout.sh gets called and thus no AKCs are sent
        # file: for file transfers the RX process is responsible to send ACKs
        def transmit_ack():
            ackQueue.put("*")
                
        # thread to transmit ACKs
        #########################
        def TransmitAckThread():
            global TX_SENDING        
            # main thread loop
            ##################
            while run_thread:
                # block until something is input to the queue
                # we don't even check it, any input will trigger an ack
                ackCmd = ackQueue.get(block=True)
                # TODO: use delay also with chat and reverse-shell?            
                if FILE_TRANSFER:
                    sleep(SEND_DELAY_SEC_F)                
                # avoid collissions with tranmissions triggered somewhere else
                while TX_SENDING:
                    sleep(TIMEOUT_POLL_SEC)                
                # send ack
                TX_SENDING = True
                # add single quotes around the password in case it contains spaces   
                # note: we may instead send something in data with ./mmdata.sh, i.o. just [ack], in order to flush the shell command output
                command = "./mmack.sh '" + PASSWORD + "'"
                if VERBOSE:
                    # stdout to see VERBOSE text from mmack.sh                        
                    p1 = subprocess.Popen(command, shell=True, stdout=None, text=True)
                else:
                    p1 = subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, text=True)
                out, err = p1.communicate()
                if p1.returncode == 0:
                    p1.terminate()
                    p1.kill()
                    logging.info("> [ack]")
                TX_SENDING = False      
                          
    if REVERSE_SHELL:                
        # thread to gather and transmit output from shell    
        #################################################
        def ShellTransmitThread():
            global TX_SENDING
            global SESSION_ESTABLISHED
            global WAITING_FOR_COMMAND_OUTPUT
            global NEED_ACK
            # main thread loop
            ##################
            while run_thread:
                # block until data in queue
                while shellOutputQueue.empty() == True:
                    sleep(TIMEOUT_POLL_SEC)         
                           
                # initialize buffer, flags and counters
                shell_output = ""
                shell_timeout = False
                read_lines = 0
                start_time = datetime.datetime.now()   
                         
                # consume all shell output lines up to SPLIT_TX_LINES or timeout SHELL_OUTPUT_READ_TIMEOUT_SEC
                # exit when SPLIT_TX_LINES or SHELL_OUTPUT_READ_TIMEOUT_SEC even if there are still data in the queue
                # this makes sure we send for now at least a partial response to the remote caller
                while (shellOutputQueue.empty() == False) and (read_lines < SPLIT_TX_LINES) and (shell_timeout == False):
                    try:
                        shell_output_part = shellOutputQueue.get(block=True, timeout=SHELL_OUTPUT_READ_TIMEOUT_SEC)
                        # append data
                        if shell_output_part != None:
                            shell_output = "".join([shell_output, shell_output_part])
                            read_lines = read_lines + 1                    
                        # timeout?
                        end_time = datetime.datetime.now()
                        delta_time = (end_time - start_time).total_seconds()
                        if delta_time > SHELL_OUTPUT_READ_TIMEOUT_SEC:
                            shell_timeout = True                    
                    except Exception as e:
                        logging.exception("Exception in shellOutputQueue: " + str(e))  
                                      
                # some checks
                if SESSION_ESTABLISHED and shell_output != "":
                    # reset flag
                    if NEED_ACK:
                        WAITING_FOR_COMMAND_OUTPUT = False
                    # prepare data for transmission as a "block" (otherwise we would send each line separately)
                    shell_output_printable = shell_output
                    shell_output = shell_output.replace("\n", "\r")                
                    # TODO: find out why we get characters that are not allowed in file names
                    #       and extend this workaround to further characters like *, ?, >, <, :, |, ...
                    #       check e.g. https://stackoverflow.com/questions/4814040/allowed-characters-in-filename
                    shell_output = shell_output.replace("(", "\(")
                    shell_output = shell_output.replace(")", "\)")
                    # avoid collissions
                    while TX_SENDING:
                        sleep(TIMEOUT_POLL_SEC)
                    # send data
                    TX_SENDING = True
                    # add single quotes around the password in case it contains spaces        
                    command = "./mmshellout.sh '" + PASSWORD + "' " + shell_output
                    if VERBOSE:
                        # stdout to see VERBOSE text from mmshellout.sh
                        p1 = subprocess.Popen(command, shell=True, stdout=None, text=True)
                    else:
                        p1 = subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, text=True)
                    out, err = p1.communicate()                
                    if p1.returncode == 0:
                        p1.terminate()
                        p1.kill()
                        # show shell output in prompt
                        #############################
                        if SHOW_TX_PROMPT:
                            count = shell_output_printable.count("\n") - 1
                            shell_output_printable = shell_output_printable.replace("\n", "\n  ", count)
                            print("> " + shell_output_printable, end='')
                        else:                                                                
                            print(shell_output_printable, end='')                                          
                    TX_SENDING = False
            
        # thread to get output from shell
        #################################
        def ShellOutputThread():        
            # shell output fifo
            ###################
            # Open read end of pipe. Open this in non-blocking mode since otherwise it
            # may block until another process/threads opens the pipe for writing.
            pipe_shell_out = os.open(PIPE_SHELL_OUT, os.O_RDONLY | os.O_NONBLOCK)
            # execute cat pipe_shell_out
            ############################
            proc = subprocess.Popen('cat '+PIPE_SHELL_OUT, 
                                    shell=True, 
                                    stdin=pipe_shell_out,
                                    stderr=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    text=True)    
            # main loop
            ###########          
            while run_thread:        
                shell_output_part = proc.stdout.readline()                                                                    
                # put shell output part in queue to be gathered and sent in separate thread
                if shell_output_part != "":            
                    shellOutputQueue.put(shell_output_part)
                
            # clean up
            ##########
            proc.terminate()
            proc.wait(timeout=0.2)
            # Close read end of pipe since it is not used in the parent process.
            os.close(pipe_shell_out)
            os.unlink(PIPE_SHELL_OUT)       
    
    # banner
    ########
    if REVERSE_SHELL:
        print("******************************")
        print("*** audiocat reverse shell ***")
        print("******************************")
    elif FILE_TRANSFER:
        print("******************************************************")
        print("*** audiocat file transfer receiver,")
        print("*** the received files can be found in folder rx_files")
        print("******************************************************")            
    else:
        print("******************************")
        print("*** audiocat chat receiver ***")
        print("******************************")
        
    # queues and threads
    ####################
    messageQueue = queue.Queue()
    # start thread to transmit data
    transmitMinimodemThread = threading.Thread(name="TransmitMinimodemThread", target=TransmitMinimodemThread)
    transmitMinimodemThread.start()     

    # start threads for reverse shell
    #################################
    if REVERSE_SHELL:
        # queue for shell output
        shellOutputQueue = queue.Queue()
        # pipe for shell in
        pipe_shell_in = os.open(PIPE_SHELL_IN, os.O_WRONLY)
        # start thread to gather and transmit output from shell
        shellTransmitThread = threading.Thread(name="ShellTransmitThread", target=ShellTransmitThread)
        shellTransmitThread.start()
        # start thread to get output from shell
        shellOutputThread = threading.Thread(name="ShellOutputThread", target=ShellOutputThread)
        shellOutputThread.start()
    elif FILE_TRANSFER:
        # pipe for file in
        pipe_file_in = os.open(PIPE_FILE_IN, os.O_WRONLY)
    # common ressources
    if REVERSE_SHELL or FILE_TRANSFER:
        # queue for ACKs
        ackQueue = queue.Queue()
        # start thread to transmit ack
        transmitAckThread = threading.Thread(name="TransmitAckThread", target=TransmitAckThread)
        transmitAckThread.start()
        
    # wait for transmitter to start?
    ################################
    if (TRANSMITTER_STARTED == True) or (REVERSE_SHELL == True):
        pass
    else:
        print("Waiting for transmitter to start...")
        while TRANSMITTER_STARTED == False:
            f = open(TRANSMITTER_STARTED_FILE, "r")
            if f.read().splitlines()[0] == "true":
                TRANSMITTER_STARTED = True
            f.close()
            sleep(0.1)
    
    # prompt message
    ################      
    if REVERSE_SHELL:
        print("Reverse shell started...")
    print("Waiting for session to be established...")
        
    # clear session flags and counters
    ##################################
    end_session()
        
    # initialize buffer, flags and counters
    got_message = False
    data_buffer = ""
    start = -1
    end = -1    
    # first value to be received will be 1
    seq_tx_prev = 0
    # default value shall be different to 1 (to be received) and different to INVALID_SEQ_NR (default value)
    seq_tx_acked_prev = 250   
    
    # main loop
    ###########
    while True:
        try:            
            # Read string data from stdin      
            # and send [keepalive] or [ack] when needed
            ###########################################
            data = ""
            while data == "":
                try:            
                    if REVERSE_SHELL and NEED_ACK and WAITING_FOR_COMMAND_OUTPUT:
                        if select.select([sys.stdin,],[],[],RETRANSMISSION_TIMEOUT_SEC/2.0)[0]:
                            data = sys.stdin.readline()
                        else:         
                            # send [ack]
                            ############
                            # when reverse shell has no output we need to send the ack here
                            if SESSION_ESTABLISHED and WAITING_FOR_COMMAND_OUTPUT:
                                WAITING_FOR_COMMAND_OUTPUT = False
                                transmit_ack()
                    elif (REVERSE_SHELL or FILE_TRANSFER) and (KEEPALIVE_TIME_SEC_F != 0.0):
                        # note: we subtract the average random delay from KEEPALIVE_TIME_SEC_F
                        if select.select([sys.stdin,],[],[],(KEEPALIVE_TIME_SEC_F - AVG_RND_DELAY_SEC))[0]:
                            data = sys.stdin.readline()
                        else:
                            if FILE_TRANSFER:
                                # read tx_sending_file
                                f = open(TX_SENDING_FILE_FILE, "r")
                                if f.read().splitlines()[0] == "true":
                                    TX_SENDING_FILE = True
                                else:
                                    TX_SENDING_FILE = False
                                f.close()
                            # send [keepalive]
                            ##################
                            # by reverse shell or file transfer we need to do this here
                            # in case of TX_SENDING we skip the transmission of the [keepalive] message
                            if (SESSION_ESTABLISHED == True) and (TX_SENDING == False) and (TX_SENDING_FILE == False) and (RX_RECEIVING_FILE == False):                            
                                # random delay to prevent collission of [keepalive] messages sent by both devices
                                if FILE_TRANSFER:
                                    sleep(float(random.randint(0,RND_MAX_DELAY_MS)/1000.0))
                                minimodem_tx("[keepalive]")
                    else:
                        data = sys.stdin.readline()
                except Exception as e:              
                    # exit app?
                    ###########
                    if run_thread == False:
                        exit(0)                               
                    # noise detected?
                    #################
                    # flush stdin
                    sys.stdin.flush()
                    # clean buffer
                    data = ""
                    stdin_err_cnt = stdin_err_cnt + 1
                    logging.info("< binary data! count = " + str(stdin_err_cnt))
                    # if we receive too many consecutive "binary bytes" the program hangs!
                    # by introducing this small delay we seem to prevent that                    
                    sleep(0.01)
                    
            # process data
            ##############
            # transmit [init_ack_chat], [init_ack_shell] or [init_ack_file] when [init] is received
            # seq_tx, seq_rx, seq_tx_acked are initialized and the session is established
            # note1: if the session was already established, then it is re-initialized!
            # note2: [init] may never come as it may be that our PC initiated the session instead
            # note3: this shall be done here e.g. because in shell mode there is no TX process running
            if data != "":
                if "[init]" in data:
                    if SESSION_ESTABLISHED == False:
                        if REVERSE_SHELL:
                            print("Reverse shell session initiated by communication partner is now established!")
                        elif FILE_TRANSFER:
                            print("File transfer session initiated by communication partner is now established!")
                        else:                        
                            print("Chat session initiated by communication partner is now established!")            
                    init_session() 
                    logging.info("< [init]")
                    # send init_ack
                    if REVERSE_SHELL:
                        minimodem_tx("[init_ack_shell]")
                    elif FILE_TRANSFER:
                        minimodem_tx("[init_ack_file]")
                    else:
                        minimodem_tx("[init_ack_chat]")
                elif "[init_ack_chat]" in data:
                    if SESSION_ESTABLISHED == False:
                        print("Chat session initiated locally is now established!")
                    init_session()
                    logging.info("< [init_ack_chat]")
                elif "[init_ack_file]" in data:
                    if SESSION_ESTABLISHED == False:
                        print("File transfer session initiated locally is now established!")
                    init_session()
                    logging.info("< [init_ack_file]")                
                elif "[init_ack_shell]" in data:
                    if SESSION_ESTABLISHED == False:
                        print("Reverse shell session initiated locally is now established!")            
                    init_session()
                    logging.info("< [init_ack_shell]")                                            
                elif "[keepalive]" in data:
                    logging.info("< [keepalive]")
                elif "[test]" in data:
                    logging.info("< [test]")
                # check if we got data inside encrypted message
                ###############################################
                else:
                    logging.debug("data = " + data)
                    
                    # detect begin and end of message
                    #################################
                    if start == -1:
                        start = data.find("-----BEGIN PGP MESSAGE-----")
                        if start >= 0:
                            end = data.find("-----END PGP MESSAGE-----")
                            if end >= 0:
                                # got a complete message inside data!
                                data_buffer = data[start:end+24]  # remove data before begin message and after end message
                                got_message = True
                            else:
                                # got only start message inside data
                                data_buffer = data[start:] # remove data before begin message
                                        
                    # detect end of message
                    #######################
                    elif end == -1:            
                        end = data.find("-----END PGP MESSAGE-----")
                        if end >= 0:
                            # now we have the complete message                  
                            data_buffer = "".join([data_buffer, data[:end+24]]) # remove data after end message
                            got_message = True               
                        # gather intermediate data
                        else:                            
                            data_buffer = "".join([data_buffer, data])  
                            
                    # decrypt input message
                    #######################
                    if got_message:                    
                        logging.debug("data_buffer = " + data_buffer)                                   
                        # store input data in a temporary file                                        
                        with open(TEMP_GPG_FILE, "w") as data_file:
                            num_bytes_written = data_file.write(data_buffer)
                            logging.debug("Wrote %d bytes to temporal .gpg file." % num_bytes_written)                    
                        # cleanup data_buffer and its flags and indexes for next use
                        got_message = False
                        data_buffer = ""
                        start = -1
                        end = -1  
                        try:
                            # call GPG to decrypt input data
                            # add single quotes around the password in case it contains spaces
                            command = "gpg --batch --passphrase '" + PASSWORD + "' " + ARMOR + " -d " + TEMP_GPG_FILE + SENT_OUT_TO_DEV_NULL
                            p1 = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, text=True)
                            out, err = p1.communicate()                                        
                            if p1.returncode == 0:
                                p1.terminate()
                                p1.kill()                      
                                seq_tx = ord(out[0])-33
                                seq_tx_str = str(seq_tx)
                                # seq_tx_acked is the field seq_rx in the message,
                                # but from our point of view we store it as the "last acknowledged seq_tx that we sent"
                                # note: seq_tx in our context is used to store the current seq_tx inside the TX process
                                seq_tx_acked = ord(out[1])-33 
                                seq_tx_acked_str = str(seq_tx_acked)
                                # store seq_tx_acked that will be checked by our TX process
                                if seq_tx_acked != seq_tx_acked_prev:
                                    f = open(SEQ_TX_ACKED_FILE, "w")
                                    f.write(seq_tx_acked_str)
                                    f.close()
                                    seq_tx_acked_prev = seq_tx_acked
                                    logging.debug("received seq_tx_acked = "+seq_tx_acked_str)                                
                                    
                                # type of message?
                                ##################
                                # ACK
                                #####
                                if out[2:7] == "[ack]":
                                    logging.info("< ack["+seq_tx_str+","+seq_tx_acked_str+"]")
                                # DATA
                                ######
                                elif out[2:8] == "[data]":
                                    decrypted_data = out[8:-1]
                                    logging.debug("The decrypted data in the message is: " + decrypted_data)
                                    # store seq_tx as seq_rx (from the perspective of the receiver) that will be sent/acknowledged next time,
                                    # this always triggers an ACK in TX process, even by repeated messages,
                                    # this is necessary because we don't know if the ACKs actually arrive!
                                    f = open(SEQ_RX_FILE, "w")
                                    f.write(seq_tx_str)
                                    f.close()
                                    logging.debug("received seq_tx = "+seq_tx_str+", now stored as seq_rx to be transmitted/acknowledged next time")                                
                                    # in case of reverse shell we need to send ACK here (just in case the shell has no output, thus no mmshellout.sh is called)                                    
                                    
                                    # new [data] message?
                                    #####################
                                    # when ACK is enabled, we process data only when seq_tx was increased (considering wraparound to zero)
                                    # when ACK is disabled, we process data only when seq_tx was changed
                                    if (seq_tx == (seq_tx_prev + 1)%94) or ((NEED_ACK == False) and (seq_tx != seq_tx_prev)):
                                        seq_tx_prev = seq_tx                         
                                        # process only when data is not empty
                                        if decrypted_data != "":
                                        
                                            # show input data with RX prompt
                                            ################################
                                            if SHOW_RX_PROMPT:
                                                str_tmp = decrypted_data.replace("\n", "\n  ")
                                                if VERBOSE:
                                                    print("< [" + f"{seq_tx:02d}" + "," + f"{seq_tx_acked:02d}" + "] " + str_tmp, flush=True)
                                                else:
                                                    print("< " + str_tmp, flush=True)                                    
                                            else:                                        
                                                print(decrypted_data)
                                                
                                            # reverse shell enabled?
                                            ########################
                                            if REVERSE_SHELL:
                                                # write input command to pipe_shell_in                                            
                                                os.write(pipe_shell_in, bytes(decrypted_data + '\n', 'utf-8'))
                                                logging.debug("Shell output sent.")
                                        # empty data
                                        else:                                        
                                            logging.info("< empty_data["+seq_tx_str+","+seq_tx_acked_str+"]")
                                    # repeated data
                                    else:
                                        str_tmp = decrypted_data.replace("\n", "\n  ")
                                        logging.info("< repeated_data["+seq_tx_str+","+seq_tx_acked_str+"] = " + str_tmp)
                                    # set flag to transmit ACK on timeout
                                    #####################################
                                    if REVERSE_SHELL and NEED_ACK:
                                        WAITING_FOR_COMMAND_OUTPUT = True
                                # FILE
                                ######
                                elif out[2:13] == "[file_name]":
                                    # store seq_tx as seq_rx (from the perspective of the receiver) that will be sent/acknowledged next time,
                                    # this always triggers an ACK in TX process, even by repeated messages,
                                    # this is necessary because we don't know if the ACKs actually arrive!
                                    f = open(SEQ_RX_FILE, "w")
                                    f.write(seq_tx_str)
                                    f.close()
                                    logging.debug("received seq_tx = "+seq_tx_str+", now stored as seq_rx to be transmitted/acknowledged next time")
                                    
                                    # new [file] data?
                                    ##################
                                    # when ACK is enabled, we process data only when seq_tx was increased (considering wraparound to zero)
                                    # when ACK is disabled, we process data only when seq_tx was changed
                                    if (seq_tx == (seq_tx_prev + 1)%94) or ((NEED_ACK == False) and (seq_tx != seq_tx_prev)):
                                        seq_tx_prev = seq_tx        
                                        logging.info("< file_data["+seq_tx_str+","+seq_tx_acked_str+"]")
                                        
                                        # classify file data (state machine)
                                        ####################################
                                        end = out.find("[file]")
                                        if end == -1:
                                            end = out.find("[file_end]")
                                            if end != -1:
                                                # new file (complete, incl. file end)                                            
                                                if file_name == "":
                                                    RX_RECEIVING_FILE = True
                                                    file_name = out[13:end]
                                                    state_file_out = WRITE_AND_DECODE_FILE_OUT_64
                                                # file end
                                                else:
                                                    state_file_out = APPEND_AND_DECODE_FILE_OUT_64
                                                # move end to beginning of file data
                                                end = end + len("[file_end]")
                                            else:
                                                # incomplete file
                                                state_file_out = INCOMPLETE_FILE_OUT_64                                            
                                        else:                            
                                            # new file (beginn)
                                            if file_name == "":
                                                RX_RECEIVING_FILE = True
                                                file_name = out[13:end]
                                                state_file_out = WRITE_FILE_OUT_64
                                            # file part
                                            else:
                                                state_file_out = APPEND_FILE_OUT_64
                                            # move end to beginning of file data
                                            end = end + len("[file]")
                                            
                                        # process file data
                                        ###################
                                        if state_file_out != INCOMPLETE_FILE_OUT_64:                 
                                            # TODO: optimize by using out[end:-1] directly...so we don't copy the data, which may be too big
                                            #       first check: id(decrypted_file_data) == id(out[end:-1]) ???...then it is just a reference, so it is ok like it is now...
                                            decrypted_file_data = out[end:-1]                                    
                                            # new file
                                            if state_file_out == WRITE_FILE_OUT_64:
                                                f = open(TMPFILE_BASE64_IN, "w")
                                                f.write(decrypted_file_data)
                                                f.close()
                                            # new complete file or last part
                                            elif (state_file_out == WRITE_AND_DECODE_FILE_OUT_64) or (state_file_out == APPEND_AND_DECODE_FILE_OUT_64):
                                                if state_file_out == WRITE_AND_DECODE_FILE_OUT_64:
                                                    f = open(TMPFILE_BASE64_IN, "w")
                                                else:
                                                    f = open(TMPFILE_BASE64_IN, "a")
                                                f.write(decrypted_file_data)
                                                f.close()
                                                command = "base64 -d < '" + TMPFILE_BASE64_IN + "' > 'rx_files/" + file_name + "'"
                                                p1 = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, text=True)
                                                out, err = p1.communicate()                                        
                                                if p1.returncode == 0:
                                                    p1.terminate()
                                                    p1.kill()
                                                else:
                                                    logging.warning("could not decode received file!")  
                                                file_name = ""
                                                RX_RECEIVING_FILE = False
                                            # new begin or part of file
                                            elif (state_file_out == WRITE_FILE_OUT_64) or (state_file_out == APPEND_FILE_OUT_64):
                                                if state_file_out == WRITE_FILE_OUT_64:
                                                    f = open(TMPFILE_BASE64_IN, "w")
                                                else:
                                                    f = open(TMPFILE_BASE64_IN, "a")
                                                f.write(decrypted_file_data)
                                                f.close()                                                                                            
                                            logging.debug("The decrypted file data in the message is: " + decrypted_file_data)

                                            # write file data to pipe_file_in
                                            #################################                     
                                            os.write(pipe_file_in, bytes(decrypted_file_data, 'utf-8'))
                                            logging.debug("File data received.")
                                            
                                            # transmit ACK
                                            ##############
                                            if NEED_ACK:                                    
                                                transmit_ack()
                                        # incomplete message
                                        else:
                                            logging.info("< incomplete_file_data["+seq_tx_str+","+seq_tx_acked_str+"]")
                                    # repeated file message
                                    else:                                    
                                        logging.info("< repeated_file_data["+seq_tx_str+","+seq_tx_acked_str+"]")      
                                        # transmit ACK
                                        ##############
                                        if NEED_ACK:                                    
                                            transmit_ack()                              
                                # unknown message type
                                else:
                                    logging.info("< unknown_message["+seq_tx_str+","+seq_tx_acked_str+"]")
                        # handle exceptions from decryption onwards
                        except Exception as e:
                            logging.exception(str(e))
                    # no message detected
                    else:
                        if VERBOSE:
                            # logging.info("< no_message, start="+str(start)+", end="+str(end))
                            # logging.info("  data="+data+", data_buffer="+data_buffer)
                            pass
                        else:
                            logging.debug("< no_message, start="+str(start)+", end="+str(end))
                            logging.debug("  data="+data+", data_buffer="+data_buffer)    

        # handle this exception nicely to catch Ctrl+C, otherwise error seen on terminal
        except KeyboardInterrupt:
            # kill threads
            run_thread=False
            sleep(0.5)
            # output new line, otherwise terminal prompt glued to last text
            print("")
            # WORKAROUND
            # brute-force cleanup
            # TODO: is there a nicer way to clean up here?
            command = "./killaudiocat.sh 2> /dev/null &"
            p1 = subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, text=True)
            out, err = p1.communicate()                                        
            if p1.returncode == 0:
                p1.terminate()
                p1.kill()
            exit(0)
            
    # main loop was exit
    ####################
    # clean up 
    ##########
    os.close(pipe_shell_in)
    os.unlink(PIPE_SHELL_IN)

# call main()
#############
if __name__ == '__main__':
    main()

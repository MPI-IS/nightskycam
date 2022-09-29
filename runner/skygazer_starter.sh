#!/bin/bash

###################################################
#                                                 #
# keeping running nightskycam_runner.sh aggressively #
#                                                 #
###################################################

run () {
    # expected to be in $PATH
    nightskycam_runner.sh &
    PID=$!
    wait $PID
}

while :
      run()
      sleep 60s

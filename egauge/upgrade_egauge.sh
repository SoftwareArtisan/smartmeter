#!/bin/bash

#
# works in pw_egauge_config mode or raw mode
# 


WD=$(dirname $0)
WD=$(cd ${WD}; pwd)

CFG=${WD}/egauge_config.py

STEP=${1:?"Step 1 or 2 -- 1 before time catchup, 2 after time catchup"}
DEVICE=${2:?"egauge device id"}
shift
shift
EXTRA_ARGS="--timeout 60"

if [[ ${STEP} == "1" ]];then
  ${CFG} getregisters ${DEVICE} --cfgfile ${WD}/${DEVICE}_backup.json "$@" ${EXTRA_ARGS}
  ${CFG} setregisters ${DEVICE} --cfgfile ${WD}/empty_config.json "$@" ${EXTRA_ARGS}
  ${CFG} upgrade ${DEVICE} "$@"  ${EXTRA_ARGS}
elif [[ ${STEP} == "2" ]];then
  ${CFG} upgrade-kernel ${DEVICE} "$@"  ${EXTRA_ARGS}
  ${CFG} setregisters ${DEVICE} --cfgfile ${WD}/${DEVICE}_backup.json "$@"  ${EXTRA_ARGS}
  ${CFG} reboot ${DEVICE} "$@"  ${EXTRA_ARGS}
fi

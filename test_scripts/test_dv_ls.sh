#!/bin/bash
##
## TÓM TẮT
##    test_dv_ls
##
## MÔ TẢ
##    Script test CS145 cho project 2.
##    Chạy mô phỏng mạng với từng file JSON, sau đó kiểm tra các route thu được
##    có đúng với route chuẩn được khai báo trong file JSON hay không.

# Phân tích tham số dòng lệnh.
if [ $# -eq 0 ]; then
  ROUTER="BOTH"
elif [[ ( $# -eq 1 ) && ( $1 == "DV" || $1 == "LS" || $1 == "BOTH" ) ]]; then
  ROUTER=$1
else
  printf "Usage: $0 [DV|LS|BOTH]\n"
  exit 1
fi

numCorrect=0
testNum=1
SUCCESS_MESSAGE="SUCCESS: All Routes correct!"
FAILURE_MESSAGE="FAILURE: Not all routes are correct"
TIMEOUT_PER_TEST=60
WORKSPACE=~/tmp/
RESULT_FILE=test_result

# Các hàm phục vụ việc chạy test.

# $1 = DV|LS, $2 = file mô phỏng mạng, $3 = có in đường phân cách hay không.
function test {
  timeOut=0
  printf "\n$testNum. Testing $2 with $1router\n"
  ((testNum++))
  timeout $TIMEOUT_PER_TEST python network.py $2 $1 | tee $RESULT_FILE
  if [ ${PIPESTATUS[0]} -eq 124 ]; then
    timeOut=1
    printf "TIMED OUT\n"
  fi
  resultTail=$(tail -n1 $RESULT_FILE)
  rm -f $RESULT_FILE
  if [[ $resultTail == $SUCCESS_MESSAGE ]]; then
    ((numCorrect++))
  elif [[ $resultTail != $FAILURE_MESSAGE && $timeOut -eq 0 ]]; then
    printf "Fatal error: failed to parse test result message\n"
    rm -rf $WORKSPACE
    exit 1
  fi
  if [ $3 -ne 0 ]; then
    printf "________________________________________"
  fi
  printf "\n"
}

# $1 = DV|LS
function testAll {
  if [[ $1 == DV ]]; then
    testMessage="Testing Distance Vector routing implementation"
  else
    testMessage="Testing Link State routing implementation"
  fi
  printf "================================================================\n"
  printf "$testMessage\n"
  printf "================================================================\n"

  jsonFiles=$( find $(pwd) -maxdepth 1 -name "*.json" )
  echo $jsonFiles
  numJsonFiles=$( echo $jsonFiles | wc -w )
  for jsonFile in $jsonFiles; do
    ((numJsonFiles--))
    test $1 $jsonFile $( if [ $numJsonFiles -eq 0 ]; then echo -n 0; else echo -n 1; fi )
  done
}

####################################################
# CHẠY TEST
####################################################

trap "rm -rf $WORKSPACE; exit 1" SIGINT

rm -rf $WORKSPACE
mkdir $WORKSPACE

if [ $ROUTER == "DV" ]; then
  testAll DV

elif [ $ROUTER == "LS" ]; then
  testAll LS

else
  testAll DV
  testAll LS

fi

rm -rf $WORKSPACE

#####################################################
# TÓM TẮT KẾT QUẢ
#####################################################

printf "================================================================\n\n"
printf "TESTS PASSED: $numCorrect/$((testNum - 1))\n"

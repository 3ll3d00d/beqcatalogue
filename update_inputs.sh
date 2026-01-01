#!/bin/bash -x

authors=(
    halcyon888
    t1g8rsfan
    kaelaria
    remixmark
    mikejl
#    bombaycat007
)
dirs=(
    miniDSPBEQ
    miniDSPBEQ
    Beq1
    miniDSPBEQ
    xml
#    miniDSPBEQ
)
repoAuthors=(
    halcyon-888
    T1G8RS-FAN
    kaelaria
    remixmark
    MikejLarson
#    BombayCat007
)
repoNames=(
    miniDSPBEQ
    MiniDSPBEQ
    Beq1
    miniDSPBEQ
    xml
#    miniDSPBEQ
)
for i in "${!authors[@]}"
do
  echo "Processing ${authors[${i}]}"
  p=".input/${authors[${i}]}/${dirs[${i}]}"
  if [[ -d "${p}" ]]
  then
    M_SHA=$(cat meta/"${authors[${i}]}".sha)
    pushd "${p}" || exit
    git pull
  else
    git clone https://github.com/"${repoAuthors[${i}]}"/"${repoNames[${i}]}".git "${p}"
    unset M_SHA
    pushd "${p}" || exit
  fi

#  DIFF_INC='*BEQ*'
#  [[ ${authors[${i}]}"" == kaelaria ]] && DIFF_INC="tv\/ movies\/"
  [[ -z ${M_SHA} ]] && DIFF_RANGE=$(git hash-object -t tree /dev/null) || DIFF_RANGE="${M_SHA}"..HEAD
  if [[ ${authors[${i}]}"" == kaelaria ]]
  then
    git diff --name-only -z "${DIFF_RANGE}" -- tv\/ movies\/ | xargs -0 -I{} -- git  log  -1 --format="\"{}\",%at" {} | sort > ../../../meta/"${authors[${i}]}".diff
  else
    git diff --name-only -z "${DIFF_RANGE}" -- *BEQ* | xargs -0 -I{} -- git  log  -1 --format="\"{}\",%at" {} | sort > ../../../meta/"${authors[${i}]}".diff
  fi
  git rev-parse HEAD > ../../../meta/"${authors[${i}]}".sha

  popd || exit
  echo "Processed ${authors[${i}]}"
done

#!/bin/zsh
export PYTHONUTF8=1
cd -- "${0:A:h:h}" || exit 1
print 'NOVA 개발 키 설정: 입력 문자는 보이지 않습니다. 붙여넣은 뒤 Enter를 누르세요.'
./.venv-rag/bin/python tools/configure_dev_key.py
result=$?
if (( result != 0 )); then
  print '키 저장에 실패했습니다. 위 오류 메시지만 알려주세요. 키 자체는 보내지 마세요.'
fi
read '?창을 닫으려면 Enter를 누르세요. '
exit $result

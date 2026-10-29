#!/bin/zsh
set -eu
project_dir=${0:A:h}
bundled_python="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
python_bin=""
for candidate in "$project_dir/.venv/bin/python3" "$bundled_python" "$(command -v python3 || true)"; do
  if [[ -x "$candidate" ]] && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
    python_bin="$candidate"
    break
  fi
done
if [[ -z "$python_bin" ]]; then
  print "Python 3.10 이상이 필요합니다. Python을 설치한 뒤 다시 실행해 주세요."
  read -k 1
  exit 1
fi
cd "$project_dir"
"$python_bin" "$project_dir/launch.py"

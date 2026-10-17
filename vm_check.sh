#!/usr/bin/env bash
# Read-only readiness check for the LinuxONE VM (#11). Changes nothing; run it on the VM:
#   bash vm_check.sh [lab-image]
img=${1:-}
ok() { printf '  %-28s %s\n' "$1" "$2"; }
echo "VM readiness"
ok "architecture" "$(uname -m)"
ok "NNPA (on-chip AI)" "$(grep -o -m1 nnpa /proc/cpuinfo || echo 'NOT FOUND: report CPU numbers only')"
ok "cores / memory" "$(nproc) / $(free -g | awk '/Mem/{print $2" GB"}')"
ok "free disk on /" "$(df -h / | awk 'NR==2{print $4}')"
ok "python3" "$(python3 --version 2>&1)"
ok "docker" "$(docker --version 2>/dev/null || echo missing)"
ok "repo data/" "$( [ -f data/features.csv ] && echo present || echo 'missing: git clone first')"
ok ".env key" "$( grep -q '^BLOCKSCOUT_API_KEY=.' .env 2>/dev/null && echo set || echo 'not set (only needed for the live box)')"
if [ -n "$img" ]; then
  ok "lab image" "$(docker image inspect "$img" >/dev/null 2>&1 && echo present || echo "missing: $img")"
  run() { docker run --rm "$img" python3 -c "$1" 2>/dev/null || echo missing; }
  ok "tensorflow" "$(run 'import tensorflow as t; print(t.__version__)')"
  ok "zDNN plugin (pip)" "$(docker run --rm "$img" sh -c 'pip show ibm-zdnn-plugin 2>/dev/null | grep ^Version' || echo missing)"
  ok "TF devices" "$(run 'import tensorflow as t; print([d.device_type for d in t.config.list_physical_devices()])')"
  ok "xgboost" "$(run 'import xgboost as x; print(x.__version__)')"
  ok "scikit-learn" "$(run 'import sklearn as s; print(s.__version__)')"
  ok "llama.cpp (python)" "$(run 'import llama_cpp as l; print(l.__version__)')"
fi

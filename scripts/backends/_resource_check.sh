#!/bin/bash
# 资源检查抽象. backend-agnostic.
# Usage:
#   _resource_check.sh free_gb              → 输出 free RAM (GB int)
#   _resource_check.sh fit_count <hard> <per_run>  → 输出能起几个进程
# Env:
#   FREE_GB_OVERRIDE=<int>  测试 mock free RAM
#
# Note: free -g rounds DOWN to integer GB. Sub-1-GB slack reads as 0.
# 故意保守 (永不 overcommit, 宁错过 1 路也不挤爆 RAM).
set -euo pipefail

cmd="${1:-}"

case "$cmd" in
    free_gb)
        if [[ -n "${FREE_GB_OVERRIDE:-}" ]]; then
            echo "$FREE_GB_OVERRIDE"
        else
            free -g | awk '/^Mem:/ {print $7}'
        fi
        ;;
    fit_count)
        hard="${2:?hard threshold required}"
        per_run="${3:?per_run estimate required}"
        if [[ -n "${FREE_GB_OVERRIDE:-}" ]]; then
            free="$FREE_GB_OVERRIDE"
        else
            free=$(free -g | awk '/^Mem:/ {print $7}')
        fi
        usable=$(awk -v f="$free" -v h="$hard" 'BEGIN{r=f-h; if(r<0)r=0; print r}')
        count=$(awk -v u="$usable" -v p="$per_run" 'BEGIN{print int(u/p)}')
        echo "$count"
        ;;
    *)
        echo "usage: $0 {free_gb|fit_count <hard> <per_run>}" >&2
        exit 2
        ;;
esac

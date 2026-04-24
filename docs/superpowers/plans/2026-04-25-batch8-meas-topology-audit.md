# Batch 8 — Meas_ES{i} 拓扑审计

> 状态：DRAFT（等待人工 APPROVE 后执行）  
> 约束全文：`docs/superpowers/plans/2026-04-24-kundur-sps-investigation-constraints.md`（REQUIRED PRE-READ）

---

## 目标

确认/否定 RC-A：Meas_ES{i} 测量块是否接在错误拓扑位置（测量的是非 ESS 支路电流）。

---

## 本批次授权操作

| 操作 | 允许 | 备注 |
|---|---|---|
| `simulink_run_script` 加载模型 | ✅ | `load_system` only |
| `get_param(..., 'Handle')` | ✅ | read-only |
| `get_param(..., 'PortConnectivity')` | ✅ | read-only |
| `get_param(..., 'BlockType')` | ✅ | read-only |
| `get_param(..., 'Dirty')` 状态检查 | ✅ | read-only |
| `probe_meas_topology.m`（新探针） | ✅ | 已写入 `probes/kundur/` |
| `set_param` | ❌ 禁止 | 会产生 dirty |
| `sim` / 仿真运行 | ❌ 禁止 | 本批次不需要 |
| `save_system` / `simulink_save_model` | ❌ 禁止 | 绝对禁止 |

---

## 执行步骤

### Step 1 — 运行 `probe_meas_topology.m`（MCP ready 后立即执行）

```matlab
repo = 'C:\Users\27443\Desktop\Multi-Agent  VSGs';
addpath(fullfile(repo, 'probes', 'kundur'));
run_dir = fullfile(repo, 'results', 'harness', 'kundur', ...
          '20260424-kundur-sps-workpoint-alignment');
model_slx = fullfile(repo, 'scenarios', 'kundur', ...
            'simulink_models', 'kundur_vsg_sps.slx');
if ~bdIsLoaded('kundur_vsg_sps')
    load_system(model_slx);
end
opts.output_filename = 'meas_topology_audit.json';
results = probe_meas_topology('kundur_vsg_sps', run_dir, opts);
fprintf('RESULT: done rc_a_count=%d dirty_after=%d\n', ...
    results.rc_a_count, results.provenance.model_dirty_after);
```

**Dirty 门控**：若 `model_dirty_after=1` → 立即 STOP（约束条件 3）。

### Step 2 — 读取并解释 artifact

关键字段：

| 字段 | RC-A 成立条件 |
|---|---|
| `meas_results[i].connects_to_expected_branch` | 全部为 `false` |
| `meas_results[i].connects_to_expected_vsrc` | 全部为 `false` |
| `meas_results[i].connects_to_gen_src` | 任意为 `true` → 强 RC-A 证据 |
| `rc_a_count` | 4 = RC-A 完全确认；1–3 = 部分确认 |

### Step 3 — 补充诊断（若 Step 2 结果仍模糊）

若 Meas_ES{i} 确实连接到 expected branch（RC-A 不成立），则需检查：
- 是否存在额外增益块在 Iabc 信号路径（RC-E）
- 使用 `simulink_run_script` 获取 Iabc 信号路径：`find_system(model, 'Name', 'Iabc_ES1')`

### Step 4 — 写出终止 Artifact

- 路径：`results/harness/kundur/20260424-kundur-sps-workpoint-alignment/attachments/meas_topology_audit.json`
- 由 `probe_meas_topology.m` 自动写出

---

## 终止条件（任一满足即 STOP）

1. `meas_topology_audit.json` 写出 → 批次完成
2. `model_dirty_after=1` → 立即 STOP + 汇报
3. MCP 调用失败超过 2 次 → STOP + 等待重连
4. 结果与当前工作假设矛盾 → STOP + 汇报

---

## STOP 后更新

1. `summary.md` 当前状态节（覆写）
2. `NOTES.md` "现在在修" 节（≤3 行，含指针）
3. 汇报格式见约束文档

---

## 上下文指针

| 文件 | 用途 |
|---|---|
| `probes/kundur/probe_meas_topology.m` | 本批次主探针（Batch 8 新建） |
| `results/.../attachments/pe_magnitude_diagnosis.json` | Batch 7 RC-A 候选依据 |
| `results/.../summary.md` | 最新 verdict |

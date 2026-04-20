# probes — 单模型诊断脚本层

每个脚本绑定具体模型，不属于工具链（不被 MCP、Bridge、训练循环调用）。
脚本可自由调用 slx_helpers/ 内核和 MCP 工具辅助诊断。

## 组织方式

```
probes/
  kundur/     ← Kundur 4机系统专用诊断
  ne39/       ← NE39 39节点系统专用诊断
    probe_phang_sensitivity.m
  archive/    ← 确认不再需要的旧探针
```

## 调用方式

训练管理系统 / Claude 对话中：
```
simulink_run_script("slx_run_quiet('probes/ne39/probe_phang_sensitivity')")
```

MATLAB 命令行：
```matlab
run('probes/ne39/probe_phang_sensitivity.m')
```

## 文件头规范

```matlab
% probe_xxx.m
% 模型: NE39bus_v2
% 检查: [一句话描述检查目标]
% 关联问题: [触发此探针的现象]
```

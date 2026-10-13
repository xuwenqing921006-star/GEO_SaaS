<script setup lang="ts">
defineProps<{ kind: "upload" | "diagnostic" }>();
</script>

<template>
  <p class="state-success" role="status">
    {{
      kind === "upload"
        ? "演示解析任务完成；真实提取结果将在后续 T-007 接入。"
        : "演示诊断任务已受理；真实 Worker 结果将在后续阶段写回此页面。"
    }}
  </p>
</template>

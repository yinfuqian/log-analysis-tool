<template>
  <div class="analysis-result">
    <h2>{{ currentStatus }}</h2>
    <el-progress :percentage="analysisProgress"></el-progress>

    <div v-if="analysisComplete" class="result">
      <h3>分析完成</h3>
      <p>日志分析结果：</p>
      <markdown-viewer :content="parsedLog" />
      <markdown-viewer :content="parsedCode" class="mt-4" />

      <div v-if="codeSnippets.length" class="mt-4">
        <h4>涉及代码片段：</h4>
        <div
          v-for="(snippet, index) in codeSnippets"
          :key="index"
          class="code-snippet"
        >
          <div class="file-path">
            {{ snippet.file }} (行号: {{ snippet.line }})
          </div>
          <pre><code class="language-java">{{ snippet.snippet }}</code></pre>
        </div>
      </div>
    </div>

    <el-dialog
      title="错误报告"
      v-model="dialogVisible"
      width="60%"
      :before-close="handleClose"
    >
      <markdown-viewer :content="parsedLog" />
      <markdown-viewer :content="parsedCode" class="mt-4" />

      <div v-if="codeSnippets.length" class="mt-4">
        <h4>涉及代码片段：</h4>
        <div
          v-for="(snippet, index) in codeSnippets"
          :key="index"
          class="code-snippet"
        >
          <div class="file-path">
            {{ snippet.file }} (行号: {{ snippet.line }})
          </div>
          <pre><code class="language-java">{{ snippet.snippet }}</code></pre>
        </div>
      </div>

      <template #footer>
        <el-button @click="dialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import analysisresult from '@/api/analysisresult';
export default analysisresult;
</script>

// MarkdownViewer.vue
<template>
  <div v-html="compiledMarkdown" class="markdown-body"></div>
</template>

<script setup>
import MarkdownIt from 'markdown-it'
import { computed } from 'vue'
const props = defineProps({ content: String })
const md = new MarkdownIt({ html: true, linkify: true, typographer: true })
const compiledMarkdown = computed(() => md.render(props.content || ''))
</script>

<style scoped>
/* 可引入 GitHub markdown 风格 */
@import 'https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.2.0/github-markdown.min.css';

.markdown-body {
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  line-height: 1.6;
  padding: 20px;
}
</style>

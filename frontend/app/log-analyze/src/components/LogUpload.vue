<template>
  <el-card>
    <el-form>
      <!-- 选择产品 -->
      <el-form-item label="选择产品">
        <el-select v-model="selectedProduct" placeholder="选择产品" @change="onProductChange">
          <el-option v-for="p in products" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
      </el-form-item>

      <!-- 选择模块 -->
      <el-form-item label="选择模块">
        <el-select v-model="selectedModule" placeholder="选择模块">
          <el-option v-for="m in modules" :key="m.module_id" :label="m.module_name" :value="m.module_id" />
        </el-select>
      </el-form-item>

      <!-- 选择代码分支 -->
      <el-form-item label="分支地址">
        <el-select v-model="selectedBranch" placeholder="选择代码分支" @change="onBranchChange">
          <el-option v-for="b in branches" :key="b.address" :label="b.address" :value="b.address" />
        </el-select>
      </el-form-item>

      <!-- 选择分支版本 -->
      <el-form-item label="分支版本">
        <el-select v-model="selectedBranchVersion" placeholder="选择分支版本">
          <el-option v-for="bv in filteredBranchVersions" :key="bv" :label="bv" :value="bv" />
        </el-select>
      </el-form-item>

      <!-- 上传日志 -->
      <el-form-item label="上传日志">
        <el-upload :action="uploadUrl" :file-list="fileList" :on-success="onUploadSuccess" :before-upload="beforeUpload"
          :data="uploadParams" :show-file-list="true" :on-error="onUploadError">
          <el-button type="primary">点击上传</el-button>
        </el-upload>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script>
import logupload from '@/api/logupload';
export default logupload;
</script>

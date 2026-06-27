const path = require('path');  // 确保引入 path 模块

const { defineConfig } = require('@vue/cli-service');

module.exports = defineConfig({
  transpileDependencies: true,

  devServer: {
    client: {
      overlay: false, // 关闭浏览器弹出错误提示
    },
    watchFiles: ['src/**/*'], // 监视 src 目录下的文件变化
    hot: true,  // 启用 HMR 热更新
    open: true, // 自动打开浏览器
  },

  configureWebpack: {
    optimization: {
      minimize: false, // 禁用代码压缩
    },
    performance: {
      hints: false, // 关闭性能提示
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'), // 配置 `@` 指向 `src` 目录
      }
    }
  },

  chainWebpack: (config) => {
    config.module
      .rule('images')
      .test(/\.(png|jpe?g|gif|svg)(\?.*)?$/)
      .use('url-loader')
      .loader('url-loader')
      .options({
        limit: 10000,
        name: 'assets/[name].[hash:7].[ext]'
      });

    config.module
      .rule('fonts')
      .test(/\.(woff2?|eot|ttf|otf)$/)
      .use('url-loader')
      .loader('url-loader')
      .options({
        limit: 10000,
        name: 'assets/fonts/[name].[hash:7].[ext]'
      });

    config.optimization.splitChunks({
      chunks: 'all',
      maxInitialRequests: 5,
      maxAsyncRequests: 6,
      automaticNameDelimiter: '-',
      name: (module) => {
        const moduleName = module.context.split('/').pop();
        return `chunk-${moduleName}`;
      }
    });
  }
});

import type { NextConfig } from "next";
import nextBuildFilter, { FilterOptions } from "next-build-filter";

const filterConfig: FilterOptions = {
  enabled: true,
  verbose: true,
  enableInDev: true,
  supportPagesRouter: true,
  supportAppRouter: true,
  appDir: 'src/app',

}

const nextConfig: NextConfig = {
  /* config options here */
  reactCompiler: true,
  turbopack: {},
  experimental: {
    // Next 的 rewrite 代理默认 30s 超时, 上传 txt 后要拆词 + 本地 ONNX 向量化,
    // 大文档往往需要几十秒到数分钟, 这里放宽到 30 分钟, 避免代理先断开。
    proxyTimeout: 30 * 60 * 1000,
  },
  async rewrites() {
    const backend = process.env.PYTHON_BACKEND_URL || "http://localhost:8000";
    return {
      // beforeFiles 优先于 route handlers, 确保 /api/* 全部代理到 Python 后端
      beforeFiles: [
        {
          source: "/api/:path*",
          destination: `${backend}/api/:path*`,
        },
      ],
    };
  },
};

const filterNextConfig = nextBuildFilter(filterConfig)(nextConfig);
export default filterNextConfig;
